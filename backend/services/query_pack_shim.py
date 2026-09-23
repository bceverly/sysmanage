# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Delegate query-pack policy decisions to the licensed engine (Phase 21.1 S4).

The fact SUBSTRATE is open-source -- every agent serves the osquery-schema
tables, because better inventory drives adoption. Turning those tables into
POLICY is the Professional half: authoring packs, assigning them per
host/tag/site, pacing collection, and grading what comes back. That lives in
``query_pack_engine``; this is the thin shim, shaped like
``config_mgmt_spec_shim``.

WHY EVERY HELPER FAILS CLOSED
-----------------------------
An absent engine must never mean "no rules applied". Validation returning
"fine" because the module did not load would accept tenant-authored SQL that
nobody checked and hand it to a fleet -- so ``validate_pack`` REFUSES when the
engine is missing, and ``resolve_assignments`` returns nothing rather than
guessing. A licensed server with a broken module is a loud, fixable install
problem; a quietly permissive one is not.

The caller has already established the license permits this engine (see
``feature_gate.require_module_loaded`` on the router), so a missing module
here means the artefact is absent or failed to load -- never that the customer
is unlicensed.
"""

import logging
from typing import Any, Dict, List, Optional

from backend.licensing.module_loader import module_loader

logger = logging.getLogger(__name__)

ENGINE_CODE = "query_pack_engine"

# Mirrors the engine's own floor. Duplicated deliberately and narrowly: the
# UI needs a number to show before any engine call, and a wrong hint is a
# cosmetic annoyance where a wrong ENFORCEMENT would be a real defect -- which
# is why the engine, not this constant, is what actually refuses.
MIN_INTERVAL_MINUTES = 5
DEFAULT_INTERVAL_MINUTES = 60
DEFAULT_LIVE_TIMEOUT_SECONDS = 120

# What concurrency to allow when the engine cannot be reached. ONE, not the
# operator's requested value: a server that has lost the engine mid-query must
# not honor "500 at once". It is deliberately not zero, because zero would
# stall a query that is already running rather than let it drain slowly.
FALLBACK_CONCURRENCY = 1


def _engine():
    """The loaded engine, or None."""
    engine = module_loader.get_module(ENGINE_CODE)
    if engine is None:
        logger.warning(
            "Module '%s' is licensed but not loaded; query-pack policy is "
            "unavailable on this server",
            ENGINE_CODE,
        )
    return engine


def engine_available() -> bool:
    """Is the engine loaded? For the API's 503-vs-403 distinction."""
    return module_loader.get_module(ENGINE_CODE) is not None


