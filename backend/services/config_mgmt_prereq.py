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
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.services import config_mgmt_engines as engines
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


# --- per-engine evaluation (Phase 20.1 multi-engine refactor) ----------------
#
# The single-engine ``evaluate`` above answers "is this host's default executor
# ready", which was the right question while there was one engine per platform.
# Once an operator can choose, the question becomes "which engines are ready
# here" -- a LIST, because a host may have several and a profile picks one.


def engine_package_pattern(engine: str, host_info: Dict[str, Any]) -> Optional[str]:
    """The installed-package name to look for, per engine, as an fnmatch glob."""
    if engine == engines.ANSIBLE:
        # Keeps the measured per-platform quirks (FreeBSD's py3* prefix,
        # Homebrew's bundle name) in one place rather than duplicating them.
        return planner.expected_package_pattern(host_info)

    kind = planner.platform_kind(host_info)
    if kind == "windows":
        # Windows package inventory does not report these the way a package
        # manager would, so there is nothing reliable to match on. That is a
        # DETECTION limit, not a platform limit -- Puppet, Salt and Chef all
        # ship Windows agents and run there perfectly well.
        return None

    family = planner.linux_distro_family(host_info) if kind == "linux" else kind
    if not family:
        return None
    package = engines.package_for(engine, family)
    return package


def evaluate_engine(
    engine: str,
    host_info: Dict[str, Any],
    installed_packages: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Readiness of ONE named engine on this host."""
    kind = planner.platform_kind(host_info)

    if engine not in engines.applicable(kind):
        return {
            "engine": engine,
            "status": STATUS_UNSUPPORTED,
            "installed_version": None,
            "can_install": False,
            "detail": "not_applicable_on_platform",
        }

    if engine in engines.VENDORED:
        # Ships with the agent. Reported as not_required rather than satisfied
        # so the UI can say "included with the agent" instead of implying
        # somebody installed it.
        return {
            "engine": engine,
            "status": STATUS_NOT_REQUIRED,
            "installed_version": None,
            "can_install": False,
            "detail": "bundled_with_agent",
        }

    pattern = engine_package_pattern(engine, host_info)
    if pattern is None:
        # Three different situations collapse to "no pattern", and the UI must
        # not describe them identically:
        #
        #   * on Windows we cannot READ the inventory for these engines, even
        #     though they run there fine -- a detection limit;
        #   * on a distro measured NOT to carry the package (Salt on Ubuntu),
        #     an install genuinely cannot work from the default repos;
        #   * anywhere else, we simply have not measured it yet.
        #
        # Calling the first of these "not available on this platform" would
        # contradict the decision that Windows is not locked to DSC.
        detail = (
            "detection_unavailable_on_windows"
            if kind == "windows"
            else "no_known_package_for_platform"
        )
        return {
            "engine": engine,
            "status": STATUS_UNSUPPORTED,
            "installed_version": None,
            "can_install": False,
            "detail": detail,
        }

    found = find_installed(installed_packages or [], pattern)
    if not found:
        return {
            "engine": engine,
            "status": STATUS_MISSING,
            "installed_version": None,
            "can_install": True,
            "detail": "not_installed",
            "package_pattern": pattern,
        }

    version = (found.get("package_version") or "").strip()
    # Only ansible-core has a measured minimum; the others have no floor we
    # have established, and inventing one would strand working hosts.
    if engine == engines.ANSIBLE and not meets_minimum(
        version, planner.MIN_ANSIBLE_CORE
    ):
        return {
            "engine": engine,
            "status": STATUS_TOO_OLD,
            "installed_version": version or None,
            "minimum_version": planner.MIN_ANSIBLE_CORE,
            "can_install": True,
            "detail": "below_minimum",
            "package_name": found.get("package_name"),
        }

    return {
        "engine": engine,
        "status": STATUS_SATISFIED,
        "installed_version": version or None,
        "can_install": False,
        "detail": None,
        "package_name": found.get("package_name"),
    }


def evaluate_all(
    host_info: Dict[str, Any],
    installed_packages: Optional[Iterable[Dict[str, Any]]] = None,
    engine_licence_available: bool = False,
) -> List[Dict[str, Any]]:
    """Readiness of every engine that could run on this host.

    ``engine_licence_available`` says whether the config_management_engine
    module is licensed AND loaded on this server; it decides whether the
    licensed adapters may offer an install.

    Ordered so the engines the host ACTUALLY HAS come first: the card should
    lead with what is available, not with a list of things the operator is
    "missing". An absent engine is not a deficiency -- a host without Puppet
    simply does not use Puppet.
    """
    packages = list(installed_packages or [])
    kind = planner.platform_kind(host_info)
    results = [
        evaluate_engine(engine, host_info, packages)
        for engine in engines.applicable(kind)
    ]
    # Mark the licensed adapters so the UI can label them. Reported as a FLAG
    # rather than by hiding the row: a Puppet shop evaluating SysManage should
    # be able to see that Puppet is supported, not conclude it is missing.
    #
    # The install button is suppressed only when the engine is licensed AND the
    # licence is absent. Suppressing it unconditionally -- which is what the
    # first cut did -- meant a customer who had just PAID for the adapters was
    # still told to go install Puppet by hand, which is precisely the friction
    # this card exists to remove.
    for row in results:
        licensed = engines.requires_license(row["engine"])
        row["requires_license"] = licensed
        if licensed and not engine_licence_available:
            row["can_install"] = False

    ready = (STATUS_SATISFIED, STATUS_NOT_REQUIRED)
    return sorted(results, key=lambda r: (r["status"] not in ready, r["engine"]))
