"""Alembic environment for the **shared** reference-data chain.

Builds the ``shared_*`` reference tables (the CVE catalog, package
metadata, mirror tables that are identical for every tenant) and tracks
its revision in ``alembic_version_shared``.  The chain is scaffolded here
in 13.1.A so ``make migrate`` can drive all three partitions; the actual
relocation of reference tables into ``shared_*`` lands in Phase 13.1.D.
All run logic is shared via ``alembic/partition_env.py``.
"""

from backend.persistence.alembic_partition_env import run_migrations

run_migrations(
    version_table="alembic_version_shared",
    include_prefixes=("shared_",),
)
