# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The storage host's append-only audit, summarized for the target (24.1/24.5).

The storage host's agent audits each repository it serves (read-only; see
the agent's ``backup/storage_audit.py``) and reports findings with every
configure and storage job.  Here they become the target's warnings:

* host-wide findings -- the NFS server, NFSv4, local locks, the v4 root,
  the service account -- once;
* per-repository findings -- its own filesystem, its own export, the export
  restricted to the host and mapped to the account, the append-only layout
  -- with the hosts they affect.

Each becomes the warning code ``audit_<code>``; an ``error`` counts the
target as a problem on the dashboard.
"""

import json
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from backend.persistence import models

HOST_WIDE = (
    "nfs_server",
    "nfs_v4",
    "nfs_v4_only",
    "nfs_local_locks",
    "nfs_v4_root",
    "service_account",
)
_RANK = {"error": 2, "warning": 1, "ok": 0}


def _findings(policy: models.BackupPolicy) -> List[Dict[str, Any]]:
    try:
        found = json.loads(policy.storage_audit) if policy.storage_audit else []
    except ValueError:
        return []
    return [f for f in found if isinstance(f, dict) and f.get("level") in _RANK]


def summarize(db: Session, target: models.BackupTarget) -> Dict[str, Dict[str, Any]]:
    """``{code: {level, hosts, params}}`` for every finding that is not ok,
    the worst level across the repositories; ``hosts`` empty when host-wide."""
    out: Dict[str, Dict[str, Any]] = {}
    policies = (
        db.query(models.BackupPolicy)
        .filter(models.BackupPolicy.target_id == target.id)
        .all()
    )
    for policy in policies:
        for finding in _findings(policy):
            if finding["level"] == "ok":
                continue
            code = finding["code"]
            entry = out.setdefault(
                code,
                {"level": "ok", "hosts": [], "params": finding.get("params") or {}},
            )
            if _RANK[finding["level"]] > _RANK[entry["level"]]:
                entry["level"] = finding["level"]
                entry["params"] = finding.get("params") or {}
            if code not in HOST_WIDE and str(policy.host_id) not in entry["hosts"]:
                entry["hosts"].append(str(policy.host_id))
    return out


def warnings(summary: Dict[str, Dict[str, Any]]) -> List[str]:
    """Warning codes, errors first, then warnings, each sorted by code."""
    ordered = sorted(summary.items(), key=lambda kv: (-_RANK[kv[1]["level"]], kv[0]))
    return [f"audit_{code}" for code, _entry in ordered]


def has_error(summary: Dict[str, Dict[str, Any]]) -> bool:
    return any(entry["level"] == "error" for entry in summary.values())
