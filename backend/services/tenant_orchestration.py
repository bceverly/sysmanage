"""
Self-service tenant provisioning orchestration — Phase 13.1.

Lets the control plane create a tenant's database and OpenBAO dynamic-creds
role *itself*, so an operator doesn't have to run ``bao``/``psql`` by hand.

Security model (see ``docs`` + ``scripts/provision_bootstrap.py``):
  * The server NEVER holds a Postgres superuser or a broad OpenBAO token.
  * A one-time, operator-run bootstrap creates a least-privilege Postgres
    ``provisioner`` role (``CREATEDB`` + ``CREATEROLE`` only) and stores its
    credentials in OpenBAO at ``sysmanage/provisioner``, plus a scoped OpenBAO
    policy limited to ``sys/mounts/database*`` / ``database/config|roles/*``.
  * This module reads the provisioner credential just-in-time and uses it to:
      1. create a per-tenant database owned by a *stable* per-tenant owner
         role (so objects aren't owned by short-lived dynamic users), and
      2. write the per-tenant OpenBAO database config + role, with a templated
         connection URL (no stored plaintext password) and a role whose
         dynamic users are members of the owner role — so they inherit full
         privileges with no manual GRANTs.
  * Gated by ``multitenancy.self_service_provisioning`` (default off) and an
    admin role at the API layer, and audited.

Everything here is idempotent: re-running for an existing tenant is safe.
"""

import logging
import re
from typing import Optional

from backend.config import config

logger = logging.getLogger(__name__)

# Where the bootstrap stores the Postgres provisioner credential in OpenBAO.
_PROVISIONER_SECRET_SUBPATH = "sysmanage/provisioner"  # nosec B105


class OrchestrationError(RuntimeError):
    """Raised when self-service provisioning can't proceed."""


def _safe_identifier(value: str) -> str:
    """Return a safe lowercased SQL identifier (letters, digits, underscore).

    Tenant slugs are operator-controlled, but we still never interpolate raw
    input into DDL — derive a conservative identifier and reject anything that
    doesn't reduce to a valid one.
    """
    ident = re.sub(r"[^a-z0-9_]", "_", (value or "").strip().lower())
    ident = re.sub(r"_+", "_", ident).strip("_")
    if not ident or not re.match(r"^[a-z_][a-z0-9_]*$", ident):
        raise OrchestrationError(f"Cannot derive a safe identifier from {value!r}")
    return ident


def _provisioner_credentials() -> dict:
    """Read the Postgres provisioner credential from OpenBAO; never logs it."""
    if not config.is_vault_enabled():
        raise OrchestrationError(
            "OpenBAO is disabled; self-service provisioning needs the "
            "provisioner credential stored in OpenBAO."
        )
    try:
        from backend.services.vault_service import VaultService  # noqa: PLC0415

        mount = config.get_vault_mount_path()
        data = VaultService().retrieve_secret(
            f"{mount}/data/{_PROVISIONER_SECRET_SUBPATH}"
        )
    except Exception as exc:  # noqa: BLE001
        raise OrchestrationError(
            "Could not read the provisioner credential from OpenBAO. Run "
            "'make provision-bootstrap' first."
        ) from exc
    if not isinstance(data, dict) or not data.get("password") or not data.get("user"):
        raise OrchestrationError(
            "Provisioner credential is missing/incomplete in OpenBAO "
            f"({_PROVISIONER_SECRET_SUBPATH}). Run 'make provision-bootstrap'."
        )
    return {
        "host": data.get("host") or "localhost",
        "port": int(data.get("port") or 5432),
        "user": data["user"],
        "password": data["password"],
        "sslmode": data.get("sslmode") or "prefer",
    }


def is_provisioner_configured() -> bool:
    """True when the provisioner credential is available (bootstrap done)."""
    try:
        _provisioner_credentials()
        return True
    except OrchestrationError:
        return False


def _connect_provisioner(creds: dict, dbname: str = "postgres"):
    """Open an autocommit psycopg2 connection as the provisioner role."""
    import psycopg2  # noqa: PLC0415

    conn = psycopg2.connect(
        host=creds["host"],
        port=creds["port"],
        user=creds["user"],
        password=creds["password"],
        dbname=dbname,
        sslmode=creds["sslmode"],
        connect_timeout=10,
    )
    conn.autocommit = True  # CREATE DATABASE can't run inside a transaction.
    return conn


