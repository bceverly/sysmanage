"""Phase 13.1.D — the mirror version catalog relocates to the ``shared`` partition.

``mirror_known_version`` (the Add-Mirror version dropdown catalog) is canonical
reference data, identical for every tenant.  It moves out of the per-tenant
chain into ``shared_mirror_known_version`` in the ``shared`` chain, and the
cross-partition FK on ``mirror_repository.known_version_id`` becomes a soft
reference (bare UUID, no constraint).

This guards the relocation end-to-end on a scratch SQLite (collapsed mode, where
both chains target the same database — exactly how a default install runs):

  * the shared chain creates + seeds ``shared_mirror_known_version``,
  * the tenant chain drops the old ``mirror_known_version``,
  * ``mirror_repository.known_version_id`` survives WITHOUT a foreign key.
"""

import os
import sqlite3
import subprocess
import sys
import tempfile

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _upgrade(chain: str, db_path: str) -> None:
    args = [sys.executable, "-m", "alembic"]
    if chain != "tenant":  # tenant is the default (unnamed) section
        args += ["--name", chain]
    args += ["upgrade", "head"]
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}
    result = subprocess.run(
        args, cwd=_REPO_ROOT, env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, f"{chain} upgrade failed:\n{result.stderr}"


def _scratch_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    return path


def test_catalog_relocates_to_shared_and_fk_softens():
    db_path = _scratch_db()
    try:
        # Collapsed mode: both chains run against the same database.
        _upgrade("shared", db_path)
        _upgrade("tenant", db_path)

        conn = sqlite3.connect(db_path)
        try:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            # Catalog now lives in the shared partition...
            assert "shared_mirror_known_version" in tables
            # ...and no longer in the tenant partition.
            assert "mirror_known_version" not in tables

            # Seed landed (the canonical catalog), with the corrected 26.04 row.
            count = conn.execute(
                "SELECT count(*) FROM shared_mirror_known_version"
            ).fetchone()[0]
            assert count >= 17, f"expected the seeded catalog, got {count} rows"
            label = conn.execute(
                "SELECT label FROM shared_mirror_known_version "
                "WHERE version_key = 'ubuntu-26.04'"
            ).fetchone()
            assert label and label[0] == "Ubuntu 26.04 (resolute)"

            # The soft reference: the column stays, the FK is gone.
            cols = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(mirror_repository)"
                ).fetchall()
            }
            assert "known_version_id" in cols
            fk_targets = {
                row[2]  # the referenced table
                for row in conn.execute(
                    "PRAGMA foreign_key_list(mirror_repository)"
                ).fetchall()
            }
            assert "mirror_known_version" not in fk_targets
        finally:
            conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)
