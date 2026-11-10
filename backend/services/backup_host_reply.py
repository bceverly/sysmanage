# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""What a backed-up host's configure reply says about its restate (Phase 24,
25.9): the quiesce hooks it finds present, what it can do beyond the 2.0
contract, and its network shares -- stored on the policy, and the server's
own capture job re-sent when they change it.  With restate-proxy (25.5): the
hashes of the proxy tokens the host made for itself, and whether its restate
reads through the proxy -- either changing re-sends both sides' jobs."""

import json
import re
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_network_mounts as network_mounts
from backend.services import backup_proxy as proxy
from backend.services import backup_server_paths as server_paths
from backend.services import backup_tick

_HOOK_NAME = re.compile(r"^[a-z0-9_-]{1,32}$")


def store_hooks(policy: Optional[models.BackupPolicy], hooks: Any) -> None:
    """The quiesce hooks the host's restate finds present (older agents and
    restates send none: the dialog then takes names as typed)."""
    if policy is not None and isinstance(hooks, list):
        names = sorted({h for h in hooks if isinstance(h, str) and _HOOK_NAME.match(h)})
        policy.available_hooks = json.dumps(names[:64])


_ABILITIES = (
    "list",
    "status",
    "cache",
    "decrypt",
    "verify",
    "diff",
    "packages",
    "hook_option",
    proxy.REMOTE_ABILITY,
    proxy.REMOTE_CAPTURE,
)


def store_abilities(policy: Optional[models.BackupPolicy], found: Any) -> None:
    """Browse / what changed / write cache: what the host's restate offers."""
    if policy is not None and isinstance(found, list):
        policy.host_abilities = json.dumps(sorted(set(found) & set(_ABILITIES)))


def _proxy_abilities(policy: models.BackupPolicy) -> tuple:
    """What the host's restate can do through a proxy: a change re-sends
    both sides' jobs (reads, then captures, go through it)."""
    found = set(proxy.abilities(policy))
    return (proxy.REMOTE_ABILITY in found, proxy.REMOTE_CAPTURE in found)


def store(
    db: Session, policy: Optional[models.BackupPolicy], reply: Dict[str, Any]
) -> None:
    """The host side's hooks, abilities and network shares.  When they change
    the server's own capture job -- the ``openbao`` hook found, an agent that
    takes ``hook_option`` -- its job files are re-sent now: the first
    configure could not know them (25.9)."""
    before = jobs.capture_hooks(policy) if policy is not None else None
    could = policy is not None and _proxy_abilities(policy)
    store_hooks(policy, reply.get("hooks"))
    store_abilities(policy, reply.get("abilities"))
    network_mounts.store_configured(policy, reply.get("network_mounts"))
    tokens_changed = proxy.store_tokens(policy, reply)
    if policy is None:
        return
    if (
        (server_paths.server_policy(policy) and jobs.capture_hooks(policy) != before)
        or tokens_changed
        or _proxy_abilities(policy) != could
    ):
        policy.config_version += 1
        backup_tick.configure_now(db)
