# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Golden-host baseline: how one host differs from a reference (Phase 20.2, S5).

The OTHER kind of drift. ``config_mgmt_drift`` answers "does this host match the
profile we assigned it"; this answers "does this host match that host". Both are
drift, and an operator reaches for the second when there is no profile yet --
"staging works and production does not, what is different".

WHY THIS IS BOUNDED, AND DELIBERATELY SO
----------------------------------------
"Capture a reference host and compare everything" is unbounded: it means
comparing arbitrary files and configuration, which needs a general fact
collector. That substrate is osquery (Phase 21.1) and it lands AFTER this.

So this compares only facts the agent ALREADY reports -- packages, users,
groups, interfaces, storage, repositories, firewall state, certificates. That
is a differ, not a collector, which matters: osquery replaces collectors. When
21.1 lands it adds fact sources to this comparison rather than replacing it.

WHY IT STORES NOTHING
---------------------
No table, no migration. The comparison is a pure function of two hosts' current
inventory, and there is no lifespan to track the way ``config_drift_finding``
tracks one -- a category either differs right now or it does not. Committing to
a schema here before the osquery-era shape is known would be a guess we would
have to migrate away from.
"""

import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.i18n import _
from backend.persistence import models

logger = logging.getLogger(__name__)

# A category is (model, identity column, compared columns). The identity is what
# makes two rows "the same thing" across hosts; the compared columns are what
# makes them differ. Both are per category because there is no useful generic
# answer -- packages match on name and differ on version, mounts match on mount
# point and differ on filesystem.
_CATEGORIES: Dict[str, Tuple[Any, str, Tuple[str, ...]]] = {
    "packages": (models.SoftwarePackage, "package_name", ("package_version",)),
    "repositories": (models.ThirdPartyRepository, "name", ("url", "enabled")),
    "users": (models.UserAccount, "username", ("shell", "home_directory")),
    "groups": (models.UserGroup, "group_name", ()),
    "interfaces": (models.NetworkInterface, "interface_name", ("interface_type",)),
    "storage": (models.StorageDevice, "mount_point", ("filesystem",)),
    "certificates": (models.HostCertificate, "certificate_name", ("issuer",)),
    "firewall": (models.FirewallStatus, "firewall_name", ("enabled",)),
}

CATEGORIES: Tuple[str, ...] = tuple(sorted(_CATEGORIES))

# Comparing every package on two full workstations produces thousands of rows
# that no operator reads. The counts stay exact; the per-item lists are capped
# so one API call cannot return a megabyte of JSON.
MAX_ITEMS_PER_BUCKET = 200


class BaselineError(ValueError):
    """A comparison that cannot be performed. Carries an HTTP status."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def _rows_by_identity(db_session, model, identity: str, host_id) -> Dict[str, Any]:
    """This host's rows for one category, keyed by identity value."""
    out: Dict[str, Any] = {}
    for row in db_session.query(model).filter(model.host_id == host_id).all():
        key = getattr(row, identity, None)
        if key is None:
            # Nothing to match on across hosts; counting it would report a
            # difference that cannot be acted on.
            continue
        out[str(key)] = row
    return out


def _describe(row, identity: str, compared: Iterable[str]) -> Dict[str, Any]:
    """The identity plus the compared fields, as plain JSON-able values."""
    item: Dict[str, Any] = {"name": str(getattr(row, identity, "") or "")}
    for field in compared:
        value = getattr(row, field, None)
        item[field] = None if value is None else str(value)
    return item


def _differences(reference, target, compared: Iterable[str]) -> Dict[str, Any]:
    """The compared fields that disagree, as ``{field: {reference, target}}``."""
    delta: Dict[str, Any] = {}
    for field in compared:
        ref_value = getattr(reference, field, None)
        tgt_value = getattr(target, field, None)
        if ref_value != tgt_value:
            delta[field] = {
                "reference": None if ref_value is None else str(ref_value),
                "target": None if tgt_value is None else str(tgt_value),
            }
    return delta


