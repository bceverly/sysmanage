#!/usr/bin/env python3
"""Round-trip Alembic migrations to catch non-reversible upgrades.

Phase 8 will ship at least 5 new tables (AccessGroup, RegistrationKey,
UpgradeProfile, PackageProfile, HostComplianceStatus). A migration whose
``downgrade()`` doesn't faithfully undo its ``upgrade()`` only fails in
production when an operator rolls back — which is the worst possible
moment to discover the bug.

Strategy:

  1. Boot DB at current ``head`` (CI's ``alembic upgrade head`` step
     already does this; we run AFTER that).
  2. Capture the canonical schema (``pg_dump --schema-only``, with
     non-deterministic noise stripped).
  3. ``alembic downgrade -1`` then ``alembic upgrade head`` — round
     the most recent migration through its full down/up cycle.
  4. Capture the schema again.  Diff the two snapshots.  Any
     difference is a round-trip failure.

Exits 0 on success, 1 on any error or detected schema drift.

The script is invoked from ``.github/workflows/integration-tests.yml``
under a dedicated ``migration-roundtrip`` job.  It can also be run
locally against a disposable Postgres if you set ``DATABASE_URL``.
"""

# pylint: disable=missing-function-docstring,broad-exception-caught

import os
import re
import subprocess  # nosec B404 — orchestrating local CLI tools
import sys
import tempfile
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a subprocess; on failure, print stdout/stderr and re-raise."""
    print(f"$ {' '.join(cmd)}", flush=True)
    return subprocess.run(  # nosec B603 — argv is constructed in this file, not user input
        cmd,
        check=True,
        text=True,
        cwd=REPO_ROOT,
        **kwargs,
    )


def _alembic(*args: str) -> None:
    """Run an alembic command via the python -c trampoline so we don't
    rely on the alembic binary being on PATH (which it isn't in some
    minimal CI Pythons)."""
    code = (
        "from alembic.config import Config; from alembic import command; "
        f"cfg = Config('alembic.ini'); command.{args[0]}(cfg, *{list(args[1:])!r})"
    )
    _run([sys.executable, "-c", code])


def _dump_schema(db_url: str, out_path: Path) -> None:
    """pg_dump --schema-only into out_path, stripped of cosmetic noise.

    Removes:
      - timestamp lines (``-- Dumped on ...``) which differ run-to-run
      - server-version comments which differ across CI / local
      - SET-statement noise that varies by client version
    Leaves:  CREATE/ALTER for every object.  That's the schema contract.
    """
    raw = out_path.with_suffix(".raw.sql")
    with open(raw, "w", encoding="utf-8") as fh:
        subprocess.run(  # nosec B603,B607 — pg_dump invocation w/ CI-controlled URL
            ["pg_dump", "--schema-only", "--no-owner", "--no-privileges", db_url],
            check=True,
            stdout=fh,
            cwd=REPO_ROOT,
        )

    text = raw.read_text(encoding="utf-8")
    # Drop comment lines that vary cosmetically.
    cleaned: List[str] = []
    skip_patterns = [
        re.compile(r"^-- Dumped (from|by) .*"),
        re.compile(r"^-- Started on .*"),
        re.compile(r"^-- Completed on .*"),
        re.compile(r"^-- TOC entry .*"),
        re.compile(r"^-- Name: .* Type: COMMENT.*"),
        re.compile(r"^SET .*"),
        re.compile(r"^SELECT pg_catalog\.set_config.*"),
        # \restrict / \unrestrict are per-dump random session-lock tokens
        # added by pg_dump 17+ to prevent concurrent modifications during
        # the dump.  They differ between every pg_dump invocation by
        # design — strip them so they don't false-positive as drift.
        re.compile(r"^\\(?:un)?restrict .*"),
        re.compile(r"^\s*$"),
    ]
    for line in text.splitlines():
        if any(p.match(line) for p in skip_patterns):
            continue
        cleaned.append(line)
    out_path.write_text("\n".join(cleaned) + "\n", encoding="utf-8")


def main() -> int:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL is not set", file=sys.stderr)
        return 1

    print("=== Migration round-trip test ===")
    print(f"Working directory: {REPO_ROOT}")
    print(f"Database:         {re.sub(r':[^@]+@', ':***@', db_url)}")

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        before = tmpdir / "schema-before.sql"
        after = tmpdir / "schema-after.sql"

        try:
            print("\n[1/4] Ensuring DB is at head...")
            _alembic("upgrade", "head")

            print("\n[2/4] Capturing baseline schema...")
            _dump_schema(db_url, before)
            baseline_size = before.stat().st_size
            print(f"      schema-before.sql: {baseline_size} bytes")

            print("\n[3/4] Round-tripping latest migration (downgrade -1 → upgrade head)...")
            _alembic("downgrade", "-1")
            _alembic("upgrade", "head")

            print("\n[4/4] Capturing post-roundtrip schema...")
            _dump_schema(db_url, after)
            roundtrip_size = after.stat().st_size
            print(f"      schema-after.sql:  {roundtrip_size} bytes")

        except subprocess.CalledProcessError as e:
            print(f"\nFAIL: alembic / pg_dump command exited {e.returncode}", file=sys.stderr)
            return 1

        # Diff the two snapshots.  Identical = round-trip works.
        try:
            diff = subprocess.run(  # nosec B603,B607
                ["diff", "-u", str(before), str(after)],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
        except FileNotFoundError:
            print("ERROR: `diff` binary not on PATH", file=sys.stderr)
            return 1

        if diff.returncode == 0:
            print("\nPASS: schema is byte-identical after round-trip.")
            return 0

        print("\nFAIL: schema drifted after downgrade -1 / upgrade head.", file=sys.stderr)
        print("--- diff (truncated to 200 lines) ---", file=sys.stderr)
        for line in diff.stdout.splitlines()[:200]:
            print(line, file=sys.stderr)
        print("--- end diff ---", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
