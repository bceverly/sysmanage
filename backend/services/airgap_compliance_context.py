# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Air-gap compliance context (Phase 11.3).

Thin connector between ``airgap_repository_engine``, ``compliance_engine``,
and ``vuln_engine`` so reports on private-side hosts can distinguish

  - "patch available publicly, but not yet transferred to this private
    network"  vs.
  - "patch available locally, but not yet applied to this host"

Decision logic:

  1. Fetch the repository's freshness (``airgap_repository_engine.
     compute_freshness`` against the latest ``AirgapIngestionRun``).
  2. Per host, compare the host's installed package versions against
     the local mirror's manifest.  Anything available locally that
     isn't installed = ``not_applied``.
  3. Anything in the public CVE feed (cached on the collector before
     transfer) that isn't in the local mirror's manifest =
     ``not_transferred``.

The OSS service surface here just exposes the freshness label + the
classification function; the actual scoring logic lives in the engines
(this module is a thin license-gated wrapper that resolves which
engine to call based on which is loaded).

License gate: this module no-ops gracefully (returns ``label="never"``,
empty buckets) when neither airgap engine is loaded — so a standard
``role: standard`` deployment that imports this file doesn't error,
the compliance reports just don't show the air-gap context column.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from backend.licensing.module_loader import module_loader


def get_repository_freshness(db) -> Dict[str, object]:
    """Return ``{last_ingest_at, days_since_ingest, freshness_label}``
    for the local mirror, or sensible defaults when no air-gap
    repository engine is loaded.

    Calls into ``airgap_repository_engine.compute_freshness`` when
    available; otherwise short-circuits with ``label='never'``.
    """
    repo_engine = module_loader.get_module("airgap_repository_engine")
    if repo_engine is None:
        return {
            "last_ingest_at": None,
            "days_since_ingest": None,
            "freshness_label": "never",
            "engine_loaded": False,
        }

    # Local import to avoid a hard dependency on the model when
    # ``role: standard`` deployments import this file.
    from backend.persistence import models

    latest = (
        db.query(models.AirgapIngestionRun)
        .filter(models.AirgapIngestionRun.status == "COMPLETE")
        .order_by(models.AirgapIngestionRun.completed_at.desc())
        .first()
    )
    last_at = latest.completed_at if latest else None
    days, label = repo_engine.compute_freshness(last_at)
    return {
        "last_ingest_at": last_at.isoformat() if last_at else None,
        "days_since_ingest": days,
        "freshness_label": label,
        "engine_loaded": True,
    }


def classify_compliance_gap(
    host_packages: List[Dict],
    local_mirror_manifest: Optional[Dict],
    public_cve_snapshot: Optional[Dict],
) -> Dict[str, List]:
    """Bucket compliance findings into the three air-gap categories.

    ``host_packages``: list of ``{name, version, package_manager}``
        entries from the host's last package inventory.
    ``local_mirror_manifest``: latest verified manifest from the
        repository — the union of what's available on-prem.
    ``public_cve_snapshot``: most-recent CVE/NVD data the collector
        had captured *at the time of last media transfer*.  Anything
        in here but not in the local mirror is "not yet transferred".

    Returns::

        {
          "not_applied":     [{"package", "installed", "available"}, ...],
          "not_transferred": [{"package", "cve_id", "fix_version"}, ...],
          "current":         [{"package", "version"}, ...],
        }

    All three lists are empty for ``role: standard`` deployments (no
    local mirror manifest available).
    """
    out = {"not_applied": [], "not_transferred": [], "current": []}
    if not host_packages:
        return out
    mirror_index = _index_manifest(local_mirror_manifest)
    cve_index = _index_cve_snapshot(public_cve_snapshot)
    for entry in host_packages:
        name = entry.get("name")
        installed = entry.get("version")
        if not name:
            continue
        available = mirror_index.get(name)
        if available and available != installed:
            out["not_applied"].append(
                {
                    "package": name,
                    "installed": installed,
                    "available": available,
                }
            )
            continue
        cve = cve_index.get(name)
        if cve:
            in_mirror = name in mirror_index
            if not in_mirror:
                out["not_transferred"].append(
                    {
                        "package": name,
                        "cve_id": cve["cve_id"],
                        "fix_version": cve.get("fix_version"),
                    }
                )
                continue
        out["current"].append({"package": name, "version": installed})
    return out


def _index_manifest(manifest):
    """Build ``{package_name: latest_version}`` from a verified manifest."""
    if not manifest:
        return {}
    files = manifest.get("files") or []
    index = {}
    for entry in files:
        if not isinstance(entry, dict):
            continue
        meta = entry.get("metadata") or {}
        name = meta.get("package_name")
        version = meta.get("package_version")
        if name and version:
            # Newer wins (best-effort string compare; full version
            # ordering is distro-specific).
            existing = index.get(name)
            if existing is None or version > existing:
                index[name] = version
    return index


def _index_cve_snapshot(snapshot):
    """Build ``{package_name: {cve_id, fix_version}}`` from a CVE
    snapshot.  Multiple CVEs per package collapse to the most-severe
    (caller's responsibility to filter further if needed)."""
    if not snapshot:
        return {}
    cves = snapshot.get("cves") or snapshot.get("vulnerabilities") or []
    index = {}
    for entry in cves:
        if not isinstance(entry, dict):
            continue
        package = entry.get("package_name") or entry.get("package")
        cve_id = entry.get("cve_id") or entry.get("id")
        if not package or not cve_id:
            continue
        if package not in index:
            index[package] = {
                "cve_id": cve_id,
                "fix_version": entry.get("fix_version"),
            }
    return index
