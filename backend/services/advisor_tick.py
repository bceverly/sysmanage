# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Periodic advisor evaluation: rules x hosts -> outcomes (ROADMAP 21.2 S2).

Every tick, in every database: load the rules (curated ones from the shared
catalog, the tenant's own), gather each approved host's evidence
(``advisor_evidence``), let the licensed ``advisor_engine`` decide one outcome
per (host, rule), and store it as one ``advisor_result`` row.

WHAT IT GUARANTEES
------------------
* Every evaluated (host, rule) pair gets a row -- including not_assessable
  with its gaps. Nothing is dropped, because a missing row would read as
  "does not fire" to anything that lists findings.
* A host whose evidence could not even be GATHERED keeps its previous rows
  (with their older ``evaluated_at``) and the failure is logged with the host
  and tenant. Overwriting them with nothing would be the silent all-clear.
* Results for a rule that is gone -- deleted, disabled, or its pack
  deprecated -- are removed, so the feed never shows an outcome of a rule
  that no longer exists.

WHAT IT DOES NOT DO (S2 is evaluation only)
-------------------------------------------
No scoring (S3), no feed or API (S4), no remediation (S5), no fact collection:
fact rows are read from ``advisor.<table>`` query-pack results, which nothing
dispatches yet, so fact rules are ``not_collected`` until that lands.

Unlicensed servers never get here: without ``advisor_engine`` the tick is not
started, and ``run_one_tick`` re-checks.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.partitions import (
    PARTITION_SHARED,
    iter_host_databases,
    partition_session,
)
from backend.services import advisor_evidence as ev

logger = logging.getLogger(__name__)

# Evidence moves on the scale of hours (the tightest freshness default is a
# day for facts); re-evaluating every host more often than this is churn.
TICK_INTERVAL_SECONDS = 15 * 60
ERROR_BACKOFF_SECONDS = 60

SHARED = models.ADVISOR_RULE_SOURCE_SHARED
TENANT = models.ADVISOR_RULE_SOURCE_TENANT


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _definition(row) -> Dict[str, Any]:
    """The rule as the engine takes it; the stored key wins over the JSON."""
    rule = dict(row.definition or {})
    rule["id"] = row.rule_key
    return rule


def load_shared_rules() -> Optional[List[Dict[str, Any]]]:
    """Curated rules from non-deprecated packs, as
    ``{"source", "key", "shared_rule_id", "rule_id", "rule"}``.

    None (not ``[]``) when the catalog could not be read: the tick then keeps
    the previous curated results, with their older ``evaluated_at``, instead
    of pruning them as if every curated rule had been withdrawn.
    """
    try:
        with partition_session(PARTITION_SHARED) as shared:
            rows = (
                shared.query(models.SharedAdvisorRule)
                .join(
                    models.SharedAdvisorRulePack,
                    models.SharedAdvisorRulePack.id
                    == models.SharedAdvisorRule.shared_pack_id,
                )
                .filter(models.SharedAdvisorRulePack.deprecated.is_(False))
                .all()
            )
            return [
                {
                    "source": SHARED,
                    "key": row.rule_key,
                    "shared_rule_id": row.id,
                    "rule_id": None,
                    "rule": _definition(row),
                }
                for row in rows
            ]
    except Exception:  # pylint: disable=broad-except
        logger.exception(
            "Advisor tick: the shared rule catalog could not be read; curated "
            "rules are not evaluated this pass"
        )
        return None


def _tenant_rules(db_session) -> List[Dict[str, Any]]:
    rows = (
        db_session.query(models.AdvisorRule)
        .filter(models.AdvisorRule.enabled.is_(True))
        .all()
    )
    return [
        {
            "source": TENANT,
            "key": row.rule_key,
            "shared_rule_id": None,
            "rule_id": row.id,
            "rule": _definition(row),
        }
        for row in rows
    ]


def _tag_ids(db_session, host) -> List[str]:
    return [
        str(row.tag_id)
        for row in db_session.query(models.HostTag)
        .filter(models.HostTag.host_id == host.id)
        .all()
    ]


@dataclass
class _Pass:
    """One database's evaluation: what every step below needs."""

    engine: Any
    db: Any
    label: str
    now: datetime
    summary: Dict[str, Any]
    existing: Dict[Tuple[str, str, str], Any] = field(default_factory=dict)

    def store(self, host_id, entry, result) -> None:
        """Upsert one (host, rule) outcome."""
        key = (str(host_id), entry["source"], entry["key"])
        row = self.existing.get(key)
        if row is None:
            row = models.AdvisorResult(
                host_id=host_id, rule_source=entry["source"], rule_key=entry["key"]
            )
            self.db.add(row)
            self.existing[key] = row
        row.shared_rule_id = entry["shared_rule_id"]
        row.rule_id = entry["rule_id"]
        row.rule_version = result.get("rule_version")
        row.lens = result.get("lens")
        row.outcome = result["outcome"]
        row.gaps = result.get("gaps") or []
        row.match_count = result.get("match_count") or 0
        row.matches = result.get("matches") or []
        row.evaluated_at = self.now
        self.summary["results"] += 1

    def prune(self, active_keys) -> None:
        """Drop outcomes of rules that are no longer in this database's rule set."""
        for key, row in list(self.existing.items()):
            if (key[1], key[2]) not in active_keys:
                self.db.delete(row)
                del self.existing[key]
                self.summary["pruned"] += 1


def _evaluate_hosts(run: _Pass, hosts, entries) -> List[Tuple[Any, Any, List, List]]:
    """Host-scope rules, host by host. Returns ``(host, evidence, packages,
    tag_ids)`` for every host that was evaluated -- the fleet rules' input."""
    rules = [e["rule"] for e in entries]
    fact_needs, domains = ev.required(rules)
    if any(r.get("scope") == "fleet" for r in rules):
        domains.add("packages")  # fleet rules compare inventories
    # Results come back one per host-scope rule, IN ORDER. Matched by position,
    # not by key: a tenant may write a rule whose key a curated rule also uses,
    # and keyed matching would file one rule's outcome under the other.
    host_entries = [e for e in entries if e["rule"].get("scope", "host") == "host"]
    evaluated = []
    for host in hosts:
        try:
            evidence, tables = ev.gather(run.db, host, fact_needs, domains)
            results = run.engine.evaluate_host(rules, evidence, tables, now=run.now)
        except Exception:  # pylint: disable=broad-except
            # Previous outcomes stay; see "WHAT IT GUARANTEES".
            logger.exception(
                "Advisor tick (%s): could not evaluate host %s (%s); its "
                "previous results are kept",
                run.label,
                host.id,
                host.fqdn,
            )
            run.summary["host_errors"] += 1
            continue
        evaluated.append(
            (host, evidence, tables.get("sm_package") or [], _tag_ids(run.db, host))
        )
        if len(results) != len(host_entries):
            logger.error(
                "Advisor tick (%s): engine returned %d results for %d rules on "
                "host %s; nothing stored for it this pass",
                run.label,
                len(results),
                len(host_entries),
                host.id,
            )
            run.summary["host_errors"] += 1
            continue
        for entry, result in zip(host_entries, results):
            run.store(host.id, entry, result)
    return evaluated


def _evaluate_fleet_rules(run: _Pass, entries, evaluated) -> None:
    for entry in entries:
        rule = entry["rule"]
        if rule.get("scope") != "fleet":
            continue
        hosts = [
            {
                "host_id": str(host.id),
                "evidence": evidence,
                "peer": ev.peer_value(host, rule.get("peer_group"), tag_ids),
                "packages": packages,
            }
            for host, evidence, packages, tag_ids in evaluated
        ]
        try:
            outcomes = run.engine.evaluate_fleet(rule, hosts, now=run.now)
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                "Advisor tick (%s): fleet rule %s failed to evaluate",
                run.label,
                entry["key"],
            )
            run.summary["rule_errors"] += 1
            continue
        for host, *_rest in evaluated:
            result = outcomes.get(str(host.id))
            if result is not None:
                run.store(host.id, entry, result)


