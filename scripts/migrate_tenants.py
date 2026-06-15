#!/usr/bin/env python3
"""
Fan-out tenant migrations — Phase 13.1.

Runs the **tenant** Alembic chain against every provisioned tenant database,
so an upgrade reaches all tenants, not just the collapsed/bootstrap DB that
``make migrate`` handles.  Staged tenant-by-tenant: a failure on one tenant is
reported and the rest still run (so one bad tenant DB doesn't block the fleet),
and the process exits non-zero if any tenant failed.

No-op (exit 0) when multi-tenancy is disabled.  Only tenants that have a
placement with an ``openbao_role`` are migrated — others can't lease the
credentials needed to reach their database and are skipped with a notice.

Run from the repo root:  python scripts/migrate_tenants.py
"""

import sys
from pathlib import Path

# Allow running as a plain script from the repo root (python scripts/...).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import config  # noqa: E402


def _placed_tenants():
    """Return [(tenant_id, slug, has_role)] for tenants that have a placement."""
    from backend.persistence.models.tenancy import (  # noqa: PLC0415
        RegistryTenant,
        RegistryTenantPlacement,
    )
    from backend.persistence.partitions import (  # noqa: PLC0415
        PARTITION_REGISTRY,
        partition_session,
    )

    out = []
    with partition_session(partition=PARTITION_REGISTRY) as session:
        rows = (
            session.query(RegistryTenantPlacement, RegistryTenant)
            .join(RegistryTenant, RegistryTenant.id == RegistryTenantPlacement.tenant_id)
            .all()
        )
        for placement, tenant in rows:
            out.append((str(tenant.id), tenant.slug, bool(placement.openbao_role)))
    return out


def main(argv=None) -> int:
    _ = argv
    if not config.is_multitenancy_enabled():
        print("Multi-tenancy disabled; no tenant databases to migrate.")
        return 0

    from backend.services import tenant_provisioning  # noqa: PLC0415

    tenants = _placed_tenants()
    if not tenants:
        print("No placed tenants found; nothing to migrate.")
        return 0

    failures = 0
    skipped = 0
    print(f"Migrating {len(tenants)} tenant database(s)...")
    for tenant_id, slug, has_role in tenants:
        if not has_role:
            print(f"  - {slug}: skipped (placement has no openbao_role)")
            skipped += 1
            continue
        try:
            revision = tenant_provisioning.provision_tenant_database(tenant_id)
            print(f"  - {slug}: migrated to {revision}")
        except Exception as exc:  # noqa: BLE001 - report and continue the fleet
            print(f"  - {slug}: FAILED — {exc}")
            failures += 1

    print(
        f"Done. {len(tenants) - failures - skipped} migrated, "
        f"{skipped} skipped, {failures} failed."
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
