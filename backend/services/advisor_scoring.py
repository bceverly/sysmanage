# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Host and fleet advisor risk, from stored outcomes (ROADMAP 21.2 S3).

The licensed ``advisor_engine`` owns the scoring (``score_host`` /
``score_fleet``): a finding's risk is impact x likelihood, a host's score is
its worst finding, and a score is WITHHELD -- None, level ``UNKNOWN`` -- from
any host that could not be assessed. This module reads the ``advisor_result``
rows and hands them over.

THE HOSTS WITH NO ROWS
----------------------
An approved host the advisor has not evaluated yet has no rows at all. It is
still a host in the fleet, so it is scored -- as UNKNOWN -- rather than left
out: dropping it would shrink the denominator exactly the way averaging
blind spots in as zero inflates it, and the fleet would look fully assessed
when it is not.
"""

from typing import Any, Dict, Iterable, List, Optional

from backend.persistence import models


def _results(rows: Iterable[Any]) -> List[Dict[str, Any]]:
    return [{"outcome": r.outcome, "risk": r.risk} for r in rows]


def host_score(engine, db, host_id) -> Dict[str, Any]:
    """One host's grade, plus when it was last evaluated (None: never)."""
    rows = (
        db.query(models.AdvisorResult)
        .filter(models.AdvisorResult.host_id == host_id)
        .all()
    )
    score = dict(engine.score_host(_results(rows)))
    score["evaluated_at"] = max((r.evaluated_at for r in rows), default=None)
    return score


def fleet_score(engine, db, host_ids: Optional[Iterable[Any]] = None) -> Dict[str, Any]:
    """The fleet rollup over every approved host (or ``host_ids``)."""
    query = db.query(models.Host.id).filter(models.Host.approval_status == "approved")
    if host_ids is not None:
        query = query.filter(models.Host.id.in_(list(host_ids)))
    hosts = [str(host_id) for (host_id,) in query.all()]
    by_host: Dict[str, List[Any]] = {host: [] for host in hosts}
    if hosts:
        for row in (
            db.query(models.AdvisorResult)
            .filter(models.AdvisorResult.host_id.in_(hosts))
            .all()
        ):
            by_host[str(row.host_id)].append(row)
    return engine.score_fleet(
        [engine.score_host(_results(rows)) for rows in by_host.values()]
    )