def _tick_one_database(run: _Pass, shared_entries) -> None:
    """Evaluate ONE database. Never raises -- one unreachable tenant must not
    stop every other tenant's evaluation."""
    try:
        entries = list(shared_entries or []) + _tenant_rules(run.db)
        run.existing = {
            (str(r.host_id), r.rule_source, r.rule_key): r
            for r in run.db.query(models.AdvisorResult).all()
        }
        active = {(e["source"], e["key"]) for e in entries}
        if shared_entries is None:
            # The catalog could not be READ: its rules still exist, so their
            # results must not be pruned as if they had been withdrawn.
            active |= {(k[1], k[2]) for k in run.existing if k[1] == SHARED}
        run.prune(active)
        if entries:
            # Every APPROVED host, up or down. ``active`` is heartbeat liveness:
            # skipping down hosts would leave their last outcome standing
            # forever, a week-old "does not fire" reading as current. Evaluated
            # instead, their evidence ages into ``stale`` on its own.
            hosts = (
                run.db.query(models.Host)
                .filter(models.Host.approval_status == "approved")
                .all()
            )
            evaluated = _evaluate_hosts(run, hosts, entries)
            _evaluate_fleet_rules(run, entries, evaluated)
            run.summary["hosts"] += len(evaluated)
        run.db.commit()
    except Exception:  # pylint: disable=broad-except
        logger.exception("Advisor tick failed for %s", run.label)
        run.db.rollback()


