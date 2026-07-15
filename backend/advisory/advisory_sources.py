"""
Advisory / errata source registry (Phase 14.1).

Declares the vendor advisory feeds the shared catalog is built from — the
advisory analogue of ``backend/vulnerability/cve_sources.py``.  A refresh runs
**server-global** (once, into the ``shared`` partition), never per-tenant.  The
actual fetch/parse/ingest logic lives in the Pro+ ``advisory_engine`` (moat); this
registry is the OSS-side declaration of what feeds exist.
"""

from typing import Any, Dict

# Advisory feeds, keyed by source id.  ``formats`` lists the advisory-id prefixes
# a source emits (used for classification / display).
ADVISORY_SOURCES: Dict[str, Dict[str, Any]] = {
    "ubuntu": {
        "name": "Ubuntu Security Notices (USN)",
        "base_url": "https://ubuntu.com/security/notices.json",
        "description": "Canonical Ubuntu Security Notices with per-release fixes.",
        "formats": ["USN"],
        "enabled_by_default": True,
    },
    "redhat": {
        "name": "Red Hat Errata (RHSA/RHBA/RHEA)",
        "base_url": "https://access.redhat.com/hydra/rest/securitydata/",
        "description": "Red Hat security, bugfix, and enhancement advisories.",
        "formats": ["RHSA", "RHBA", "RHEA"],
        "enabled_by_default": True,
    },
    "suse": {
        "name": "SUSE / openSUSE Updates (SUSE-SU / openSUSE-SU)",
        "base_url": "https://www.suse.com/support/update/",
        "description": "SUSE and openSUSE security and recommended updates.",
        "formats": ["SUSE-SU", "openSUSE-SU"],
        "enabled_by_default": True,
    },
    "debian": {
        "name": "Debian Security Advisories (DSA)",
        "base_url": "https://www.debian.org/security/dsa.json",
        "description": "Debian Security Advisories with fixed package versions.",
        "formats": ["DSA"],
        "enabled_by_default": True,
    },
    "freebsd": {
        "name": "FreeBSD Security Advisories (FreeBSD-SA)",
        "base_url": "https://www.freebsd.org/security/advisories/",
        "description": "FreeBSD base-system security advisories.",
        "formats": ["FreeBSD-SA"],
        "enabled_by_default": False,
    },
    "openbsd": {
        "name": "OpenBSD Errata (syspatch)",
        "base_url": "https://www.openbsd.org/errata.html",
        "description": (
            "OpenBSD base-system security/reliability errata, signed with "
            "signify(1) and applied with syspatch(8).  Per-host applicability is "
            "reported authoritatively by the agent (syspatch -c), not by version "
            "comparison."
        ),
        "formats": ["OpenBSD-Errata"],
        "enabled_by_default": False,
    },
}


def default_enabled_sources() -> list:
    """Source ids enabled out of the box (used to seed refresh settings)."""
    return [k for k, v in ADVISORY_SOURCES.items() if v.get("enabled_by_default")]


def is_valid_source(source: str) -> bool:
    """Whether ``source`` is a known advisory feed id."""
    return source in ADVISORY_SOURCES
