# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
OS lifecycle source registry (Phase 14.3).

Declares the feeds the shared OS support-lifecycle / EOL registry is built from —
the lifecycle analogue of ``backend/vulnerability/cve_sources.py`` and
``backend/advisory/advisory_sources.py``.  A refresh runs **server-global** (once,
into the ``shared`` partition), never per-tenant.  The fetch/parse/ingest logic
lives in the Pro+ ``lifecycle_engine``; this registry is the OSS declaration.

``endoflife.date`` is the primary source: a well-maintained, machine-readable
lifecycle database (``/api/<product>.json`` → cycles with release/eol/support
dates, LTS + latest).  The ``products`` map normalises our OS names to its slugs.
"""

from typing import Any, Dict

LIFECYCLE_SOURCES: Dict[str, Dict[str, Any]] = {
    "endoflife.date": {
        "name": "endoflife.date",
        "base_url": "https://endoflife.date/api",
        "description": "Machine-readable OS support-lifecycle / EOL database.",
        "enabled_by_default": True,
        # our normalised os_name -> endoflife.date product slug
        "products": {
            "ubuntu": "ubuntu",
            "debian": "debian",
            "fedora": "fedora",
            "rhel": "rhel",
            "redhat": "rhel",
            "centos": "centos",
            "almalinux": "almalinux",
            "rocky": "rocky-linux",
            "opensuse": "opensuse",
            "suse": "sles",
            "freebsd": "freebsd",
            "macos": "macos",
            "windows": "windows",
        },
    },
}


def default_enabled_sources() -> list:
    """Source ids enabled out of the box."""
    return [k for k, v in LIFECYCLE_SOURCES.items() if v.get("enabled_by_default")]


def product_slug(source: str, os_name: str):
    """Map a normalised OS name to the source's product slug (or None)."""
    src = LIFECYCLE_SOURCES.get(source) or {}
    return (src.get("products") or {}).get((os_name or "").lower())
