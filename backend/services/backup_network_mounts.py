# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The network shares a host's backup leaves out, kept on its policy.

An older restate walks into a network filesystem, so the agent leaves the
host's network and automount points out with a rules file of its own, and
says which at configure.  A restate that skips them itself
(``skips_network_mounts``) says at configure only that it does
(``native``), and each capture's result names what it actually skipped
(``skipped_network_mounts``, each ``path`` and ``type``): that is what the
policy then shows, until the next capture.
"""

import json
from typing import Any, Dict, List, Optional

from backend.persistence import models

_MAX_PATHS = 200
_MAX_PATH = 1024
_MAX_TYPE = 64


def _paths(value: Any) -> List[str]:
    """At most 200 absolute paths of at most 1024 characters."""
    if not isinstance(value, list):
        return []
    found = [p for p in value if isinstance(p, str) and p.startswith("/")]
    return [p for p in found if len(p) <= _MAX_PATH][:_MAX_PATHS]


def _known(policy: models.BackupPolicy) -> Dict[str, Any]:
    try:
        known = json.loads(policy.network_mounts or "null")
    except ValueError:
        return {}
    return known if isinstance(known, dict) else {}


def _skipped(value: Any) -> List[Dict[str, str]]:
    """restate's ``skipped_network_mounts``: each ``path`` and ``type``."""
    if not isinstance(value, list):
        return []
    found = []
    for entry in value:
        if not isinstance(entry, dict) or not _paths([entry.get("path")]):
            continue
        kind = entry.get("type")
        kind = kind[:_MAX_TYPE] if isinstance(kind, str) else ""
        found.append({"path": entry["path"], "type": kind})
    return found[:_MAX_PATHS]


def store_configured(policy: Optional[models.BackupPolicy], found: Any) -> None:
    """What the host's agent reported at configure (an older agent reports
    nothing, which leaves what was known).  A native restate's configure
    names nothing left out: what its last capture skipped stays shown."""
    if policy is None or not isinstance(found, dict):
        return
    native = bool(found.get("native"))
    stored: Dict[str, Any] = {
        "excluded": _paths(found.get("excluded")),
        "kept": _paths(found.get("kept")),
        "native": native,
    }
    known = _known(policy)
    if native and known.get("native") and "skipped" in known:
        stored["excluded"] = _paths(known.get("excluded"))
        stored["skipped"] = _skipped(known.get("skipped"))
    policy.network_mounts = json.dumps(stored)


def store_captured(policy: Optional[models.BackupPolicy], result: Any) -> None:
    """What a capture by a restate that skips network mounts itself left
    out.  A result without ``skipped_network_mounts`` (an older restate,
    whose leave-outs are the agent's rules) changes nothing."""
    if policy is None or not isinstance(result, dict):
        return
    if not isinstance(result.get("skipped_network_mounts"), list):
        return
    skipped = _skipped(result["skipped_network_mounts"])
    policy.network_mounts = json.dumps(
        {
            "excluded": [entry["path"] for entry in skipped],
            "kept": _paths(_known(policy).get("kept")),
            "native": True,
            "skipped": skipped,
        }
    )
