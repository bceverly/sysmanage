#!/usr/bin/env python3
"""
sysmanage-migrate — apply SysManage database migrations (production tool).

Runs, from the SysManage server (the DB hosts are never touched directly):

  1. the **registry** chain (control-plane tables),
  2. the **shared** chain (reference data),
  3. the **tenant** chain against the bootstrap/collapsed database, and
  4. the per-tenant fan-out: the tenant chain against EVERY tenant database
     listed in the registry, with a progress bar (N of N = 100%).

In the default single-database (homelab) deployment steps 1-3 run against the
one database and step 4 is a no-op.  With multi-tenancy enabled, step 4 leases
each tenant's credentials from OpenBAO (which must be running) and migrates that
tenant's database; failures are isolated per tenant so one bad tenant doesn't
block the rest, and the command exits non-zero if any tenant failed.

Idempotent and safe to re-run (already-current databases are skipped).

Usage:
  sysmanage-migrate            # apply everything
  sysmanage-migrate --status   # show what's current vs pending (no changes)
  sysmanage-migrate --dry-run  # show what WOULD run, without changing anything
  sysmanage-migrate --no-tenants   # chains only, skip the per-tenant fan-out
"""

import argparse
import os
import sys
from pathlib import Path

# Allow running as a plain script from the install dir.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))


def _chain_config(section: str, script_subdir: str):
    """Build an Alembic Config for a named chain, with absolute paths."""
    from alembic.config import Config  # noqa: PLC0415

    cfg = Config(str(_REPO_ROOT / "alembic.ini"), ini_section=section)
    cfg.set_main_option("script_location", str(_REPO_ROOT / script_subdir))
    return cfg


_CHAINS = (
    ("registry", "alembic/registry", "registry (control-plane tables)"),
    ("shared", "alembic/shared", "shared (reference data)"),
    ("alembic", "alembic", "tenant (bootstrap database)"),
)


def _code_head(cfg) -> str:
    from alembic.script import ScriptDirectory  # noqa: PLC0415

    return ScriptDirectory.from_config(cfg).get_current_head() or "(none)"


def run_chains(dry_run: bool) -> None:
    """Upgrade the registry, shared, and tenant (bootstrap) chains to head."""
    from alembic import command  # noqa: PLC0415

    for section, subdir, label in _CHAINS:
        cfg = _chain_config(section, subdir)
        head = _code_head(cfg)
        if dry_run:
            print(f"  [dry-run] would upgrade {label} -> {head}")
            continue
        print(f"  -> {label}")
        command.upgrade(cfg, "head")


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
            .join(
                RegistryTenant, RegistryTenant.id == RegistryTenantPlacement.tenant_id
            )
            .order_by(RegistryTenant.slug)
            .all()
        )
        for placement, tenant in rows:
            out.append((str(tenant.id), tenant.slug, bool(placement.openbao_role)))
    return out


def _progress_bar(done: int, total: int, width: int = 30) -> str:
    """A textual progress bar; done==total renders as 100%."""
    if total <= 0:
        return ""
    filled = int(width * done / total)
    bar = "#" * filled + "-" * (width - filled)
    pct = int(round(100 * done / total))
    return f"[{bar}] {done}/{total} ({pct}%)"


def _emit_progress(done: int, total: int, suffix: str = "") -> None:
    line = _progress_bar(done, total) + (f"  {suffix}" if suffix else "")
    if sys.stdout.isatty():
        # In-place update on a terminal; pad to clear the previous line.
        sys.stdout.write("\r" + line.ljust(72))
        sys.stdout.flush()
    else:
        print(line)


def _ensure_multitenancy_engine() -> bool:
    """Load + bridge the licensed multi-tenancy engine into the OSS seam.

    Per-tenant provisioning logic lives in the compiled ``multitenancy_engine``
    (a Pro+ MULTITENANT_SAAS capability), so this operator tool must load and
    bridge it exactly like the server does at startup — otherwise the fan-out's
    ``provision_tenant_database`` calls hit the unlicensed shim and refuse.

    Best-effort and idempotent: returns True when the engine is bridged, False
    (with an actionable message) when it can't be — e.g. unlicensed or no build
    cached for this platform/Python.  Loads from the local module cache (no
    network) when the engine was already fetched via ``make update``.
    """
    import asyncio  # noqa: PLC0415

    from backend.multitenancy import seam  # noqa: PLC0415

    if seam.is_engine_present():
        return True

    async def _load_and_bridge() -> bool:
        from backend.licensing.license_service import license_service  # noqa: PLC0415
        from backend.licensing.module_loader import module_loader  # noqa: PLC0415
        from backend.multitenancy import bridge  # noqa: PLC0415

        await license_service.initialize()
        if not license_service.is_pro_plus_active:
            return False
        module_loader.initialize()
        await module_loader.ensure_module_available("multitenancy_engine")
        engine_module = module_loader.get_module("multitenancy_engine")
        if engine_module is None:
            return False
        return bridge.bridge_loaded_engine(engine_module)

    try:
        return asyncio.run(_load_and_bridge())
    except Exception as exc:  # noqa: BLE001 - report, don't crash the whole run
        print(f"     [warn] could not load the multi-tenancy engine: {exc}")
        return False


