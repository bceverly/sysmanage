# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""What a host CAN answer -- the shared reader for Phase 21.1 S6.

S1 made every agent advertise which fact tables it serves and why it does not
serve the rest. S6 is the other half: the consumers -- compliance, vuln, fleet
and the 20.2 drift baselines -- reading that advertisement and saying "not
covered here" instead of showing an empty result.

WHY THIS IS FOUR-VALUED AND NOT A BOOLEAN
------------------------------------------
``covered(host, "mounts")`` returning True/False loses the distinction the
whole phase exists for. The four answers are genuinely different actions:

* ``SERVED``          -- ask; the data is real.
* ``NOT_APPLICABLE``  -- a Windows host has no ``mounts``. Not a gap, not a
                        defect, and NOT something to show an operator as a
                        finding.
* ``UNSUPPORTED``     -- the host could serve it and cannot right now
                        (unprivileged agent, broken provider). This IS worth
                        showing: it is fixable.
* ``UNKNOWN``         -- the host never advertised. An agent older than 21.1,
                        or one whose report could not be built.

THE THIRD STATE IS THE ONE THAT BITES
-------------------------------------
``UNKNOWN`` must never be treated as "not covered". Every host in a fleet is
pre-21.1 until it is upgraded, and a consumer that reads unknown as uncovered
would switch off for the entire estate the day this shipped -- while looking
like it was working. It is the same trap ``limited_flag`` documents for
capability gating: absence of an advertisement is not an advertisement of
absence.

So the rule for callers is: **UNKNOWN means proceed as before.** Consumers
degrade only on a POSITIVE statement that the host cannot answer.
"""

import logging
from typing import Any, Dict, Optional, Tuple

from backend.services import agent_capability_service as caps

logger = logging.getLogger(__name__)

SERVED = "served"
NOT_APPLICABLE = "not_applicable"
UNSUPPORTED = "unsupported"
UNKNOWN = "unknown"

# The states in which a consumer should NOT report a finding built on this
# table. ``UNKNOWN`` is deliberately absent -- see the module docstring.
NOT_ANSWERABLE = (NOT_APPLICABLE, UNSUPPORTED)


def coverage(host) -> Optional[Dict[str, Any]]:
    """The host's fact-coverage advertisement, or None if it never sent one."""
    report = caps.get_capability_report(host)
    if not report:
        return None
    facts = report.get("facts")
    return facts if isinstance(facts, dict) else None


def contract_version(host) -> Optional[int]:
    """Which fact contract this host speaks, or None.

    Worth carrying into findings: a fleet upgrades gradually, so comparing
    results across hosts can silently compare different contracts.
    """
    facts = coverage(host) or {}
    version = facts.get("contract_version")
    return version if isinstance(version, int) else None


def table_state(host, table: str) -> Tuple[str, Optional[str]]:
    """``(state, detail)`` for one contract table on one host.

    ``detail`` is the provider for SERVED, the agent's own reason code for
    NOT_APPLICABLE and UNSUPPORTED, and None for UNKNOWN. The agent's code is
    passed through rather than reworded: "wrong_platform" and
    "insufficient_privilege" send an operator to different places, and a
    generic "unavailable" sends them to neither.
    """
    facts = coverage(host)
    if not facts:
        return UNKNOWN, None
    served = facts.get("served") or {}
    if table in served:
        return SERVED, served[table]
    not_applicable = facts.get("not_applicable") or {}
    if table in not_applicable:
        return NOT_APPLICABLE, not_applicable[table]
    unsupported = facts.get("unsupported") or {}
    if table in unsupported:
        return UNSUPPORTED, unsupported[table]
    # Advertised, but this table is in none of the three buckets. That should
    # be impossible -- build_fact_coverage puts every contract table in
    # exactly one -- so it means the host speaks a contract this server does
    # not know, which is UNKNOWN rather than a denial.
    return UNKNOWN, None


