"""
Host selection utilities for package operations.

This module provides functions for finding appropriate hosts to perform
package-related operations based on OS and version criteria.
"""

import json
import random
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.models import Host


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

    if os_name == "Ubuntu":
        # For Ubuntu hosts, platform is "Linux" and platform_release contains "Ubuntu X.Y"
        hosts = base_query.filter(
            Host.platform == "Linux",
            Host.platform_release.like(f"{os_name} {os_version}%"),
        ).all()

    elif os_name in ["CentOS Stream", "Fedora", "RHEL", "Rocky", "AlmaLinux"]:
        # RHEL-based distributions: platform is "Linux", check platform_release
        hosts = base_query.filter(
            Host.platform == "Linux",
            Host.platform_release.like(f"{os_name} {os_version}%"),
        ).all()

    elif os_name in ["openSUSE Leap", "openSUSE Tumbleweed", "SLES"]:
        # SUSE distributions: platform is "Linux", check platform_release
        hosts = base_query.filter(
            Host.platform == "Linux",
            Host.platform_release.like(f"{os_name} {os_version}%"),
        ).all()

    elif os_name == "macOS":
        # macOS: platform is "macOS", platform_release contains version name like "Sequoia 15.6"
        hosts = base_query.filter(
            Host.platform == "macOS",
        ).all()

    elif os_name == "FreeBSD":
        # FreeBSD: platform matches, platform_release contains version (e.g., "14.3")
        hosts = base_query.filter(
            Host.platform == os_name,
            Host.platform_release.like(f"{os_version}%"),
        ).all()

    elif os_name == "NetBSD":
        # NetBSD: platform matches, platform_release contains version
        hosts = base_query.filter(
            Host.platform == os_name,
            Host.platform_release.like(f"{os_version}%"),
        ).all()

    elif os_name == "OpenBSD":
        # OpenBSD: platform matches, platform_release contains version
        hosts = base_query.filter(
            Host.platform == os_name,
            Host.platform_release.like(f"{os_version}%"),
        ).all()

    elif os_name == "Windows":
        # Windows: platform matches, check platform_release for version
        hosts = base_query.filter(
            Host.platform == "Windows",
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
        return random.choice(hosts)

    # Normalize scores to probabilities and select
    rand_value = random.uniform(0, total_score)
    cumulative = 0
    for host, score in host_scores:
        cumulative += score
        if rand_value <= cumulative:
            return host

    # Fallback (should not normally reach here)
    return hosts[0]
