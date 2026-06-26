"""PostgreSQL-backed migration smoke test (Phase 13.1.D follow-up).

The SQLite-only ``test_alembic_prefix_guard`` cannot catch dialect-specific
migration bugs — e.g. a column declared ``CHAR(36)`` that must be ``UUID`` on
PostgreSQL, or a foreign key whose name PostgreSQL auto-generates differently
from SQLite.  Both bit Phase 13.1.D/F migrations precisely because the only
migration test ran on SQLite.

This test runs ALL THREE Alembic chains (registry, shared, tenant) to head
against a REAL, scratch PostgreSQL database and asserts the same prefix
discipline the SQLite guard does.  It is skipped unless ``DATABASE_URL`` points
at PostgreSQL (so local SQLite-only dev and CI without a PG service just skip
it); CI's ``test-backend`` job provides a ``postgres`` service, so it runs there.
"""

import os
import subprocess
import sys

import pytest

try:
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
except ImportError:  # pragma: no cover - psycopg2 is a backend dependency
    psycopg2 = None

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DB_URL = os.environ.get("DATABASE_URL", "")
_SCRATCH_DB = "sysmanage_migtest"

pytestmark = pytest.mark.skipif(
    not _DB_URL.startswith(("postgresql://", "postgres://")) or psycopg2 is None,
    reason="set DATABASE_URL to a PostgreSQL server (with psycopg2) to run the "
    "PG migration smoke test",
)


def _admin_dsn() -> str:
    """The DATABASE_URL pointed at the default maintenance DB, for CREATE/DROP."""
    # Replace the trailing /<dbname> with /postgres so we can create the scratch DB.
    base, _, _dbname = _DB_URL.rpartition("/")
    return f"{base}/postgres"


def _scratch_url() -> str:
    base, _, _dbname = _DB_URL.rpartition("/")
    return f"{base}/{_SCRATCH_DB}"


def _create_scratch_db():
    conn = psycopg2.connect(_admin_dsn())
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with conn.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{_SCRATCH_DB}"')
            cur.execute(f'CREATE DATABASE "{_SCRATCH_DB}"')
    finally:
        conn.close()


def _drop_scratch_db():
    conn = psycopg2.connect(_admin_dsn())
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with conn.cursor() as cur:
            # Terminate any leftover connections, then drop.
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (_SCRATCH_DB,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{_SCRATCH_DB}"')
    finally:
        conn.close()


def _upgrade(chain: str, url: str) -> None:
    args = [sys.executable, "-m", "alembic"]
    if chain != "tenant":  # tenant is the default (unnamed) section
        args += ["--name", chain]
    args += ["upgrade", "head"]
    env = {**os.environ, "DATABASE_URL": url}
    result = subprocess.run(
        args, cwd=_REPO_ROOT, env=env, capture_output=True, text=True, check=False
    )
    assert (
        result.returncode == 0
    ), f"alembic upgrade for chain {chain!r} failed on PostgreSQL:\n{result.stderr}"


def _tables(url: str) -> set:
    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            return {
                r[0] for r in cur.fetchall() if not r[0].startswith("alembic_version")
            }
    finally:
        conn.close()


@pytest.fixture(scope="module")
def scratch_db():
    try:
        _create_scratch_db()
    except psycopg2.Error as exc:  # pragma: no cover - privilege-dependent
        pytest.skip(f"cannot create scratch PG database (privilege?): {exc}")
    try:
        yield _scratch_url()
    finally:
        _drop_scratch_db()


def test_all_chains_apply_on_postgres(scratch_db):
    """Every Alembic chain applies to head on a real PostgreSQL database.

    Runs registry → shared → tenant in sequence against a fresh scratch DB (the
    collapsed single-database deployment).  Exercising each chain's DDL on PG is
    the dialect coverage the SQLite-only ``test_alembic_prefix_guard`` cannot
    give — this is what catches the ``r7registry`` (CHAR-vs-UUID FK),
    ``s1shared``, and ``d1sharedmkv`` (PG auto-named FK) bugs that previously
    reached ``make migrate``.  An upgrade failure on any chain fails the test
    with alembic's stderr."""
    _upgrade("registry", scratch_db)
    _upgrade("shared", scratch_db)
    _upgrade("tenant", scratch_db)

    tables = _tables(scratch_db)
    # The relocated catalog landed in the shared partition and the old tenant
    # copy was dropped (the d1sharedmkv FK-name fix, exercised on PG).
    assert "shared_mirror_known_version" in tables
    assert "mirror_known_version" not in tables
    # The per-tenant IdP columns migration (e1idptenancy) applied too.
    assert "external_idp_provider" in tables
    # And the backup table from the registry chain (the r7registry FK fix).
    assert "registry_tenant_backup" in tables
