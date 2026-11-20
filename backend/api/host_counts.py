# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Host counts answered by the database, not by loading rows (Phase 22.7)."""

import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy import case, func
from sqlalchemy.orm import sessionmaker

from backend.services import disk_space
from backend.auth.auth_bearer import JWTBearer
from backend.persistence import db, models

router = APIRouter()

NO_UPDATES = (0, 0, 0)


def update_counts_by_host(session, host_ids=None) -> dict:
    """``{host_id: (security, system, total)}`` pending updates, counted in
    the database with one grouped query.

    Phase 22.7: the host list loaded every host's update rows one host at a
    time to count them -- at 20,000 hosts with 25 updates each, 20,000
    queries and 500,000 rows, 36 seconds per call, polled by the dashboard
    every 30 seconds.  It also counted ``is_security_update`` /
    ``is_system_update``, attributes the model does not have, so both counts
    were always 0; the type is ``update_type`` ("security", "system"), as the
    updates summary counts it.  ``host_ids`` limits the query; None counts
    every host."""
    update = models.PackageUpdate
    query = session.query(
        update.host_id,
        func.sum(case((update.update_type == "security", 1), else_=0)),
        func.sum(case((update.update_type == "system", 1), else_=0)),
        func.count(update.id),
    )
    if host_ids is not None:
        query = query.filter(update.host_id.in_(host_ids))
    return {
        host_id: (int(security or 0), int(system or 0), int(total or 0))
        for host_id, security, system, total in query.group_by(update.host_id)
    }


def host_summary(session) -> dict:
    """The dashboard's host numbers in one aggregate query: how many hosts,
    how many approved, approved and up / down, and approved hosts that need a
    reboot."""
    host = models.Host
    approved = host.approval_status == "approved"
    row = session.query(
        func.count(host.id),
        func.sum(case((approved, 1), else_=0)),
        func.sum(case((approved & (host.status == "up"), 1), else_=0)),
        func.sum(case((approved & (host.status == "down"), 1), else_=0)),
        func.sum(case((approved & host.reboot_required.is_(True), 1), else_=0)),
    ).one()
    total, approved_n, up, down, reboot = (int(v or 0) for v in row)
    return {
        "total": total,
        "approved": approved_n,
        "approved_up": up,
        "approved_down": down,
        "reboot_required": reboot,
        **_repair_summary(session),
        # Nearly full disks (2026-11-20).
        **disk_space.summary(session),
    }


# How many hosts needing a repair the summary names (the rest are counted).
REPAIR_NAMED = 20


def _repair_summary(session) -> dict:
    """Approved hosts whose package manager needs repair, or that are not safe
    to reboot (2026-11-19): counted, and the first few named -- not-safe-to-
    reboot first -- so the dashboard and the Updates page can say which and
    offer the repair without loading the host list."""
    host = models.Host
    flagged = (host.approval_status == "approved") & (
        host.package_manager_needs_repair.is_(True) | host.reboot_unsafe.is_(True)
    )
    count, unsafe = (
        session.query(
            func.count(host.id),
            func.sum(case((host.reboot_unsafe.is_(True), 1), else_=0)),
        )
        .filter(flagged)
        .one()
    )
    rows = (
        session.query(host)
        .filter(flagged)
        .order_by(host.reboot_unsafe.desc(), host.fqdn)
        .limit(REPAIR_NAMED)
        .all()
    )
    return {
        "package_manager_repair": int(count or 0),
        "reboot_unsafe": int(unsafe or 0),
        "repair_hosts": [
            {
                "id": str(row.id),
                "fqdn": row.fqdn,
                "package_manager_needs_repair": bool(row.package_manager_needs_repair),
                "package_manager_repair_reason": row.package_manager_repair_reason,
                "package_manager_repairable": bool(row.package_manager_repairable),
                "reboot_unsafe": bool(row.reboot_unsafe),
                "reboot_unsafe_reason": row.reboot_unsafe_reason,
            }
            for row in rows
        ],
    }


def _host_summary_sync(tenant_id=None) -> dict:
    # pylint: disable-next=import-outside-toplevel
    from backend.persistence.partitions import get_request_engine

    bind = db.get_engine() if tenant_id is None else get_request_engine(tenant_id)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=bind)
    with session_local() as session:
        return host_summary(session)


@router.get("/hosts/summary", dependencies=[Depends(JWTBearer())])
async def get_hosts_summary():
    """Counts for the dashboard (Phase 22.7).  The dashboard fetched the
    whole host list -- 15 MB at 20,000 hosts -- every 30 seconds to show
    three numbers."""
    # The active tenant is a ContextVar: read it here, not in the thread.
    # pylint: disable-next=import-outside-toplevel
    from backend.persistence.tenant_context import get_active_tenant

    return await asyncio.to_thread(_host_summary_sync, get_active_tenant())
