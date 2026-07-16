# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
CI guard: each Alembic partition chain only creates tables with its prefix
(Phase 13.1.D, design §5).

  * the ``registry`` chain creates only ``registry_*`` tables,
  * the ``shared`` chain creates only ``shared_*`` tables,
  * the ``tenant`` chain creates NEITHER prefix (its tables are unprefixed).

This keeps the partition convention from rotting as the schema evolves —
especially in the unprefixed tenant chain, where a stray ``registry_``/
``shared_`` table would silently break split-ability.  Each chain is run on an
isolated scratch SQLite database and its created tables are inspected.
"""

import os
import sqlite3
import subprocess
import sys
import tempfile

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _run_chain(chain: str, db_path: str) -> list:
    """Run a chain's ``upgrade head`` on a scratch SQLite; return its tables."""
    args = [sys.executable, "-m", "alembic"]
    if chain != "tenant":  # tenant is the default (unnamed) section
        args += ["--name", chain]
    args += ["upgrade", "head"]
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}
    result = subprocess.run(
        args, cwd=_REPO_ROOT, env=env, capture_output=True, text=True, check=False
    )
    assert (
        result.returncode == 0
    ), f"alembic upgrade for chain {chain!r} failed:\n{result.stderr}"
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        conn.close()
    return [
        r[0]
        for r in rows
        if not r[0].startswith("alembic_version") and not r[0].startswith("sqlite_")
    ]


def _scratch_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)  # let alembic/sqlite create it fresh
    return path


def test_registry_chain_only_creates_registry_prefixed_tables():
    db = _scratch_db()
    try:
        tables = _run_chain("registry", db)
        assert tables, "registry chain created no tables (expected registry_*)"
        offenders = [t for t in tables if not t.startswith("registry_")]
        assert (
            not offenders
        ), f"registry chain created non-registry_ tables: {offenders}"
    finally:
        _safe_unlink(db)


def test_shared_chain_only_creates_shared_prefixed_tables():
    db = _scratch_db()
    try:
        tables = _run_chain("shared", db)
        offenders = [t for t in tables if not t.startswith("shared_")]
        assert not offenders, f"shared chain created non-shared_ tables: {offenders}"
    finally:
        _safe_unlink(db)


def test_tenant_chain_creates_no_partitioned_prefix_tables():
    db = _scratch_db()
    try:
        tables = _run_chain("tenant", db)
        offenders = [
            t for t in tables if t.startswith("registry_") or t.startswith("shared_")
        ]
        assert not offenders, (
            f"tenant chain created registry_/shared_ tables (must be unprefixed): "
            f"{offenders}"
        )
    finally:
        _safe_unlink(db)


def _safe_unlink(path):
    try:
        os.unlink(path)
    except OSError:
        # Best-effort cleanup of a temp file; a missing/locked file is fine to
        # ignore (the OS reclaims it), so don't fail the test over it.
        pass
