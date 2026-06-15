"""
Per-tenant database provisioning — Phase 13.1.C (design §12).

Runs the **tenant** Alembic chain against a tenant's database (resolved
through the OpenBAO-leased per-tenant engine) and records the resulting
revision in ``registry_tenant_db_version`` so rollouts can be staged
tenant-by-tenant and a bad migration's blast radius is one tenant.

The database itself is assumed to already exist (created out of band or by
the OpenBAO database-secrets role's creation statements); this brings its
schema up to head.
"""

import logging
import os

from backend.utils.log_sanitize import scrub

logger = logging.getLogger(__name__)


def _alembic_config():
    """Build an Alembic Config for the tenant chain, robust to cwd.

    The tenant chain is the default ``[alembic]`` section; we resolve the ini
    and ``script_location`` to absolute paths so provisioning works regardless
    of the server's working directory.
    """
    from alembic.config import Config  # noqa: PLC0415

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    cfg = Config(os.path.join(repo_root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(repo_root, "alembic"))
    return cfg


def _record_db_version(tenant_id, chain: str, revision) -> None:
    """Upsert the tenant's current revision into the registry."""
    from backend.persistence.models.tenancy import (  # noqa: PLC0415
        RegistryTenantDbVersion,
    )
    from backend.persistence.partitions import (  # noqa: PLC0415
        PARTITION_REGISTRY,
        partition_session,
    )

    with partition_session(partition=PARTITION_REGISTRY) as session:
        row = (
            session.query(RegistryTenantDbVersion)
            .filter(
                RegistryTenantDbVersion.tenant_id == tenant_id,
                RegistryTenantDbVersion.chain == chain,
            )
            .first()
        )
        if row is None:
            row = RegistryTenantDbVersion(tenant_id=tenant_id, chain=chain)
            session.add(row)
        row.revision = revision
        session.commit()


def provision_tenant_database(tenant_id) -> str:
    """Bring a tenant DB to the tenant chain's head; return the revision.

    Resolves the per-tenant engine (which leases OpenBAO credentials), runs
    ``alembic upgrade head`` against it via an injected connection, then records
    the head revision in the registry.
    """
    from alembic import command  # noqa: PLC0415
    from alembic.script import ScriptDirectory  # noqa: PLC0415

    from backend.persistence.partitions import (  # noqa: PLC0415
        PARTITION_TENANT,
        resolve_engine,
    )

    engine = resolve_engine(partition=PARTITION_TENANT, tenant_id=tenant_id)
    cfg = _alembic_config()

    with engine.connect() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")

    head = ScriptDirectory.from_config(cfg).get_current_head()
    _record_db_version(tenant_id, "tenant", head)
    logger.info("Provisioned tenant %s database to revision %s", scrub(tenant_id), head)
    return head
