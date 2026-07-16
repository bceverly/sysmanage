# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add_host_geolocation_columns

Phase 12.7: Host geo-location + global map.

Adds seven columns to ``host`` for the public-IP + GeoLite2 lookup
chain plus one composite index used by the map's per-region cluster
queries:

    public_ip               String(45)   -- IPv6-safe storage
    public_ip_resolved_at   DateTime     -- cache-invalidation key
    geo_country_code        String(2)    -- ISO 3166-1 alpha-2
    geo_subdivision_code    String(10)   -- ISO 3166-2
    geo_city                String(200)  -- MaxMind canonical English
    geo_latitude            Float        -- decimal degrees
    geo_longitude           Float        -- decimal degrees
    INDEX (geo_country_code, geo_subdivision_code)

Idempotent — re-runnable on a database that already has any subset
of these columns / the index.  Type choices avoid PostgreSQL-only
types (INET, NUMERIC(p,s)) so the same migration runs on SQLite.

Revision ID: l0geo10
Revises: k9mfaemail
Create Date: 2026-05-18

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "l0geo10"
down_revision: Union[str, None] = "k9mfaemail"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Columns we're adding, kept as data so upgrade()/downgrade() stay
# short and the idempotency loop is obvious.
_GEO_COLUMNS = (
    ("public_ip", sa.String(45)),
    ("public_ip_resolved_at", sa.DateTime()),
    ("geo_country_code", sa.String(2)),
    ("geo_subdivision_code", sa.String(10)),
    ("geo_city", sa.String(200)),
    ("geo_latitude", sa.Float()),
    ("geo_longitude", sa.Float()),
)

_GEO_INDEX_NAME = "ix_host_geo_country_subdivision"
_GEO_INDEX_COLS = ("geo_country_code", "geo_subdivision_code")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_columns = {col["name"] for col in inspector.get_columns("host")}
    for name, type_ in _GEO_COLUMNS:
        if name not in existing_columns:
            op.add_column("host", sa.Column(name, type_, nullable=True))

    # Index creation — also idempotent.  ``get_indexes`` returns dicts
    # with ``name`` keys; we skip if our index already exists.
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("host")}
    if _GEO_INDEX_NAME not in existing_indexes:
        op.create_index(
            _GEO_INDEX_NAME,
            "host",
            list(_GEO_INDEX_COLS),
            unique=False,
        )


def downgrade() -> None:
    # Drop in reverse order: index first (it references the columns),
    # then the columns themselves.  Each step guarded by an existence
    # check so a partial-upgrade rollback still works.
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("host")}
    if _GEO_INDEX_NAME in existing_indexes:
        op.drop_index(_GEO_INDEX_NAME, table_name="host")

    existing_columns = {col["name"] for col in inspector.get_columns("host")}
    for name, _ in reversed(_GEO_COLUMNS):
        if name in existing_columns:
            op.drop_column("host", name)