def fan_out_tenants(dry_run: bool) -> int:
    """Migrate every placed tenant database with a progress bar.

    Returns the number of tenants that FAILED (0 = all good).
    """
    from backend.config import config  # noqa: PLC0415

    if not config.is_multitenancy_enabled():
        print("  -> per-tenant databases: skipped (multi-tenancy disabled)")
        return 0

    tenants = _placed_tenants()
    migratable = [(tid, slug) for (tid, slug, has_role) in tenants if has_role]
    skipped = [slug for (_t, slug, has_role) in tenants if not has_role]
    total = len(migratable)

    print(f"  -> per-tenant databases: {total} to migrate", end="")
    if skipped:
        print(f" ({len(skipped)} skipped: no openbao_role — {', '.join(skipped)})")
    else:
        print()
    if total == 0:
        return 0
    if dry_run:
        for _tid, slug in migratable:
            print(f"     [dry-run] would migrate tenant '{slug}'")
        return 0

    # Per-tenant provisioning lives in the licensed engine — load + bridge it
    # before the fan-out (the server does this at startup; this standalone tool
    # must do it too).  Without it every tenant would fail with the unlicensed
    # shim's refusal, so fail loudly + actionably instead.
    if not _ensure_multitenancy_engine():
        print(
            "  [FAIL] multi-tenancy is enabled but the licensed multitenancy_engine "
            "is not loaded — cannot migrate per-tenant databases. Ensure the Pro+ "
            "MULTITENANT_SAAS license is active and run 'make update' so the engine "
            "is cached for this platform/Python."
        )
        return total

    from backend.services import tenant_provisioning  # noqa: PLC0415

    failures = 0
    done = 0
    _emit_progress(done, total, "starting...")
    for tid, slug in migratable:
        try:
            revision = tenant_provisioning.provision_tenant_database(tid)
            suffix = f"{slug} -> {revision}"
        except Exception as exc:  # noqa: BLE001 - isolate per-tenant failures
            failures += 1
            suffix = f"{slug} FAILED: {exc}"
        done += 1
        _emit_progress(done, total, suffix)
    if sys.stdout.isatty():
        sys.stdout.write("\n")
    return failures


def show_status() -> int:
    """Print code heads + per-tenant migration drift.  Always exit 0."""
    print("=== SysManage migration status ===")
    for section, subdir, label in _CHAINS:
        cfg = _chain_config(section, subdir)
        print(f"  {label}: code head = {_code_head(cfg)}")

    from backend.config import config  # noqa: PLC0415

    if not config.is_multitenancy_enabled():
        print("  per-tenant: multi-tenancy disabled (single database).")
        return 0

    tenant_cfg = _chain_config("alembic", "alembic")
    tenant_head = _code_head(tenant_cfg)
    from backend.persistence.models.tenancy import (  # noqa: PLC0415
        RegistryTenant,
        RegistryTenantDbVersion,
    )
    from backend.persistence.partitions import (  # noqa: PLC0415
        PARTITION_REGISTRY,
        partition_session,
    )

    print(f"  per-tenant (tenant chain head = {tenant_head}):")
    with partition_session(partition=PARTITION_REGISTRY) as session:
        tenants = session.query(RegistryTenant).order_by(RegistryTenant.slug).all()
        if not tenants:
            print("    (no tenants)")
        for tenant in tenants:
            ver = (
                session.query(RegistryTenantDbVersion)
                .filter(
                    RegistryTenantDbVersion.tenant_id == tenant.id,
                    RegistryTenantDbVersion.chain == "tenant",
                )
                .first()
            )
            current = ver.revision if ver else None
            state = "up to date" if current == tenant_head else "PENDING"
            print(f"    {tenant.slug}: {current or '(never migrated)'} [{state}]")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--status", action="store_true", help="Show status; make no changes."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would run; no changes."
    )
    parser.add_argument(
        "--no-tenants",
        action="store_true",
        help="Apply the chains only; skip the per-tenant fan-out.",
    )
    parser.add_argument(
        "--tenants-only",
        action="store_true",
        help="Run only the per-tenant fan-out; skip the chains.",
    )
    args = parser.parse_args(argv)

    if args.status:
        return show_status()

    print("=== Applying SysManage database migrations ===")
    if not args.tenants_only:
        run_chains(args.dry_run)
    failures = 0
    if not args.no_tenants:
        failures = fan_out_tenants(args.dry_run)

    if failures:
        print(f"[FAIL] {failures} tenant database(s) failed to migrate (see above).")
        return 1
    print("[OK] Migrations complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
