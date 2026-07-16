# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Alembic environment for the **registry** control-plane chain.

Builds the ``registry_*`` tables (Phase 13.1.A) and tracks its revision
in ``alembic_version_registry`` so it can coexist with the ``tenant`` and
``shared`` chains in a single collapsed database.  All run logic is shared
via ``alembic/partition_env.py``.
"""

from backend.persistence.alembic_partition_env import run_migrations

run_migrations(
    version_table="alembic_version_registry",
    include_prefixes=("registry_",),
)