def create_tenant_database(dbname: str, owner_role: str) -> None:
    """Idempotently create ``owner_role`` (NOLOGIN) and ``dbname`` owned by it.

    Connects as the least-privilege provisioner (CREATEDB+CREATEROLE).  Safe to
    re-run: existing role/database are left as-is.
    """
    from psycopg2 import sql  # noqa: PLC0415

    creds = _provisioner_credentials()
    conn = _connect_provisioner(creds)
    try:
        with conn.cursor() as cur:
            # Owner role: a stable NOLOGIN role that owns the schema, so objects
            # are never owned by short-lived dynamic users.
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (owner_role,))
            if cur.fetchone() is None:
                cur.execute(
                    sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(owner_role))
                )
                logger.info("Created owner role %s", owner_role)
            # The provisioner must be a MEMBER of the owner role (able to SET
            # ROLE to it) before it can assign database ownership to it or create
            # dynamic users IN ROLE it.  Idempotent: re-granting is harmless.
            cur.execute(
                sql.SQL("GRANT {} TO CURRENT_USER").format(sql.Identifier(owner_role))
            )
            # Database owned by the owner role.
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
            if cur.fetchone() is None:
                cur.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {}").format(
                        sql.Identifier(dbname), sql.Identifier(owner_role)
                    )
                )
                logger.info("Created tenant database %s (owner %s)", dbname, owner_role)
    finally:
        conn.close()


def configure_openbao_role(
    *,
    config_name: str,
    role_name: str,
    owner_role: str,
    dbname: str,
    host: str,
    port: int,
    ttl: str = "1h",
    max_ttl: str = "24h",
) -> None:
    """Write the per-tenant OpenBAO database config + dynamic-creds role.

    The connection URL is templated (``{{username}}/{{password}}``) so no
    plaintext password is stored and root rotation works; the leased role's
    dynamic users are created ``IN ROLE owner_role`` so they inherit full
    privileges on the tenant schema without any manual GRANTs.
    """
    creds = _provisioner_credentials()
    from backend.services.vault_service import VaultService  # noqa: PLC0415

    svc = VaultService()
    db_mount = config.get_vault_database_mount_path()

    # 1) Connection config: OpenBAO connects as the provisioner ("root") to
    #    mint dynamic users.  Templated URL keeps the password out of storage.
    svc.make_raw_request(
        "POST",
        f"{db_mount}/config/{config_name}",
        {
            "plugin_name": "postgresql-database-plugin",
            "allowed_roles": [role_name],
            "connection_url": (
                "postgresql://{{username}}:{{password}}@"
                f"{host}:{port}/{dbname}?sslmode={creds['sslmode']}"
            ),
            "username": creds["user"],
            "password": creds["password"],
        },
    )
    # 2) Role: dynamic users are members of the stable owner role, and every
    #    session SET ROLEs to it, so objects they CREATE (during migrations or
    #    at runtime) are owned by the stable owner — not by the short-lived
    #    dynamic user.  Without the SET ROLE, the next lease can't touch them.
    creation = (
        "CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' "
        f"VALID UNTIL '{{{{expiration}}}}' IN ROLE \"{owner_role}\";"
        f" ALTER ROLE \"{{{{name}}}}\" SET role TO '{owner_role}';"
    )
    svc.make_raw_request(
        "POST",
        f"{db_mount}/roles/{role_name}",
        {
            "db_name": config_name,
            "creation_statements": creation,
            "default_ttl": ttl,
            "max_ttl": max_ttl,
        },
    )
    logger.info(
        "Configured OpenBAO database role %s (config %s)", role_name, config_name
    )


def derive_names(slug: str) -> dict:
    """Derive the DB/role names for a tenant slug (deterministic + safe)."""
    base = _safe_identifier(slug)
    return {
        "dbname": f"tenant_{base}",
        "owner_role": f"{base}_owner",
        "config_name": base,
        "openbao_role": f"{base}-role",
    }


def auto_provision_tenant(
    tenant_id: str,
    *,
    slug: str,
    host: Optional[str] = None,
    port: Optional[int] = None,
    region: Optional[str] = None,
    tier: str = "silo",
) -> dict:
    """End-to-end self-service provisioning for one tenant.

    Creates the DB + owner role, writes the OpenBAO config/role, records the
    placement, then runs the tenant migration chain.  Idempotent.  Returns a
    summary dict.  Raises OrchestrationError on any step.
    """
    if not config.is_self_service_provisioning_enabled():
        raise OrchestrationError("Self-service provisioning is disabled.")

    host = host or "localhost"
    port = int(port or 5432)
    names = derive_names(slug)

    # 1) Database + owner role.
    create_tenant_database(names["dbname"], names["owner_role"])

    # 2) OpenBAO config + dynamic-creds role.
    configure_openbao_role(
        config_name=names["config_name"],
        role_name=names["openbao_role"],
        owner_role=names["owner_role"],
        dbname=names["dbname"],
        host=host,
        port=port,
    )

    # 3) Record placement (DB coordinates + the OpenBAO role; never a password).
    _upsert_placement(
        tenant_id,
        host=host,
        port=port,
        dbname=names["dbname"],
        region=region,
        tier=tier,
        openbao_role=names["openbao_role"],
    )

    # 4) Run the tenant migration chain against the freshly-created DB.
    from backend.services import tenant_provisioning  # noqa: PLC0415

    revision = tenant_provisioning.provision_tenant_database(tenant_id)

    return {
        "tenant_id": str(tenant_id),
        "dbname": names["dbname"],
        "openbao_role": names["openbao_role"],
        "revision": revision,
        "status": "provisioned",
    }


