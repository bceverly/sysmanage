#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Gate: a route handler that never awaits must not be ``async def``.

THE BUG THIS CATCHES
--------------------
FastAPI runs an ``async def`` handler ON the event loop and a plain ``def``
handler in its thread pool.  A handler that makes blocking calls (SQLAlchemy,
files, subprocesses) and awaits nothing therefore blocks the loop for as long
as each call takes -- and when it waits for a pooled database connection,
nothing else runs, including the coroutines that would give a connection back.
Production stalled 30 s that way on 2026-11-18 (``update_agent``, a tenant pool
of 2 + 6, every host asked to upgrade at once).

A handler that awaits nothing gains nothing from ``async``, so the rule is
simple: no ``await`` (or ``async for`` / ``async with``) in the body means
plain ``def`` -- unless the ``def`` line says ``# loop-safe: <reason>``: a
handler with no blocking call at all that must answer from the event loop
even when every worker thread is busy (``/api/health``).  It does NOT catch a handler that awaits AND makes blocking
calls -- those are reviewed one by one (their blocking part goes through
``run_in_threadpool``).

THE ALLOWLIST ONLY SHRINKS
--------------------------
When this gate arrived about 800 handlers broke the rule.  They are listed in
``scripts/async-handlers-allowlist.txt`` and converted a slice at a time.  A
handler NOT on the list fails the gate; a listed handler that has been fixed
(or removed) also fails until its line is removed -- ``--prune`` does that.
Nothing ever adds to the list: a new handler is written correctly instead.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import Iterator, List, Set

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO / "backend"
ALLOWLIST = REPO / "scripts" / "async-handlers-allowlist.txt"
ROUTE = re.compile(r"^(router|app|api_router|[a-z_]*router)\.(get|post|put|patch|delete|api_route)\b")
_AWAITS = (ast.Await, ast.AsyncFor, ast.AsyncWith)


def _is_route(node: ast.AsyncFunctionDef) -> bool:
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if ROUTE.match(ast.unparse(target)):
            return True
    return False


def _awaits(node: ast.AsyncFunctionDef) -> bool:
    """Does the handler's OWN body await?  Nested functions do not count."""
    stack = list(node.body)
    while stack:
        current = stack.pop()
        if isinstance(current, _AWAITS):
            return True
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        stack.extend(ast.iter_child_nodes(current))
    return False


LOOP_SAFE = re.compile(r"#\s*loop-safe:\s*\S")


def _loop_safe(lines: List[str], node: ast.AsyncFunctionDef) -> bool:
    """``async`` on purpose: the ``def`` line says ``# loop-safe: <reason>``.

    For a handler that makes no blocking call at all and must answer from the
    event loop even when every worker thread is busy -- ``/api/health``, which
    every agent polls every second (2026-11-18).  The reason is required."""
    return bool(LOOP_SAFE.search(lines[node.lineno - 1]))


def offenders(root: Path | None = None) -> Iterator[str]:
    """``path:function`` for every async route handler that never awaits."""
    root = root or ROOT
    for path in sorted(root.rglob("*.py")):
        if "tests" in path.parts or "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        rel = path.relative_to(REPO).as_posix()
        lines = path.read_text(encoding="utf-8").splitlines()
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and _is_route(node):
                if not _awaits(node) and not _loop_safe(lines, node):
                    yield f"{rel}:{node.name}"


def read_allowlist(path: Path | None = None) -> List[str]:
    path = path or ALLOWLIST
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


_HEADER = """\
# Route handlers that are `async def` but never await -- converted a slice at a
# time to plain `def` (see scripts/check_async_handlers.py).  This list only
# shrinks: never add to it.  `make lint-async-handlers-prune` removes the
# entries that have been fixed.
"""


def write_allowlist(entries: List[str], path: Path | None = None) -> None:
    path = path or ALLOWLIST
    path.write_text(_HEADER + "".join(f"{e}\n" for e in sorted(entries)), encoding="utf-8")


def _report_new(new: List[str]) -> None:
    print(f"FAIL: {len(new)} route handler(s) are `async def` but never await:")
    for entry in new:
        print(f"  {entry}")
    print(
        "\n"
        "What is wrong: FastAPI runs an `async def` handler on the event loop, so\n"
        "its blocking calls (the database above all) stall the whole server while\n"
        "they wait.  This is a problem in the code named above, not in the gate.\n"
        "To fix it:\n"
        "  1. Change `async def` to `def` on each handler listed.  FastAPI then runs\n"
        "     it in its thread pool; nothing else about it changes.\n"
        "  2. If a test calls the handler with `await`, call it directly instead\n"
        "     (and drop its `@pytest.mark.asyncio`).\n"
        "  3. If the handler really must stay async, it awaits something -- and then\n"
        "     this gate does not flag it.  Do NOT add it to the allowlist."
    )


def _report_stale(stale: List[str]) -> None:
    print(f"FAIL: {len(stale)} allowlist entr(y/ies) no longer break the rule (fixed or gone):")
    for entry in stale:
        print(f"  {entry}")
    print(
        "\n"
        "Good news -- these were converted.  The allowlist only shrinks, so:\n"
        "  1. Run `make lint-async-handlers-prune` (it removes exactly these lines).\n"
        "  2. Commit scripts/async-handlers-allowlist.txt with the change."
    )


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--prune", action="store_true",
                        help="remove fixed entries from the allowlist (never adds)")  # fmt: skip
    args = parser.parse_args(argv)

    found: Set[str] = set(offenders())
    allowed = read_allowlist()
    if args.prune:
        kept = [e for e in allowed if e in found]
        write_allowlist(kept)
        print(f"Pruned {len(allowed) - len(kept)} fixed entr(y/ies); {len(kept)} remain.")
        return 0

    new = sorted(found - set(allowed))
    stale = sorted(set(allowed) - found)
    if new:
        _report_new(new)
    if stale:
        if new:
            print()
        _report_stale(stale)
    if new or stale:
        return 1
    print(f"OK: no new async-without-await route handlers ({len(allowed)} left to convert)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
