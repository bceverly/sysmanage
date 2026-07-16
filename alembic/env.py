# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Alembic environment for the **tenant** chain — the existing per-customer
schema (the original 140+ migration chain).

Phase 13.1 introduced two sibling partition chains (``registry`` and
``shared``); the common run logic now lives in ``alembic/partition_env.py``
and each chain's ``env.py`` is a thin call into it.  The tenant chain keeps
the legacy ``alembic_version`` table (so the existing chain is untouched)
and simply *excludes* the ``registry_*`` / ``shared_*`` tables from its
autogenerate view — they belong to the other chains, even though all three
share one ``Base.metadata`` and (in collapsed mode) one database.
"""

from backend.persistence.alembic_partition_env import run_migrations

run_migrations(
    version_table="alembic_version",
    exclude_prefixes=("registry_", "shared_"),
)
