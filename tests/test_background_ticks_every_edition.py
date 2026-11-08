# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The background ticks start in every edition (found 2026-11-06).

``start_licensed_ticks()`` sat inside startup's ``if
license_service.is_pro_plus_active:`` branch, so a Community server never ran
the backup scheduler -- the one Community tick: no scheduled capture, no
prune, and a host that moved address kept an export for the old one (the
server-loss drill).  Each tick gates itself on its own license, so startup
must call them whatever the edition.
"""

import ast
from pathlib import Path

LIFECYCLE = Path(__file__).resolve().parents[1] / "backend/startup/lifecycle.py"


def _parents(tree):
    found = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            found[child] = node
    return found


def test_the_ticks_are_not_started_only_under_a_pro_plus_license():
    tree = ast.parse(LIFECYCLE.read_text(encoding="utf-8"))
    parents = _parents(tree)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", None) == "start_licensed_ticks"
    ]
    assert len(calls) == 1
    node = calls[0]
    while node in parents:
        node = parents[node]
        if isinstance(node, ast.If):
            assert "is_pro_plus_active" not in ast.unparse(node.test)
