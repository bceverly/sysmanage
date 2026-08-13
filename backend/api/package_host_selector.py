# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Host selection utilities for package operations.

This module provides functions for finding appropriate hosts to perform
package-related operations based on OS and version criteria.
"""

import json
import random
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.persistence.models import Host

# The (os_name, os_version) <-> (platform, platform_release) convention lives
# HERE and nowhere else.  An agent reports a DISTRIBUTION ("Ubuntu", "26.04")
# while the host record stores a PLATFORM ("Linux") plus a platform_release
# that already contains the distro name ("Ubuntu 26.04").  Comparing those
# field-for-field is the bug that made every Linux host re-send its entire
# ~89k package catalog forever: handle_packages_batch_start rejected the batch
# with os_mismatch, so the catalog never landed, so the "no rows for this OS"
# check re-requested it on the next OS update, indefinitely.  FreeBSD hid it,
# because there the distribution and the platform are both "FreeBSD".
LINUX_DISTROS = [
    "Ubuntu",
    "CentOS Stream",
    "Fedora",
    "RHEL",
    "Rocky",
    "AlmaLinux",
    "openSUSE Leap",
    "openSUSE Tumbleweed",
    "SLES",
]

# BSD variants: platform matches os_name, platform_release contains version only
BSD_VARIANTS = ["FreeBSD", "NetBSD", "OpenBSD"]


def _matches_linux(platform: str, release: str, os_name: str, os_version: str) -> bool:
    """Linux distros, which the host record spells in two different shapes.

    Canonical: platform "Linux" with the distro name inside platform_release
    ("Ubuntu 26.04").  Tolerated: some rows carry the distro as the platform
    itself ("Ubuntu" / "22.04").

    Accepting both is deliberate.  A false REJECT is the expensive direction --
    the catalog never lands and the server re-requests it for ever -- while this
    still rejects a genuine cross-OS report, because a Fedora agent matches
    neither shape of an Ubuntu host row.
    """
    if platform == "Linux":
        return release.startswith(f"{os_name} {os_version}")
    return platform == os_name and release.startswith(os_version)


def host_matches_os(host: Host, os_name: str, os_version: str) -> bool:
    """Does ``host`` actually run the OS an agent claims to report packages for?

    The in-Python counterpart of :func:`find_hosts_for_os`, which expresses the
    same convention as SQL filters.  Both read the module constants above so a
    new distro cannot be added to one and forgotten in the other.

    Deliberately permissive when the host's OS is not yet known: a host that has
    registered but not yet reported platform details must not have its packages
    rejected, because that failure mode is silent and self-perpetuating.
    """
    platform = (host.platform or "").strip()
    release = (host.platform_release or "").strip()
    if not platform or not release:
        return True  # unknown OS on the host record: nothing to contradict

    if os_name in LINUX_DISTROS:
        return _matches_linux(platform, release, os_name, os_version)

    if os_name == "macOS":
        # platform_release is a marketing name + version ("Sequoia 15.6"), which
        # the agent does not send, so the platform alone is the check.
        return platform == "macOS"

    if os_name in BSD_VARIANTS or os_name == "Windows":
        expected = os_name if os_name in BSD_VARIANTS else "Windows"
        return platform == expected and release.startswith(os_version)

    return platform == os_name and release.startswith(os_version)


def find_hosts_for_os(db: Session, os_name: str, os_version: str) -> List[Host]:
    """
    Find active, approved hosts matching the specified OS and version.

    Args:
        db: Database session
        os_name: Operating system name (e.g., "Ubuntu", "FreeBSD", "Windows")
        os_version: Operating system version (e.g., "24.04", "14.3", "11")

    Returns:
        List of matching hosts

    Note:
        - platform_release contains "Distribution Version" (e.g., "Ubuntu 24.04")
        - platform_version contains kernel version info
    """
    base_query = db.query(Host).filter(
        Host.active.is_(True),
        Host.approval_status == "approved",
    )

    linux_distros = LINUX_DISTROS
    bsd_variants = BSD_VARIANTS

    if os_name in linux_distros:
        # Linux distributions: platform is "Linux", platform_release is "DistroName Version"
        hosts = base_query.filter(
            Host.platform == "Linux",
            Host.platform_release.like(f"{os_name} {os_version}%"),
        ).all()

    elif os_name == "macOS":
        # macOS: platform is "macOS", platform_release contains version name like "Sequoia 15.6"
        hosts = base_query.filter(
            Host.platform == "macOS",
        ).all()

    elif os_name in bsd_variants or os_name == "Windows":
        # BSD and Windows: platform matches os_name, platform_release contains version
        hosts = base_query.filter(
            Host.platform == os_name if os_name in bsd_variants else "Windows",
            Host.platform_release.like(f"{os_version}%"),
        ).all()

    else:
        # Fallback: try direct matching on platform_release
        hosts = base_query.filter(
            Host.platform == os_name,
            Host.platform_release.like(f"{os_version}%"),
        ).all()

    return hosts


def score_host(host: Host) -> int:
    """
    Score a host based on the number of package managers available.

    Hosts with more package managers get higher scores, making them more
    likely to be selected for package operations.

    Args:
        host: The host to score

    Returns:
        Integer score (higher is better)
    """
    base_score = 1  # Every host gets a base score

    # Parse enabled shells to count package managers
    if host.enabled_shells:
        try:
            enabled_shells = json.loads(host.enabled_shells)
            # Count optional package managers (homebrew, chocolatey, etc.)
            optional_managers = 0
            for shell_name in enabled_shells:
                shell_lower = shell_name.lower()
                if any(
                    mgr in shell_lower
                    for mgr in [
                        "homebrew",
                        "brew",
                        "chocolatey",
                        "choco",
                        "flatpak",
                        "snap",
                        "pip",
                        "npm",
                    ]
                ):
                    optional_managers += 1
            return base_score + optional_managers
        except (json.JSONDecodeError, TypeError):
            pass

    return base_score


def select_best_host(hosts: List[Host]) -> Optional[Host]:
    """
    Select the best host from a list, with bias towards hosts with more package managers.

    Uses weighted random selection where hosts with higher scores (more package managers)
    are more likely to be selected.

    Args:
        hosts: List of candidate hosts

    Returns:
        Selected host, or None if the list is empty
    """
    if not hosts:
        return None

    if len(hosts) == 1:
        return hosts[0]

    # Calculate scores for all hosts
    host_scores = [(host, score_host(host)) for host in hosts]

    # Weighted random selection
    total_score = sum(score for _, score in host_scores)
    if total_score == 0:
        # If all scores are 0, just pick randomly
        return random.choice(hosts)  # nosec B311  # NOSONAR

    # Normalize scores to probabilities and select
    rand_value = random.uniform(0, total_score)  # nosec B311  # NOSONAR
    cumulative = 0
    for host, score in host_scores:
        cumulative += score
        if rand_value <= cumulative:
            return host

    # Fallback (should not normally reach here)
    return hosts[0]
