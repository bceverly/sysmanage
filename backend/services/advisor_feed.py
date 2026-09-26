# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The advisor's rule catalog, recommendation feed and host view (ROADMAP 21.2 S4).

Reads ``advisor_result`` rows and the rules behind them, and shapes them for
the API. Decisions -- validation, scores, remediation text -- come from the
licensed ``advisor_engine``, passed in as ``engine``.

NOT ASSESSABLE IS ITS OWN COLUMN, EVERYWHERE
--------------------------------------------
Every shape here carries the unassessable count or list BESIDE the findings,
never folded into "no recommendations": a feed that shows three findings and
hides that forty host/rule pairs could not be evaluated reads as a fleet in
good shape. Same rule the Recent Runs screen follows for *Not covered* beside
*Failed*.
"""

from typing import Any, Dict, List, Optional, Tuple

from backend.persistence import models
from backend.services import advisor_scoring as scoring
from backend.services import advisor_tick as tick

FIRES = models.ADVISOR_OUTCOME_FIRES
NOT_ASSESSABLE = models.ADVISOR_OUTCOME_NOT_ASSESSABLE
NOT_APPLICABLE = models.ADVISOR_OUTCOME_NOT_APPLICABLE
DOES_NOT_FIRE = models.ADVISOR_OUTCOME_DOES_NOT_FIRE


# ---------------------------------------------------------------------------
# rules
# ---------------------------------------------------------------------------


def rule_dict(engine, source: str, rule: Dict[str, Any], **extra) -> Dict[str, Any]:
    """A rule as the API shows it, with its validation problems (codes)."""
    return {
        "source": source,
        "key": rule.get("id"),
        "title": rule.get("title"),
        "lens": rule.get("lens"),
        "scope": rule.get("scope", "host"),
        "impact": rule.get("impact"),
        "likelihood": rule.get("likelihood"),
        "definition": rule,
        "errors": list(engine.validate_rule(rule)),
        **extra,
    }


def all_rules(engine, db) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """``{(source, key): rule_dict}`` for every rule the tick evaluates.

    Curated rules come from the shared catalog; when it cannot be read they
    are simply absent here -- the results they left still show, keyed, and
    the feed marks them ``rule: null`` rather than inventing a title.
    """
    rules = {}
    for entry in tick.load_shared_rules() or []:
        rules[(entry["source"], entry["key"])] = rule_dict(
            engine, entry["source"], entry["rule"], id=str(entry["shared_rule_id"])
        )
    for row in db.query(models.AdvisorRule).all():
        rule = dict(row.definition or {}, id=row.rule_key)
        rules[(models.ADVISOR_RULE_SOURCE_TENANT, row.rule_key)] = rule_dict(
            engine,
            models.ADVISOR_RULE_SOURCE_TENANT,
            rule,
            id=str(row.id),
            enabled=row.enabled,
            created_by=row.created_by,
        )
    return rules


def _key_of(row) -> Tuple[str, str]:
    return (row.rule_source, row.rule_key)


# ---------------------------------------------------------------------------
# the fleet feed
# ---------------------------------------------------------------------------


def _empty_entry(key, rule) -> Dict[str, Any]:
    return {
        "source": key[0],
        "key": key[1],
        "rule": rule,
        "risk": None,
        "hosts_firing": 0,
        "hosts_not_assessable": 0,
        "hosts_not_applicable": 0,
        "hosts_clean": 0,
        "gap_reasons": {},
    }


def feed(engine, db, lens: Optional[str] = None) -> Dict[str, Any]:
    """One entry per rule, worst first, plus the fleet score.

    Order: rules that fire, by risk then by how many hosts; then rules that
    fire nowhere but could not be assessed somewhere (a blind spot is worth
    seeing); then the rest.
    """
    rules = all_rules(engine, db)
    entries: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in db.query(models.AdvisorResult).all():
        key = _key_of(row)
        rule = rules.get(key)
        if lens and (row.lens or (rule or {}).get("lens")) != lens:
            continue
        entry = entries.setdefault(key, _empty_entry(key, rule))
        if row.outcome == FIRES:
            entry["hosts_firing"] += 1
            if row.risk is not None:
                entry["risk"] = max(entry["risk"] or 0, row.risk)
        elif row.outcome == NOT_ASSESSABLE:
            entry["hosts_not_assessable"] += 1
            for gap in row.gaps or []:
                reason = (gap or {}).get("reason") or "unknown"
                entry["gap_reasons"][reason] = entry["gap_reasons"].get(reason, 0) + 1
        elif row.outcome == NOT_APPLICABLE:
            entry["hosts_not_applicable"] += 1
        else:
            entry["hosts_clean"] += 1
    ordered = sorted(
        entries.values(),
        key=lambda e: (
            0 if e["hosts_firing"] else 1 if e["hosts_not_assessable"] else 2,
            -(e["risk"] or 0),
            -e["hosts_firing"],
            -e["hosts_not_assessable"],
            e["key"],
        ),
    )
    return {
        "fleet": scoring.fleet_score(engine, db),
        "totals": {
            "findings": sum(e["hosts_firing"] for e in ordered),
            "not_assessable": sum(e["hosts_not_assessable"] for e in ordered),
            "not_applicable": sum(e["hosts_not_applicable"] for e in ordered),
            "clean": sum(e["hosts_clean"] for e in ordered),
        },
        "rules": ordered,
    }


# ---------------------------------------------------------------------------
# one host
# ---------------------------------------------------------------------------


def _result_dict(engine, row, rule) -> Dict[str, Any]:
    out = {
        "source": row.rule_source,
        "key": row.rule_key,
        "title": (rule or {}).get("title"),
        "lens": row.lens,
        "outcome": row.outcome,
        "impact": row.impact,
        "likelihood": row.likelihood,
        "risk": row.risk,
        "evaluated_at": row.evaluated_at.isoformat() if row.evaluated_at else None,
    }
    if row.outcome == FIRES:
        out["match_count"] = row.match_count
        out["matches"] = row.matches or []
        definition = (rule or {}).get("definition")
        out["remediation"] = (
            list(engine.render_remediation(definition, row.matches or []))
            if definition
            else []
        )
    elif row.outcome in (NOT_ASSESSABLE, NOT_APPLICABLE):
        out["gaps"] = row.gaps or []
    return out


def host_view(engine, db, host) -> Dict[str, Any]:
    """A host's score and every outcome, grouped -- the unassessable ones as
    their own list, never hidden behind "no findings"."""
    rules = all_rules(engine, db)
    rows = (
        db.query(models.AdvisorResult)
        .filter(models.AdvisorResult.host_id == host.id)
        .all()
    )
    grouped: Dict[str, List[Dict[str, Any]]] = {
        FIRES: [],
        NOT_ASSESSABLE: [],
        NOT_APPLICABLE: [],
        DOES_NOT_FIRE: [],
    }
    for row in rows:
        grouped.setdefault(row.outcome, []).append(
            _result_dict(engine, row, rules.get(_key_of(row)))
        )
    # S5: each finding's latest proposed fix, if its rule has one.
    latest: Dict[Tuple[str, str], Any] = {}
    for proposal in (
        db.query(models.AdvisorProposal)
        .filter(models.AdvisorProposal.host_id == host.id)
        .order_by(models.AdvisorProposal.created_at)
        .all()
    ):
        latest[(proposal.rule_source, proposal.rule_key)] = proposal
    for finding in grouped[FIRES]:
        proposal = latest.get((finding["source"], finding["key"]))
        finding["proposal"] = (
            {"id": str(proposal.id), "status": proposal.status, "kind": proposal.kind}
            if proposal is not None
            else None
        )
    grouped[FIRES].sort(key=lambda r: (-(r["risk"] or 0), r["key"]))
    for outcome in (NOT_ASSESSABLE, NOT_APPLICABLE, DOES_NOT_FIRE):
        grouped[outcome].sort(key=lambda r: r["key"])
    return {
        "host_id": str(host.id),
        "fqdn": host.fqdn,
        "score": scoring.host_score(engine, db, host.id),
        "findings": grouped[FIRES],
        "not_assessable": grouped[NOT_ASSESSABLE],
        "not_applicable": grouped[NOT_APPLICABLE],
        "clean": grouped[DOES_NOT_FIRE],
    }


# ---------------------------------------------------------------------------
# one rule
# ---------------------------------------------------------------------------


def rule_hosts(
    engine, db, source: str, key: str, outcome: Optional[str] = None
) -> Dict[str, Any]:
    """Which hosts a rule fires on (or cannot be assessed on, etc.)."""
    rule = all_rules(engine, db).get((source, key))
    query = (
        db.query(models.AdvisorResult, models.Host.fqdn)
        .join(models.Host, models.Host.id == models.AdvisorResult.host_id)
        .filter(
            models.AdvisorResult.rule_source == source,
            models.AdvisorResult.rule_key == key,
        )
    )
    if outcome:
        query = query.filter(models.AdvisorResult.outcome == outcome)
    hosts = []
    for row, fqdn in query.all():
        entry = _result_dict(engine, row, rule)
        entry["host_id"] = str(row.host_id)
        entry["fqdn"] = fqdn
        hosts.append(entry)
    hosts.sort(key=lambda h: (-(h["risk"] or 0), h["fqdn"] or ""))
    return {"rule": rule, "hosts": hosts}