def run_one_tick() -> Dict[str, Any]:
    """Evaluate every database once. Never raises.

    Public so an operator endpoint or a test can drive exactly one tick.
    """
    summary: Dict[str, Any] = {
        "hosts": 0,
        "results": 0,
        "pruned": 0,
        "host_errors": 0,
        "rule_errors": 0,
    }
    engine = module_loader.get_module("advisor_engine")
    if engine is None or not hasattr(engine, "evaluate_host"):
        # Not licensed, or an S1-era engine with the contract but no evaluator.
        return summary
    now = _now()
    shared_entries = load_shared_rules()
    # EVERY database: a tenant's hosts and rules live in that tenant's
    # database, so reading only the bootstrap one would evaluate nobody under
    # multi-tenancy and report a clean zero.
    for label, _tenant, db_session in iter_host_databases():
        try:
            run = _Pass(
                engine=engine, db=db_session, label=label, now=now, summary=summary
            )
            _tick_one_database(run, shared_entries)
        finally:
            db_session.close()
    return summary


async def advisor_tick_service() -> None:
    """Background service: one evaluation every ``TICK_INTERVAL_SECONDS``."""
    logger.info(
        "Starting advisor evaluation tick (interval=%ds)", TICK_INTERVAL_SECONDS
    )
    while True:
        try:
            summary = run_one_tick()
            if summary["results"] or summary["host_errors"]:
                logger.info(
                    "Advisor tick: hosts=%d results=%d pruned=%d host_errors=%d "
                    "rule_errors=%d",
                    summary["hosts"],
                    summary["results"],
                    summary["pruned"],
                    summary["host_errors"],
                    summary["rule_errors"],
                )
            await asyncio.sleep(TICK_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("Advisor tick service canceled -- exiting loop")
            raise
        except Exception:  # pylint: disable=broad-except
            logger.exception("Advisor tick service error -- sleeping then retrying")
            await asyncio.sleep(ERROR_BACKOFF_SECONDS)


# asyncio keeps only a WEAK reference to a task: without this one the loop
# could be garbage-collected mid-flight.
_TASK = None


def start_if_licensed():
    """Start the tick when ``advisor_engine`` is loaded; the task or None.

    Never fatal: a scheduler that will not start must not take the server
    with it. Called from startup, which is at its line budget -- the gate and
    the error handling live here rather than there.
    """
    global _TASK  # pylint: disable=global-statement
    if module_loader.get_module("advisor_engine") is None:
        return None
    if _TASK is not None and not _TASK.done():
        return _TASK  # lifespan ran twice (reload / test harness)
    try:
        _TASK = asyncio.create_task(advisor_tick_service())
        logger.info("Advisor evaluation tick started: %s", _TASK)
        return _TASK
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Failed to start the advisor evaluation tick: %s", exc)
        return None
