# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Golden-host drift over watched FILES (ROADMAP 21.1 S7).

20.2 compares inventory the server already holds -- packages, users, mounts.
This compares files, and files need their own comparator rather than the
generic one for a reason that is the whole point of the slice: **a row here
records an OUTCOME, not just a value.**

WHY THE GENERIC COMPARATOR WOULD BE WRONG
------------------------------------------
``compare_category`` compares identity -> fields. Applied to file state it
would treat every row as a measurement, and produce confident nonsense:

* A path the target could not READ has a null sha256. Against a reference with
  a real hash that is "different" -- a reported divergence that may not exist.
  Against another unreadable host it is "identical" -- two hosts agreeing
  because neither could look.
* A path present on the reference and simply NOT WATCHED on the target would
  read as "missing", i.e. as a deleted file. It is not deleted; nobody asked.

So each pair of rows lands in one of three places, and the third is the one
that does not exist in any other category:

* **drift**       -- both sides measured, and they disagree. Real.
* **identical**   -- both sides measured, and they agree. Real.
* **blind spot**  -- at least one side did not measure. NOT drift, and
                     emphatically not agreement. Surfaced separately so an
                     operator reading "no differences" knows how much of the
                     watch list that verdict actually covers.

THE EMPTY-WATCH-LIST TRAP
--------------------------
Two hosts with no watch list assigned have zero rows each, and every
set-difference over two empty sets is empty. The category would report
"identical" for a comparison that never happened -- the fabricated all-clear
this phase exists to prevent, arriving through the back door of a feature
working exactly as coded. ``compare_files`` refuses that case explicitly.
"""

from typing import Any, Dict, List

from backend.i18n import _
from backend.persistence import models
from backend.persistence.models.file_watch import (
    STATE_ABSENT,
    STATE_PRESENT,
    STATES_NOT_MEASURED,
)

# What a difference in each field MEANS to an operator, so the UI does not have
# to guess. Order is the order they are reported in.
COMPARED_FIELDS = ("sha256", "mode", "owner", "group_name", "type", "target")

# Same cap as the other categories: counts stay exact, lists are bounded.
MAX_ITEMS_PER_BUCKET = 200


def _rows_by_path(db_session, host_id) -> Dict[str, Any]:
    rows = (
        db_session.query(models.HostFileState)
        .filter(models.HostFileState.host_id == host_id)
        .all()
    )
    return {row.path: row for row in rows}


def _describe(row) -> Dict[str, Any]:
    return {
        "name": row.path,
        "state": row.state,
        "sha256": row.sha256,
        "mode": row.mode,
        "owner": row.owner,
        "group_name": row.group_name,
        "type": row.type,
        "target": row.target,
    }


def _blind_spot(path: str, side: str, reason: str) -> Dict[str, str]:
    """One path we could not compare, and which side could not answer."""
    return {"name": path, "side": side, "reason": reason}


def _field_differences(ref, tgt) -> List[Dict[str, Any]]:
    """Fields that disagree between two MEASURED rows.

    Only called when both sides are ``present``; the caller has already dealt
    with every outcome where one side has no measurement to offer.
    """
    delta = []
    for field in COMPARED_FIELDS:
        ref_value = getattr(ref, field, None)
        tgt_value = getattr(tgt, field, None)
        if ref_value != tgt_value:
            delta.append({"field": field, "reference": ref_value, "target": tgt_value})
    return delta


def _classify(path, ref, tgt, buckets) -> None:
    """Place one watched path into exactly one bucket."""
    missing, extra, different, blind = buckets

    # A side that did not measure cannot contribute to a verdict, whichever
    # side it is and whatever the other side found.
    for row, side in ((ref, "reference"), (tgt, "target")):
        if row is None:
            blind.append(_blind_spot(path, side, "not_watched"))
            return
        if row.state in STATES_NOT_MEASURED:
            blind.append(_blind_spot(path, side, row.state))
            return

    ref_present = ref.state == STATE_PRESENT
    tgt_present = tgt.state == STATE_PRESENT

    if ref_present and tgt.state == STATE_ABSENT:
        # Real drift: the reference has this file and the target does not.
        missing.append(_describe(ref))
        return
    if ref.state == STATE_ABSENT and tgt_present:
        extra.append(_describe(tgt))
        return
    if ref.state == STATE_ABSENT and tgt.state == STATE_ABSENT:
        # Neither host has it. Genuine agreement, not a gap.
        return

    delta = _field_differences(ref, tgt)
    if delta:
        different.append({"name": path, "fields": delta})


def compare_files(db_session, reference_host_id, host_id) -> Dict[str, Any]:
    """Compare watched-file state between a reference host and a target.

    Shape-compatible with ``compare_category`` -- the API and UI treat it as
    one more category -- plus a ``blind_spots`` bucket the others do not need.
    """
    ref_rows = _rows_by_path(db_session, reference_host_id)
    tgt_rows = _rows_by_path(db_session, host_id)

    if not ref_rows and not tgt_rows:
        # See THE EMPTY-WATCH-LIST TRAP in the module docstring. Every
        # set-difference below would be empty and the category would announce
        # that two hosts match, having compared nothing at all.
        return {
            "comparable": False,
            "not_comparable": {
                "category": "files",
                "side": "both",
                "reason": "no_watch_list",
                "detail": _(
                    "Neither host has a file watch list assigned, so there is "
                    "nothing to compare."
                ),
            },
            "missing": [],
            "extra": [],
            "different": [],
            "blind_spots": [],
            "counts": {
                "missing": 0,
                "extra": 0,
                "different": 0,
                "blind_spots": 0,
                "reference_total": 0,
                "target_total": 0,
            },
            "truncated": False,
        }

    missing: List[Dict] = []
    extra: List[Dict] = []
    different: List[Dict] = []
    blind: List[Dict] = []
    buckets = (missing, extra, different, blind)

    # The union, so a path watched on only ONE side is still accounted for --
    # as a blind spot, never as a deletion.
    for path in sorted(set(ref_rows) | set(tgt_rows)):
        _classify(path, ref_rows.get(path), tgt_rows.get(path), buckets)

    for bucket in buckets:
        bucket.sort(key=lambda item: item["name"])

    return {
        "comparable": True,
        "missing": missing[:MAX_ITEMS_PER_BUCKET],
        "extra": extra[:MAX_ITEMS_PER_BUCKET],
        "different": different[:MAX_ITEMS_PER_BUCKET],
        # Deliberately NOT folded into the other three: a blind spot is not a
        # difference, and counting it as one would inflate a drift report with
        # things nobody measured.
        "blind_spots": blind[:MAX_ITEMS_PER_BUCKET],
        "counts": {
            "missing": len(missing),
            "extra": len(extra),
            "different": len(different),
            "blind_spots": len(blind),
            "reference_total": len(ref_rows),
            "target_total": len(tgt_rows),
        },
        "truncated": any(len(b) > MAX_ITEMS_PER_BUCKET for b in buckets),
    }