def answerable(host, table: str) -> bool:
    """Can a finding about ``table`` be built for this host?

    True for SERVED and for UNKNOWN. Unknown proceeds because an agent that
    has not upgraded must keep behaving exactly as it did before this slice.
    """
    state, _detail = table_state(host, table)
    return state not in NOT_ANSWERABLE


def serves(host, table: str) -> bool:
    """Is this host KNOWN to serve ``table``? True only for SERVED.

    THE DIFFERENCE FROM ``answerable`` -- and picking the wrong one is a live
    defect, not a style choice.

    ``answerable`` lets UNKNOWN through because a consumer that EXISTED before
    21.1 must keep working against agents that have not upgraded: reading "never
    advertised" as "cannot answer" would switch that consumer off for the whole
    estate on upgrade day.

    A consumer that is BRAND NEW has no such legacy to protect, and the
    permissive reading inverts into the very defect this phase exists to
    prevent. Comparing a new fact table across two hosts that never advertised
    it finds zero rows on each side and reports them identical -- a fabricated
    all-clear, produced by a feature that has never once run. Such a consumer
    must require a POSITIVE advertisement.

    Rule of thumb: ``answerable`` to keep old behavior, ``serves`` to gate new
    behavior.
    """
    state, _detail = table_state(host, table)
    return state == SERVED


def why_not_served(host, table: str) -> Optional[Dict[str, str]]:
    """Why ``serves`` said no, or None when it said yes.

    Same shape as ``explain``, but it also reports UNKNOWN -- which ``explain``
    deliberately does not, because for the pre-existing consumers UNKNOWN is
    not a denial. Here it is the commonest answer: an agent too old to know the
    table exists.
    """
    state, detail = table_state(host, table)
    if state == SERVED:
        return None
    return {"table": table, "state": state, "reason": detail or state}


def explain(host, table: str) -> Optional[Dict[str, str]]:
    """Why this host cannot answer, or None when it can.

    Shaped for a consumer to attach verbatim to a result, so every surface
    reports the same reason in the same words rather than inventing its own.
    """
    state, detail = table_state(host, table)
    if state not in NOT_ANSWERABLE:
        return None
    return {"table": table, "state": state, "reason": detail or state}


def advertised_columns(host, table: str) -> Optional[Tuple[str, ...]]:
    """The columns this host says it FILLS for ``table``, or None.

    None when the table is not served, or when the agent predates the column
    advertisement (21.2 S1). Coverage used to be per table only, and native
    ``mounts`` served the table while filling none of its capacity columns --
    so a question about disk usage "succeeded" against NULLs.
    """
    if not serves(host, table):
        return None
    columns = (coverage(host) or {}).get("columns")
    if not isinstance(columns, dict) or not isinstance(columns.get(table), list):
        return None
    return tuple(columns[table])


def missing_columns(host, table: str, needed) -> Optional[Dict[str, Any]]:
    """Why ``host`` cannot answer a question that reads ``needed`` columns of
    ``table``, or None when it can.

    For NEW consumers only -- same rule as ``serves``: an agent that never
    advertised its columns is a gap, not "all of them", because reading it the
    permissive way is exactly how the capacity rule evaluated NULLs as "fine".
    """
    reason = why_not_served(host, table)
    if reason is not None:
        return reason
    filled = advertised_columns(host, table)
    if filled is None:
        return {"table": table, "state": UNKNOWN, "reason": "columns_not_advertised"}
    missing = sorted(set(needed or ()) - set(filled))
    if missing:
        return {
            "table": table,
            "state": SERVED,
            "reason": "columns_not_populated",
            "columns": missing,
        }
    return None


def missing_tables(host, tables) -> Dict[str, Dict[str, str]]:
    """``{table: explanation}`` for each requested table the host cannot answer."""
    out = {}
    for table in tables or ():
        reason = explain(host, table)
        if reason is not None:
            out[table] = reason
    return out
