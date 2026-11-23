# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Soften the "who did it" user FKs on tenant tables to soft GUID references

2026-11-22, production: creating an automatic update profile failed with

    ForeignKeyViolation: upgrade_profiles_created_by_fkey
    DETAIL: Key (created_by)=(...) is not present in table "user".

Users are server-global (the main database); a tenant database's ``user``
table is empty, so a hard FK from a tenant table to ``user.id`` can never be
satisfied there.  ``package_profiles`` was fixed the same way in June
(q14softpkgprofcreatedby); these are the rest of its kind -- every one an
``ON DELETE SET NULL`` record of who created or changed a row of tenant data.
The columns stay (the value still says who); only the cross-partition FK goes.
The user's own records (``api_key``, MFA, password reset, ``user_*``) keep
their FKs: they live with the user in the main database.

Idempotent and SQLite + PostgreSQL safe (SQLite does not enforce them, and
fresh databases are built from the FK-less models).

Revision ID: q109softuserfks
Revises: q108avswap
Create Date: 2026-11-22 00:00:00.000000
"""

from alembic import op

revision = "q109softuserfks"
down_revision = "q108avswap"
branch_labels = None
depends_on = None

# (table, column, constraint) -- names as production's databases carry them.
SOFTENED = (
    ("access_groups", "created_by", "access_groups_created_by_fkey"),
    ("airgap_bundle", "created_by_user_id", "airgap_bundle_created_by_user_id_fkey"),
    ("airgap_collection_run", "created_by", "fk_airgap_collection_run_created_by"),
    ("airgap_ingestion_run", "created_by", "fk_airgap_ingestion_run_created_by"),
    ("default_repository", "created_by", "default_repository_created_by_fkey"),
    ("dynamic_secret_lease", "issued_by", "dynamic_secret_lease_issued_by_fkey"),
    (
        "enabled_package_manager",
        "created_by",
        "enabled_package_manager_created_by_fkey",
    ),
    ("firewall_role", "created_by", "fk_firewall_role_created_by"),
    ("firewall_role", "updated_by", "fk_firewall_role_updated_by"),
    ("host_firewall_role", "created_by", "fk_host_firewall_role_created_by"),
    ("mirror_settings", "updated_by", "mirror_settings_updated_by_fkey"),
    ("registration_keys", "created_by", "registration_keys_created_by_fkey"),
    ("report_branding", "updated_by", "report_branding_updated_by_fkey"),
    ("report_template", "created_by", "report_template_created_by_fkey"),
    ("upgrade_profiles", "created_by", "upgrade_profiles_created_by_fkey"),
)


def _drop_user_fks(table, column):
    """Drop every FK from ``table.column`` to ``user`` -- whatever it is
    named (a database built by hand or an older migration may differ)."""
    op.execute(f"""
        DO $$ DECLARE c record; BEGIN
          IF to_regclass('public.{table}') IS NULL THEN RETURN; END IF;
          FOR c IN SELECT con.conname FROM pg_constraint con
                   JOIN pg_attribute a ON a.attrelid = con.conrelid
                    AND a.attnum = ANY(con.conkey)
                   WHERE con.contype = 'f' AND con.conrelid = 'public.{table}'::regclass
                     AND con.confrelid = 'public."user"'::regclass
                     AND a.attname = '{column}'
          LOOP
            EXECUTE format('ALTER TABLE public.{table} DROP CONSTRAINT %I', c.conname);
          END LOOP;
        END $$;
        """)


def upgrade():
    # expand-contract-ok: drops cross-partition FKs only; every column is kept
    # (as a soft GUID reference), so old code reading them still works, and the
    # FKs were already unsatisfiable in tenant databases.
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, column, _name in SOFTENED:
        _drop_user_fks(table, column)


def downgrade():
    # Re-add each FK where it is missing.  NOT VALID: rows written in a tenant
    # database while it was soft reference users the tenant DB does not hold,
    # so they are not re-checked (new writes there would fail again -- the
    # expected cost of going back to a hard cross-partition FK).
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, column, name in SOFTENED:
        op.execute(f"""
            DO $$ BEGIN
              IF to_regclass('public.{table}') IS NOT NULL AND NOT EXISTS (
                  SELECT 1 FROM pg_constraint WHERE conname = '{name}'
                    AND conrelid = 'public.{table}'::regclass) THEN
                ALTER TABLE public.{table} ADD CONSTRAINT {name}
                  FOREIGN KEY ({column}) REFERENCES public."user"(id)
                  ON DELETE SET NULL NOT VALID;
              END IF;
            END $$;
            """)
