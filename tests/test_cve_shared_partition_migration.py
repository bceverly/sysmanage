"""Functional guard for the CVE → shared-partition relocation (option B).

Exercises the *real* migrations end-to-end on a scratch SQLite database in the
production order (shared chain renames before the tenant chain drops), proving:

  * an EXISTING deployment's populated ``vulnerability`` rows survive the move
    (renamed in place to ``shared_vulnerability``), and
  * the old tenant-side CVE tables + the cross-partition FK on
    ``host_vulnerability_finding`` are removed.

Plus a FRESH-install check: the shared chain creates empty ``shared_*`` CVE
tables when there is nothing to rename.
"""

import contextlib
import os
import sqlite3
import subprocess
import sys
import tempfile

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Revision just before the tenant-chain drop (the pre-relocation tenant head).
_TENANT_PRE_DROP = "f1apikey01"


def _alembic(args, db_path):
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"alembic {args} failed:\n{result.stderr}"


def _tables(db_path):
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        conn.close()
    return {r[0] for r in rows}


def _scratch_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    return path


def _safe_unlink(path):
    with contextlib.suppress(OSError):
        os.unlink(path)


def test_existing_deployment_preserves_cve_rows_and_drops_old():
    db = _scratch_db()
    try:
        # 1. Bring the tenant chain to the pre-relocation head (creates the old
        #    unprefixed CVE tables + host_vulnerability_finding w/ its FK).
        _alembic(["upgrade", _TENANT_PRE_DROP], db)
        assert "vulnerability" in _tables(db)

        # 2. Seed populated CVE data + a finding referencing it (FK enforcement is
        #    off by default in sqlite3, so parent scan/host rows aren't required).
        conn = sqlite3.connect(db)
        try:
            conn.execute(
                "INSERT INTO vulnerability (id, cve_id, created_at, updated_at) "
                "VALUES ('v1','CVE-2026-0001','2026-01-01','2026-01-01')"
            )
            conn.execute(
                "INSERT INTO package_vulnerability "
                "(id, vulnerability_id, package_name, package_manager, "
                "created_at, updated_at) "
                "VALUES ('p1','v1','openssl','apt','2026-01-01','2026-01-01')"
            )
            conn.execute(
                "INSERT INTO host_vulnerability_finding "
                "(id, scan_id, vulnerability_id, package_name, installed_version, "
                "severity) VALUES ('f1','s1','v1','openssl','1.1.1','HIGH')"
            )
            conn.commit()
        finally:
            conn.close()

        # 3. Shared chain runs first (production order) → rename in place.
        _alembic(["--name", "shared", "upgrade", "head"], db)
        # 4. Tenant chain to head → drops old tables + the cross-partition FK.
        _alembic(["upgrade", "head"], db)

        tables = _tables(db)
        # Old tenant-side CVE tables are gone; shared_* hold the data.
        assert "vulnerability" not in tables
        assert "package_vulnerability" not in tables
        assert "cve_refresh_settings" not in tables
        assert "shared_vulnerability" in tables
        assert "shared_package_vulnerability" in tables

        conn = sqlite3.connect(db)
        try:
            # The populated row survived the relocation.
            row = conn.execute(
                "SELECT cve_id FROM shared_vulnerability WHERE id='v1'"
            ).fetchone()
            assert row is not None and row[0] == "CVE-2026-0001"
            # The finding survived (tenant-local) ...
            assert (
                conn.execute(
                    "SELECT vulnerability_id FROM host_vulnerability_finding "
                    "WHERE id='f1'"
                ).fetchone()[0]
                == "v1"
            )
            # ... and no longer has a FK to the (now shared) CVE table.
            fks = conn.execute(
                "PRAGMA foreign_key_list(host_vulnerability_finding)"
            ).fetchall()
            referred = {fk[2] for fk in fks}  # column 2 = referenced table
            assert "vulnerability" not in referred
            assert "shared_vulnerability" not in referred
        finally:
            conn.close()
    finally:
        _safe_unlink(db)


def test_fresh_install_creates_empty_shared_cve_tables():
    db = _scratch_db()
    try:
        # Shared chain alone (fresh DB, nothing to rename) must create the
        # shared_* CVE tables so first-run scans have somewhere to read.
        _alembic(["--name", "shared", "upgrade", "head"], db)
        tables = _tables(db)
        for expected in (
            "shared_vulnerability",
            "shared_package_vulnerability",
            "shared_vulnerability_ingestion_log",
            "shared_cve_refresh_settings",
        ):
            assert expected in tables, f"missing {expected}"
    finally:
        _safe_unlink(db)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
