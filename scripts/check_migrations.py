#!/usr/bin/env python3
"""
Guard against non-expand-contract migrations (Phase 13.1).

SysManage migrates a fleet of databases incrementally — control-plane chains
first, then each tenant DB one at a time (``sysmanage-migrate``).  During that
window the SAME running code serves migrated and not-yet-migrated databases, so
migrations MUST be **backward-compatible / expand-contract**: add things now,
remove them in a LATER release once every database is past the add.

This scans each migration's ``upgrade()`` for destructive DDL that breaks that
rule — dropping/renaming tables/columns/constraints — and fails if it finds any.
``downgrade()`` is exempt (drops there are expected).

A genuinely-safe drop (e.g. the contract half of an expand-contract pair, run a
release after the column stopped being used) can be allowlisted by putting
``# expand-contract-ok: <reason>`` on or just above the offending line.

Usage:  python scripts/check_migrations.py
Exit:   0 = clean, 1 = violations found.
"""

import ast
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_MIGRATION_DIRS = [
    _REPO_ROOT / "alembic" / "versions",
    _REPO_ROOT / "alembic" / "registry" / "versions",
    _REPO_ROOT / "alembic" / "shared" / "versions",
]

# alembic ``op.<name>(...)`` calls that are destructive in an upgrade.
_DESTRUCTIVE_OPS = {"drop_table", "drop_column", "drop_constraint", "rename_table"}
# Raw-SQL destructive patterns inside op.execute("...").
_DESTRUCTIVE_SQL = re.compile(
    r"\b(drop\s+table|drop\s+column|rename\s+to|rename\s+column|alter\s+table\s+\w+\s+rename)\b",
    re.IGNORECASE,
)
_ALLOW = "expand-contract-ok"


def _allowlisted(source_lines, lineno) -> bool:
    """True if the offending line (or the line above) carries the marker."""
    for ln in (lineno - 1, lineno - 2):  # 0-based index = lineno-1; and one above
        if 0 <= ln < len(source_lines) and _ALLOW in source_lines[ln]:
            return True
    return False


def _scan_upgrade(func: ast.FunctionDef, source_lines, path):
    findings = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        func_node = node.func
        # op.<destructive>(...) or op.alter_column(..., new_column_name=...)
        if isinstance(func_node, ast.Attribute):
            attr = func_node.attr
            if attr in _DESTRUCTIVE_OPS:
                if not _allowlisted(source_lines, node.lineno):
                    findings.append((node.lineno, f"op.{attr}(...)"))
            elif attr == "alter_column":
                for kw in node.keywords:
                    if kw.arg == "new_column_name" and not _allowlisted(
                        source_lines, node.lineno
                    ):
                        findings.append((node.lineno, "op.alter_column(rename)"))
            elif attr == "execute":
                for arg in node.args:
                    if (
                        isinstance(arg, ast.Constant)
                        and isinstance(arg.value, str)
                        and _DESTRUCTIVE_SQL.search(arg.value)
                        and not _allowlisted(source_lines, node.lineno)
                    ):
                        findings.append((node.lineno, "op.execute(destructive SQL)"))
    return findings


def _check_file(path: Path):
    source = path.read_text()
    source_lines = source.splitlines()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [(0, f"syntax error: {exc}")]
    findings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            findings.extend(_scan_upgrade(node, source_lines, path))
    return findings


def main() -> int:
    total = 0
    for d in _MIGRATION_DIRS:
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.py")):
            for lineno, what in _check_file(path):
                rel = path.relative_to(_REPO_ROOT)
                print(f"{rel}:{lineno}: destructive DDL in upgrade(): {what}")
                total += 1
    if total:
        print(
            f"\n[FAIL] {total} non-expand-contract operation(s) found. Migrations "
            "must be backward-compatible across the fleet — see "
            "docs/migration-expand-contract.md. If a drop is the intentional "
            "contract step (a release after the add), add "
            f"'# {_ALLOW}: <reason>' to the line."
        )
        return 1
    print("[OK] No non-expand-contract migrations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
