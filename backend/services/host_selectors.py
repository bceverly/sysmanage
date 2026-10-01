# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Which active hosts a set of selectors names right now.

Lifted out of ``config_mgmt_fleet.resolve_hosts`` (2026-10-01) so malware scan
jobs target fleets the same way configuration inventories do: by hosts, tags
and sites, resolved at launch and never copied -- a copied list is wrong the
moment a host joins a tag, and wrong silently.
"""

from typing import Any, Iterable, List

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.persistence import models


def hosts_for_selectors(
    db_session: Session,
    all_hosts: bool = False,
    host_ids: Iterable[Any] = (),
    tag_ids: Iterable[Any] = (),
    site_ids: Iterable[Any] = (),
) -> List[Any]:
    """The ACTIVE hosts the selectors name (each host once).

    Inactive hosts are excluded: queuing work for one buries it in a queue
    that may never drain while the operator sees it as dispatched.
    """
    query = db_session.query(models.Host).filter(models.Host.active.is_(True))
    if all_hosts:
        return query.all()
    host_ids, tag_ids, site_ids = list(host_ids), list(tag_ids), list(site_ids)
    if not (host_ids or tag_ids or site_ids):
        return []

    clauses = []
    if host_ids:
        clauses.append(models.Host.id.in_(host_ids))
    if site_ids:
        clauses.append(models.Host.site_id.in_(site_ids))
    if tag_ids:
        # A subquery rather than a join: joining HostTag multiplies a host by
        # its matching tags, so a host carrying two of the selected tags would
        # become two targets and be dispatched to twice.
        tagged = (
            db_session.query(models.HostTag.host_id)
            .filter(models.HostTag.tag_id.in_(tag_ids))
            .subquery()
        )
        clauses.append(models.Host.id.in_(db_session.query(tagged.c.host_id)))

    return query.filter(or_(*clauses)).all()