def deprovision_tenant(tenant_id, *, slug: str, drop_database: bool = False) -> dict:
    """Tear down a tenant: OpenBAO role/config, (optionally) the DB, registry rows.

    Best-effort and resilient: a failure in one step is recorded in
    ``errors`` and the rest still run, so a partially-provisioned tenant can
    always be cleaned up.  Registry rows are always removed last so the tenant
    disappears from the control plane even if external cleanup hit a snag.
    """
    names = derive_names(slug)
    result = {
        "openbao_removed": False,
        "database_dropped": False,
        "registry_removed": False,
        "errors": [],
    }

    _teardown_openbao(names, result)
    if drop_database:
        _drop_tenant_database(names, result)
    _delete_registry_records(tenant_id, result)
    return result


def _teardown_openbao(names: dict, result: dict) -> None:
    """Revoke leases and delete the tenant's OpenBAO role + config (best-effort)."""
    if not config.is_vault_enabled():
        return
    try:
        from backend.services.vault_service import VaultService  # noqa: PLC0415

        svc = VaultService()
        db_mount = config.get_vault_database_mount_path()
        role = names["openbao_role"]
        cfg = names["config_name"]
        # Revoke any live dynamic credentials first so their roles can be
        # dropped, then remove the role + connection config.
        for method, path in (
            ("PUT", f"sys/leases/revoke-prefix/{db_mount}/creds/{role}"),
            ("DELETE", f"{db_mount}/roles/{role}"),
            ("DELETE", f"{db_mount}/config/{cfg}"),
        ):
            try:
                svc.make_raw_request(method, path)
            except Exception as exc:  # noqa: BLE001 - continue teardown
                result["errors"].append(f"openbao {path}: {exc}")
        result["openbao_removed"] = True
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"openbao: {exc}")


def _drop_tenant_database(names: dict, result: dict) -> None:
    """Drop the tenant database and its owner role (best-effort)."""
    from psycopg2 import sql  # noqa: PLC0415

    dbname = names["dbname"]
    owner = names["owner_role"]
    try:
        creds = _provisioner_credentials()
        conn = _connect_provisioner(creds)
        try:
            with conn.cursor() as cur:
                # Terminate other connections so DROP DATABASE can proceed.
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (dbname,),
                )
                cur.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(dbname))
                )
                result["database_dropped"] = True
                # Owner role now owns nothing in the dropped DB; drop it too.
                try:
                    cur.execute(
                        sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(owner))
                    )
                except Exception as exc:  # noqa: BLE001 - role may still be referenced
                    result["errors"].append(f"drop owner role: {exc}")
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"drop database: {exc}")


def _delete_registry_records(tenant_id, result: dict) -> None:
    """Remove the tenant's registry rows (grants, domains, placement, version, row)."""
    try:
        from backend.persistence.models.tenancy import (  # noqa: PLC0415
            RegistryTenant,
            RegistryTenantDbVersion,
            RegistryTenantEmailDomain,
            RegistryTenantPlacement,
            RegistryUserTenantGrant,
        )
        from backend.persistence.partitions import (  # noqa: PLC0415
            PARTITION_REGISTRY,
            partition_session,
        )

        with partition_session(partition=PARTITION_REGISTRY) as session:
            for model in (
                RegistryUserTenantGrant,
                RegistryTenantEmailDomain,
                RegistryTenantPlacement,
                RegistryTenantDbVersion,
            ):
                session.query(model).filter(model.tenant_id == tenant_id).delete(
                    synchronize_session=False
                )
            session.query(RegistryTenant).filter(RegistryTenant.id == tenant_id).delete(
                synchronize_session=False
            )
            session.commit()
        result["registry_removed"] = True
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"registry: {exc}")


def _upsert_placement(tenant_id, **fields) -> None:
    """Create/update the tenant's placement row in the registry."""
    from backend.persistence.models.tenancy import (  # noqa: PLC0415
        RegistryTenantPlacement,
    )
    from backend.persistence.partitions import (  # noqa: PLC0415
        PARTITION_REGISTRY,
        partition_session,
    )

    with partition_session(partition=PARTITION_REGISTRY) as session:
        placement = (
            session.query(RegistryTenantPlacement)
            .filter(RegistryTenantPlacement.tenant_id == tenant_id)
            .first()
        )
        if placement is None:
            placement = RegistryTenantPlacement(tenant_id=tenant_id)
            session.add(placement)
        for key, value in fields.items():
            setattr(placement, key, value)
        session.commit()
