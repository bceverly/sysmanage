"""
Tenant data-mover — relocate per-tenant data from the bootstrap database into
each tenant's database (Phase 13.1 data plane).

The companion to the per-domain data-plane work: as each object (host,
packages, inventory, …) is routed to the tenant partition, its existing rows
must be carried from the bootstrap/legacy database into the correct tenant
database.  This is the **idempotent** engine for that — safe to run repeatedly
"along the way", and a ``verify`` step gates the eventual "burn the ships" drop
of the now-empty legacy tables.

How a row finds its tenant: every per-tenant object is ultimately rooted at a
host, and the host→tenant binding lives in the registry index
(``registry_host_tenant``).  Each domain declares how to get from a row to its
host id; the mover looks up that host's tenant and copies the row there.  Rows
whose tenant is unknown (an unenrolled/unassigned host) are LEFT in place —
they can't be placed yet, so they stay server-scoped until assigned.

**Adding a domain is one entry in ``DOMAINS``** — that's the whole extension
point as we migrate objects one by one.

Idempotent: a row already present in the target (by primary key) is skipped, so
re-running never duplicates.  With ``delete_source=True`` a moved row is removed
from the bootstrap DB, so the legacy table drains to empty as domains migrate.

No-op when multi-tenancy is disabled (single-database homelab: there is nowhere
to move data to).
"""

import logging
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)


@dataclass
class Domain:
    """One movable object: its model + how to find a row's host (→ tenant)."""

    name: str
    # Returns the model class (lazy — avoids import cycles at module load).
    model_factory: Callable
    # row -> host_id (the host this row belongs to).  For the host itself this
    # is identity; for host-rooted children it's the ``host_id`` column.
    host_id_of: Callable
    # Optional human note.
    note: str = field(default="")


def _host_model():
    from backend.persistence import models  # noqa: PLC0415

    return models.Host


# ---------------------------------------------------------------------------
# Domain registry — ADD ONE ENTRY PER OBJECT as it is routed to the tenant
# partition.  Order matters only loosely (the host should come first so its
# children's tenant resolves), but each row resolves its tenant independently.
# ---------------------------------------------------------------------------
DOMAINS: List[Domain] = [
    Domain(
        name="host",
        model_factory=_host_model,
        host_id_of=lambda row: row.id,
        note="the root object; every other per-tenant row hangs off a host",
    ),
    # e.g. when packages are routed:
    # Domain("package_update", lambda: models.PackageUpdate,
    #        host_id_of=lambda r: r.host_id),
]


def _is_multitenancy_enabled() -> bool:
    from backend.config import config  # noqa: PLC0415

    return config.is_multitenancy_enabled()


def _bootstrap_sessionmaker():
    from backend.persistence import db  # noqa: PLC0415

    return sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())


def _tenant_sessionmaker(tenant_id):
    from backend.persistence.partitions import get_request_engine  # noqa: PLC0415

    return sessionmaker(
        autocommit=False, autoflush=False, bind=get_request_engine(tenant_id)
    )


def _pk_value(row):
    """Single-column primary-key value (all these models use an ``id`` PK)."""
    return getattr(row, "id")


def _row_values(row) -> dict:
    """Column-name → value for every mapped column on ``row``."""
    mapper = sa_inspect(row).mapper
    return {col.key: getattr(row, col.key) for col in mapper.column_attrs}


def move_domain(domain: Domain, *, apply: bool, delete_source: bool) -> dict:
    """Move one domain's rows from the bootstrap DB to each row's tenant DB.

    Returns ``{moved, skipped_present, skipped_unassigned, errors}``.  When
    ``apply`` is False this is a dry run (counts only, no writes).
    """
    from backend.services.host_tenant_index import (  # noqa: PLC0415
        tenant_for_host,
    )

    model = domain.model_factory()
    result = {"moved": 0, "skipped_present": 0, "skipped_unassigned": 0, "errors": 0}

    src_local = _bootstrap_sessionmaker()
    src = src_local()
    try:
        rows = src.query(model).all()
        # Cache one target session per tenant.
        target_sessions = {}
        try:
            for row in rows:
                host_id = domain.host_id_of(row)
                tenant_id = tenant_for_host(host_id)
                if not tenant_id:
                    result["skipped_unassigned"] += 1
                    continue
                values = _row_values(row)
                pk = _pk_value(row)
                if not apply:
                    result["moved"] += 1
                    continue
                try:
                    tgt = target_sessions.get(tenant_id)
                    if tgt is None:
                        tgt = _tenant_sessionmaker(tenant_id)()
                        target_sessions[tenant_id] = tgt
                    if tgt.get(model, pk) is not None:
                        result["skipped_present"] += 1
                    else:
                        tgt.add(model(**values))
                        tgt.flush()
                        result["moved"] += 1
                    if delete_source:
                        src.delete(row)
                except Exception as exc:  # noqa: BLE001 - isolate per-row
                    result["errors"] += 1
                    logger.error(
                        "data-mover %s row %s failed: %s", domain.name, pk, exc
                    )
            if apply:
                for tgt in target_sessions.values():
                    tgt.commit()
                if delete_source:
                    src.commit()
        finally:
            for tgt in target_sessions.values():
                tgt.close()
    finally:
        src.close()
    return result


def move_all(*, apply: bool = False, delete_source: bool = False) -> dict:
    """Run every registered domain.  Returns ``{domain: result, ...}`` (plus a
    ``_enabled`` flag).  No-op (enabled False) when multi-tenancy is off."""
    if not _is_multitenancy_enabled():
        return {"_enabled": False}
    report = {"_enabled": True}
    for domain in DOMAINS:
        report[domain.name] = move_domain(
            domain, apply=apply, delete_source=delete_source
        )
    return report


def verify_source_drained() -> dict:
    """Report, per domain, how many rows REMAIN in the bootstrap DB.

    The "burn the ships" gate: a domain is safe to drop from the bootstrap DB
    only when ``remaining`` is 0 (every row moved to a tenant) — or when the
    only rows left belong to deliberately-unassigned hosts.  Returns
    ``{domain: {remaining, unassigned}}``.
    """
    from backend.services.host_tenant_index import (  # noqa: PLC0415
        tenant_for_host,
    )

    out = {}
    src_local = _bootstrap_sessionmaker()
    src = src_local()
    try:
        for domain in DOMAINS:
            model = domain.model_factory()
            rows = src.query(model).all()
            unassigned = sum(
                1 for r in rows if not tenant_for_host(domain.host_id_of(r))
            )
            out[domain.name] = {"remaining": len(rows), "unassigned": unassigned}
    finally:
        src.close()
    return out


def check() -> dict:
    """Dry-run report: how many rows each domain WOULD move."""
    return move_all(apply=False, delete_source=False)
