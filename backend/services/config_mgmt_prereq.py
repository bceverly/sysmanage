# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Is a host ready to run Phase 20.1 config-management profiles?

WHY THIS READS EXISTING DATA RATHER THAN ASKING THE AGENT
---------------------------------------------------------
The obvious design is a new agent probe reporting "ansible-core 2.21.1".  It
is also the expensive one, and unnecessary: the agent ALREADY reports its
installed packages into ``software_package`` (name, version, manager), so the
server can answer both "is it there" and "which version" from data it collects
anyway.  No new agent code, no capability-schema change, no extra round trip.

``capability_probes`` deliberately cannot help here either -- its own design
rules forbid subprocess execution because it runs on every registration and
every live query, and reading a version means running ``ansible --version``.

WHAT THIS COSTS, STATED PLAINLY
-------------------------------
1. Freshness is bounded by the software-inventory cadence, so immediately
   after an install the status can still read "missing" until the next
   collection.  The caller should trigger a refresh after dispatching an
   install rather than pretending the answer is live.
2. It only sees PACKAGE-MANAGER installs.  Somebody who installed via pipx or
   from source is invisible here and will read as missing even though the host
   works.  That is the right failure direction -- we under-claim readiness
   rather than over-claim it -- but it is a false negative, not a truth.
"""

import fnmatch
import re
from typing import Any, Dict, Iterable, Optional, Tuple

from backend.services import config_mgmt_plan_builder as planner

# Status values the UI renders.  Deliberately three, not two: "not_required"
# is not the same as "satisfied", and a Windows host that vendors its executor
# should not be shown the same affordance as a Linux host that happens to have
# ansible installed.
STATUS_SATISFIED = "satisfied"
STATUS_MISSING = "missing"
STATUS_TOO_OLD = "too_old"
STATUS_NOT_REQUIRED = "not_required"
STATUS_UNSUPPORTED = "unsupported"


def _version_tuple(version: str) -> Tuple[int, ...]:
    """Leading numeric components of a version, as ints.

    String comparison is WRONG for versions -- "2.9" sorts above "2.20"
    lexically, which would report a host running 2.9 as satisfying a 2.20
    floor.  Non-numeric suffixes (rc1, _1, -p8) are ignored rather than
    guessed at.
    """
    parts = []
    for chunk in re.split(r"[.\-_+~]", (version or "").strip()):
        match = re.match(r"^(\d+)", chunk)
        if not match:
            break
        parts.append(int(match.group(1)))
    return tuple(parts)


def meets_minimum(installed: str, minimum: str) -> bool:
    """True when ``installed`` is at least ``minimum``.

    An unparseable installed version returns False: we would rather ask an
    operator to look than silently treat an unknown as good enough.
    """
    got = _version_tuple(installed)
    want = _version_tuple(minimum)
    if not got or not want:
        return False
    # Compare on the shorter length so "2.21" satisfies a "2.20" floor without
    # needing equal component counts.
    width = min(len(got), len(want))
    return got[:width] >= want[:width]


def find_installed(
    packages: Iterable[Dict[str, Any]], pattern: str
) -> Optional[Dict[str, Any]]:
    """The first installed package whose name matches ``pattern``."""
    for package in packages or []:
        name = (package.get("package_name") or "").strip()
        if name and fnmatch.fnmatch(name, pattern):
            return package
    return None


def evaluate(
    host_info: Dict[str, Any],
    installed_packages: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Describe this host's readiness to run config-management profiles.

    ``installed_packages`` is rows from ``software_package`` for the host,
    each carrying at least ``package_name`` and ``package_version``.
    """
    executor = planner.executor_for(host_info)
    minimum = planner.MIN_ANSIBLE_CORE

    if not planner.requires_install(host_info):
        # Windows: dsc.exe ships with the agent.  Report it as not-required
        # rather than satisfied so the UI can say "included with the agent"
        # instead of implying somebody installed something.
        return {
            "executor": executor,
            "status": STATUS_NOT_REQUIRED,
            "installed_version": None,
            "minimum_version": None,
            "can_install": False,
            "detail": "bundled_with_agent",
        }

    pattern = planner.expected_package_pattern(host_info)
    if pattern is None:
        # A platform we have no measured install path for.  Say so rather than
        # offering a button that dispatches a plan we know will fail.
        return {
            "executor": executor,
            "status": STATUS_UNSUPPORTED,
            "installed_version": None,
            "minimum_version": minimum,
            "can_install": False,
            "detail": "no_known_package_for_platform",
        }

    found = find_installed(installed_packages or [], pattern)
    if not found:
        return {
            "executor": executor,
            "status": STATUS_MISSING,
            "installed_version": None,
            "minimum_version": minimum,
            "can_install": True,
            "detail": "not_installed",
            "package_pattern": pattern,
        }

    version = (found.get("package_version") or "").strip()
    if not meets_minimum(version, minimum):
        # Present but too old.  Still offer the install button: on every
        # platform measured, the packaged version is already >= the floor, so
        # an upgrade is the realistic remedy.
        return {
            "executor": executor,
            "status": STATUS_TOO_OLD,
            "installed_version": version or None,
            "minimum_version": minimum,
            "can_install": True,
            "detail": "below_minimum",
            "package_name": found.get("package_name"),
        }

    return {
        "executor": executor,
        "status": STATUS_SATISFIED,
        "installed_version": version,
        "minimum_version": minimum,
        "can_install": False,
        "detail": None,
        "package_name": found.get("package_name"),
    }
