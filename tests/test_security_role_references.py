# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Every ``SecurityRoles.X`` the server names must exist.

THE BUG THIS CATCHES
--------------------
``SecurityRoles.VIEW_SCRIPT`` does not exist -- the script roles are ADD, EDIT,
DELETE, RUN and DELETE_EXECUTION. Phase 21.1 S4 shipped seven read endpoints
gated on it, and every one of them returned 500 the moment a page loaded:

    AttributeError: type object 'SecurityRoles' has no attribute 'VIEW_SCRIPT'

Nothing caught it earlier because the reference sits INSIDE a handler body, so
importing the module is clean, pylint sees an attribute on an imported name,
and the service-layer tests never go through the router. It only fails when
that specific endpoint is actually called -- which, for a brand-new page, is
the first time a human opens it.

A whole-repo scan is the cheap guard: it is a typo class, it applies to every
router equally, and it costs one regex.
"""

import re
from pathlib import Path


from backend.security.roles import SecurityRoles

REPO = Path(__file__).resolve().parents[1]
# Where authorization decisions are written.  Tests are excluded: they
# legitimately construct bogus names to prove a refusal.
SCANNED = ("backend/api", "backend/services", "backend/auth", "backend/security")

_REFERENCE = re.compile(r"\bSecurityRoles\.([A-Za-z_][A-Za-z0-9_]*)")

# Attributes that are not role members but are legitimate on the enum itself.
_NOT_ROLES = {"__members__", "__name__", "__class__", "from_string"}


def _references():
    """{(file, role name)} across every scanned source file."""
    found = set()
    for folder in SCANNED:
        root = REPO / folder
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            text = path.read_text(encoding="utf-8", errors="replace")
            for name in _REFERENCE.findall(text):
                if name not in _NOT_ROLES:
                    found.add((str(path.relative_to(REPO)), name))
    return found


def test_scan_actually_finds_references():
    """A scan that silently matches nothing would pass forever."""
    assert len(_references()) > 20, "the SecurityRoles scan found almost nothing"


def test_every_named_role_exists():
    unknown = sorted(
        (path, name) for path, name in _references() if not hasattr(SecurityRoles, name)
    )
    assert not unknown, "SecurityRoles members that do not exist:\n" + "\n".join(
        f"  {path}: SecurityRoles.{name}" for path, name in unknown
    )