def compare_category(db_session, category: str, reference_host_id, host_id) -> Dict:
    """Compare ONE category between a reference host and a target host.

    Returns ``{missing, extra, different, counts}``:

    * ``missing``   -- on the reference, absent from the target
    * ``extra``     -- on the target, absent from the reference
    * ``different`` -- present on both, but a compared field disagrees

    Named from the TARGET's point of view, because that is the host the operator
    is trying to fix: "missing" is what it needs, "extra" is what it has that
    the reference does not.
    """
    model, identity, compared = _CATEGORIES[category]
    ref_rows = _rows_by_identity(db_session, model, identity, reference_host_id)
    tgt_rows = _rows_by_identity(db_session, model, identity, host_id)

    missing, extra, different = [], [], []

    for key, row in ref_rows.items():
        if key not in tgt_rows:
            missing.append(_describe(row, identity, compared))
            continue
        delta = _differences(row, tgt_rows[key], compared)
        if delta:
            different.append({"name": key, "fields": delta})

    for key, row in tgt_rows.items():
        if key not in ref_rows:
            extra.append(_describe(row, identity, compared))

    for bucket in (missing, extra, different):
        bucket.sort(key=lambda item: item["name"])

    return {
        "missing": missing[:MAX_ITEMS_PER_BUCKET],
        "extra": extra[:MAX_ITEMS_PER_BUCKET],
        "different": different[:MAX_ITEMS_PER_BUCKET],
        # Exact even when the lists above are capped, so a summary never
        # under-reports the size of a divergence.
        "counts": {
            "missing": len(missing),
            "extra": len(extra),
            "different": len(different),
            "reference_total": len(ref_rows),
            "target_total": len(tgt_rows),
        },
        "truncated": any(
            len(bucket) > MAX_ITEMS_PER_BUCKET for bucket in (missing, extra, different)
        ),
    }


def resolve_categories(requested: Optional[Iterable[str]]) -> List[str]:
    """Validate a caller's category selection, or return them all.

    An unknown category is refused rather than ignored: silently dropping it
    would return a clean-looking result for a comparison the caller believes
    they asked for.
    """
    if not requested:
        return list(CATEGORIES)
    wanted = [str(name).strip().lower() for name in requested if str(name).strip()]
    unknown = [name for name in wanted if name not in _CATEGORIES]
    if unknown:
        # Literal msgid: gettext keys on the English text, so the message has
        # to be a literal here rather than assembled at the raise site.
        raise BaselineError(
            _("Unknown comparison category: %s") % ", ".join(sorted(unknown)),
            status=400,
        )
    return wanted or list(CATEGORIES)


def compare_hosts(
    db_session, reference_host_id, host_id, categories: Optional[Iterable[str]] = None
) -> Dict[str, Any]:
    """Compare a target host against a reference host across categories.

    Raises ``BaselineError`` when either host is unknown, or when the two are
    the same host -- a host never differs from itself, and returning an empty
    result for that would look like a clean comparison rather than a mistake.
    """
    if str(reference_host_id) == str(host_id):
        raise BaselineError("a host cannot be compared against itself", status=400)

    wanted = resolve_categories(categories)

    hosts = {}
    for label, ident in (("reference", reference_host_id), ("target", host_id)):
        row = db_session.query(models.Host).filter(models.Host.id == ident).first()
        if row is None:
            raise BaselineError(
                (
                    _("Reference host not found")
                    if label == "reference"
                    else _("Target host not found")
                ),
                status=404,
            )
        hosts[label] = row

    results = {}
    total_differences = 0
    for category in wanted:
        outcome = compare_category(db_session, category, reference_host_id, host_id)
        results[category] = outcome
        total_differences += sum(
            outcome["counts"][key] for key in ("missing", "extra", "different")
        )

    return {
        "reference_host_id": str(reference_host_id),
        "reference_fqdn": hosts["reference"].fqdn,
        "host_id": str(host_id),
        "host_fqdn": hosts["target"].fqdn,
        "categories": results,
        "total_differences": total_differences,
        # The headline an operator wants before opening any category.
        "identical": total_differences == 0,
    }