def validate_pack(pack: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a pack definition. FAILS CLOSED when the engine is absent."""
    engine = _engine()
    if engine is None:
        return {
            "valid": False,
            "problems": ["query pack validation is unavailable on this server"],
        }
    try:
        return engine.validate_pack(pack)
    except Exception:  # pylint: disable=broad-except
        logger.exception("query_pack_engine raised while validating a pack")
        return {"valid": False, "problems": ["the pack could not be validated"]}


def resolve_assignments(
    host: Dict[str, Any], assignments: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Which packs this host runs. Empty when the engine is absent."""
    engine = _engine()
    if engine is None:
        return []
    try:
        return engine.resolve_assignments(host, assignments)
    except Exception:  # pylint: disable=broad-except
        logger.exception("query_pack_engine raised while resolving assignments")
        return []


def select_due(candidates: List[Dict[str, Any]], now, limit: int = 50):
    """The assignments to dispatch this tick. Empty when the engine is absent."""
    engine = _engine()
    if engine is None:
        return []
    try:
        return engine.select_due(candidates, now, limit=limit)
    except Exception:  # pylint: disable=broad-except
        logger.exception("query_pack_engine raised while selecting due work")
        return []


def build_dispatch(
    pack: Dict[str, Any],
    queries: List[Dict[str, Any]],
    coverage: Optional[Dict[str, Any]],
    platform: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """The payload for one pack run, or None when the engine is absent.

    ``None`` rather than an unfiltered payload on purpose: dispatching every
    query without the coverage check would send hosts questions they cannot
    answer, and those come back as ERRORS -- a different and worse claim than
    "this host does not serve those tables".
    """
    engine = _engine()
    if engine is None:
        return None
    try:
        return engine.build_dispatch(pack, queries, coverage, platform)
    except Exception:  # pylint: disable=broad-except
        logger.exception("query_pack_engine raised while building a dispatch")
        return None


# ---------------------------------------------------------------------------
# S5 -- live query bounds
# ---------------------------------------------------------------------------


def clamp_concurrency(value: Any) -> int:
    """How many targets may be in flight. Falls back to a SAFE floor."""
    engine = _engine()
    if engine is None:
        return FALLBACK_CONCURRENCY
    try:
        return int(engine.clamp_concurrency(value))
    except Exception:  # pylint: disable=broad-except
        logger.exception("query_pack_engine raised while clamping concurrency")
        return FALLBACK_CONCURRENCY


def clamp_timeout(value: Any) -> int:
    """Per-host timeout in seconds."""
    engine = _engine()
    if engine is None:
        return DEFAULT_LIVE_TIMEOUT_SECONDS
    try:
        return int(engine.clamp_timeout(value))
    except Exception:  # pylint: disable=broad-except
        logger.exception("query_pack_engine raised while clamping the timeout")
        return DEFAULT_LIVE_TIMEOUT_SECONDS


def next_batch_size(concurrency: int, in_flight: int, waiting: int) -> int:
    """How many more targets may be released right now.

    ZERO without the engine, not "all of them". A server that has lost its
    license mid-query must stop dispatching rather than fall back to the
    unbounded behavior this slice exists to prevent -- the same rule the
    fleet-job shim follows.
    """
    engine = _engine()
    if engine is None:
        return 0
    try:
        return int(engine.next_batch_size(concurrency, in_flight, waiting))
    except Exception:  # pylint: disable=broad-except
        logger.exception("query_pack_engine raised while sizing a wave")
        return 0


def validate_live_query(sql: str, required_tables=None) -> List[str]:
    """Problems with an ad-hoc statement. FAILS CLOSED without the engine."""
    engine = _engine()
    if engine is None:
        return ["live queries are unavailable on this server"]
    try:
        return list(engine.validate_live_query(sql, required_tables))
    except Exception:  # pylint: disable=broad-except
        logger.exception("query_pack_engine raised while validating a live query")
        return ["the query could not be validated"]


def live_status_after(total: int, finished: int) -> str:
    """The live query's status given how many targets have settled."""
    engine = _engine()
    if engine is None:
        return "running"
    try:
        return str(engine.live_status_after(total, finished))
    except Exception:  # pylint: disable=broad-except
        logger.exception("query_pack_engine raised while grading a live query")
        return "running"


def grade_run(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Grade one run's per-query outcomes.

    The ONE helper that degrades rather than refusing, because it runs on the
    INGEST path: results have already been collected on a real host, and
    dropping them because a module is missing would lose measurements that
    cannot be taken again. The fallback keeps the safety property by hand --
    anything not ``ok`` leaves the run ``partial``, never ``success``.
    """
    engine = _engine()
    if engine is not None:
        try:
            return engine.grade_run(results)
        except Exception:  # pylint: disable=broad-except
            logger.exception("query_pack_engine raised while grading a run")

    total = len(results or [])
    ok = sum(1 for r in results or [] if (r or {}).get("status") == "ok")
    not_covered = sum(
        1 for r in results or [] if (r or {}).get("status") == "not_covered"
    )
    failed = total - ok - not_covered
    if total == 0:
        status = "partial"
    elif failed == total:
        status = "failed"
    elif failed or not_covered:
        status = "partial"
    else:
        status = "success"
    return {
        "status": status,
        "queries_total": total,
        "queries_ok": ok,
        "queries_not_covered": not_covered,
        "queries_failed": failed,
    }
