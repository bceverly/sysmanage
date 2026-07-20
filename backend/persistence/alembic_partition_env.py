# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Shared Alembic environment logic for the three partition chains.

Phase 13.1 splits the schema into three independent Alembic chains —
``registry`` (``registry_*`` tables), ``shared`` (``shared_*`` reference
tables), and ``tenant`` (the existing per-customer schema, unprefixed).
Each chain is a single linear chain with **its own version table** so the
three can coexist in one database (collapsed/homelab mode) without
stomping each other:

    registry  → alembic_version_registry
    shared    → alembic_version_shared
    tenant    → alembic_version            (the legacy/default table)

Rather than copy-paste three near-identical ``env.py`` files, the common
run logic lives here and each chain's ``env.py`` calls :func:`run_migrations`
with its partition name, version table, and table-name filter.  This is
the "one env.py that branches on --name" from the design doc, realized as
a shared helper so each chain still has a conventional ``env.py`` that
Alembic discovers per ``script_location``.

The database URL resolution mirrors the original tenant ``env.py``:
``DATABASE_URL`` env var (CI) → config → CI fallback.  In collapsed mode
all three chains resolve to the *same* URL, which is exactly what makes
"stuff it all in one database" work with zero extra configuration.
"""

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Alembic's config key for the target database URL.
_SQLALCHEMY_URL = "sqlalchemy.url"


def _resolve_database_url() -> str:
    """Resolve the target DB URL with the same priority as the tenant env."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    try:
        from backend.persistence.db import (  # noqa: PLC0415
            get_database_url,
        )

        url = get_database_url()
    except Exception as exc:  # pragma: no cover - CI fallback
        print(f"Warning: could not get database URL from config: {exc}")
        url = "postgresql://sysmanage:abc123@localhost:5432/sysmanage"

    if not url or not url.startswith(("postgresql://", "sqlite:///")):
        print("Error: invalid database URL format; using CI default")
        url = "postgresql://sysmanage:abc123@localhost:5432/sysmanage"
    return url


def _make_include_name(include_prefixes, exclude_prefixes):
    """Build an Alembic ``include_name`` filter scoped to this partition.

    Only ``table`` names are filtered (so a chain's autogenerate sees only
    its own partition's tables); every other object type passes through.
    This keeps the chains honest — the ``tenant`` chain will not try to
    create ``registry_*`` tables just because they share ``Base.metadata``.
    """

    def include_name(name, type_, parent_names):  # noqa: ARG001
        if type_ != "table" or name is None:
            return True
        if include_prefixes is not None:
            return any(name.startswith(p) for p in include_prefixes)
        if exclude_prefixes is not None:
            return not any(name.startswith(p) for p in exclude_prefixes)
        return True

    return include_name


def run_migrations(
    *,
    version_table: str,
    include_prefixes=None,
    exclude_prefixes=None,
):
    """Run the current chain's migrations.

    Args:
        version_table: the Alembic version table for this chain.
        include_prefixes: if set, autogenerate considers only tables whose
            name starts with one of these prefixes.
        exclude_prefixes: if set, autogenerate ignores tables whose name
            starts with one of these prefixes.  (``include_prefixes`` wins
            when both are given.)
    """
    config = context.config

    # Populate Base.metadata with every model (so autogenerate diffs work)
    # then point the run at it.  Importing the models package registers all
    # tables on the shared Base; the include filter scopes this chain.
    from backend.persistence.db import Base  # noqa: PLC0415
    import backend.persistence.models  # noqa: F401, PLC0415  # pylint: disable=unused-import

    target_metadata = Base.metadata

    # Set the URL unless one was already injected (tests pass a connection).
    if not config.get_main_option(_SQLALCHEMY_URL):
        from backend.persistence.db import _psycopg_url  # noqa: PLC0415

        config.set_main_option(_SQLALCHEMY_URL, _psycopg_url(_resolve_database_url()))

    if config.config_file_name is not None:
        fileConfig(config.config_file_name)

    include_name = _make_include_name(include_prefixes, exclude_prefixes)

    common = {
        "target_metadata": target_metadata,
        "version_table": version_table,
        "include_name": include_name,
        "include_schemas": False,
    }

    if context.is_offline_mode():
        context.configure(
            url=config.get_main_option(_SQLALCHEMY_URL),
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
            **common,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    # Online mode.  Tests inject a live connection via config.attributes.
    if hasattr(config, "attributes") and "connection" in config.attributes:
        connection = config.attributes["connection"]
        context.configure(connection=connection, **common)
        with context.begin_transaction():
            context.run_migrations()
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # WAL journal mode is more reliable than the default DELETE mode when
    # multiple pytest-xdist workers run migrations against separate SQLite
    # databases concurrently — DELETE mode creates/removes a rollback
    # journal per transaction, which can trigger "attempt to write a
    # readonly database" on FreeBSD under heavy parallel I/O.
    if connectable.url.get_backend_name() == "sqlite":
        from sqlalchemy import event  # noqa: PLC0415

        @event.listens_for(connectable, "connect")
        def _set_sqlite_wal(dbapi_conn, _rec):
            dbapi_conn.execute("PRAGMA journal_mode=WAL")

    with connectable.connect() as connection:
        context.configure(connection=connection, **common)
        with context.begin_transaction():
            context.run_migrations()
