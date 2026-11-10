# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Can a host reach its backup storage? (ROADMAP Phase 24)

A backed-up host mounts its repository from the storage host over NFSv4: one
TCP port, 2049, at the storage host's address.  The server asks each host's
agent to open a connection there (``check_backup_storage``, the address and
nothing else) and keeps the last answer per host in ``backup_reach``.  A
host that cannot reach it is not offered backups -- Equip, a policy, Back up
now, the bulk actions and the scheduler all pass it by -- with a message
saying so, rather than failing every night (production, 2026-10-30: the
server's own cloud droplet and the home NAS).

Behind NAT (25.8): a host on a private network behind another reaches the
port, but the storage host sees its traffic come from the gateway, so the
export made for the host's own address refuses the mount.  When the storage
host's agent can list who it sees on port 2049 (``list_nfs_peers``), the
check holds its connection open (HOLD_SECONDS) and reports its source port;
the storage host is asked at once, the connection is found by that port, and
an address other than the one the export names is kept (``seen_as``).  Such
a host is not offered backups either, with what to do instead.  Never is an
export widened to the gateway's address: every host behind it could mount
the repository.  NAT that rewrites the source port is not recognized, and
then nothing is said.

Through restate-proxy (25.5) what a host must reach is the proxy: its
address and port as the target names them.  The check is then sent the
port and how the proxy's certificate is trusted (a site CA, a pinned key),
and the agent completes a TLS handshake as restate's curl will, so a host
that reaches the port but would refuse the certificate is told so too.  NAT
does not apply: the proxy knows hosts by their token, never their address.
An agent too old to check a proxy answers for port 2049, and that answer is
not kept (unknown).

Never-checked, still-checking, or checked against another address or port
(the storage host moved, the target changed transport) is unknown, and
unknown never blocks.  Checks are asked
for when a host has none for the current address, once a day after that,
and on "Check again".
"""

import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence import models
from backend.services import agent_capability_service as capabilities
from backend.services import backup_jobs as jobs
from backend.services import backup_proxy as proxy

logger = logging.getLogger(__name__)

GROUP = "backup_reach"
COMMAND = "check_backup_storage"
PEERS_GROUP = "backup_peers"
PEERS_COMMAND = "list_nfs_peers"
# How long the host holds its connection open for the storage host to look.
HOLD_SECONDS = 60
PORT = 2049
UNREACHABLE = "storage_unreachable"
RECHECK_AFTER = timedelta(days=1)
# A check unanswered this long (agent away) may be asked again.
ANSWER_WITHIN = timedelta(minutes=10)


def storage_address(db: Session) -> Optional[Dict[str, Any]]:
    """``{"address", "port", "host_id", "fqdn", "proxy"}`` of what hosts must
    reach: the storage host as they mount from it (its IPv4, port 2049,
    backup_jobs.nfs_source), or the target's restate-proxy (``proxy``: what
    the agent's TLS check needs).  None when there is no storage host."""
    target = jobs.the_target(db)
    storage = jobs.storage_host(db, target)
    if storage is None:
        return None
    found = {"host_id": storage.id, "fqdn": storage.fqdn, "proxy": None}
    if proxy.uses_proxy(target):
        port = target.proxy_port or proxy.DEFAULT_PORT
        check = {"port": port}
        if target.proxy_pin_sha256:
            check["pin_sha256"] = target.proxy_pin_sha256
        if target.proxy_ca_pem:
            check["ca"] = target.proxy_ca_pem
        return dict(found, address=target.proxy_host, port=port, proxy=check)
    address = jobs.host_address(storage)
    if not address:
        return None
    return dict(found, address=address, port=PORT)


def _row(db: Session, host_id: Any) -> Optional[models.BackupReach]:
    return (
        db.query(models.BackupReach)
        .filter(models.BackupReach.host_id == host_id)
        .first()
    )


def can_check(host: models.Host) -> bool:
    """The host's agent has the check (its capability report says so)."""
    report = capabilities.get_capability_report(host) or {}
    return GROUP in (report.get("capabilities") or [])


def state(db: Session, host: models.Host) -> Optional[Dict[str, Any]]:
    """The last answer for the current storage address, or None (unknown)."""
    storage = storage_address(db)
    row = _row(db, host.id)
    if storage is None or row is None or not _same(row, storage):
        return None
    if row.reachable is None:
        return None
    return {
        "reachable": bool(row.reachable),
        "seen_as": row.seen_as,
        "host_address": jobs.host_address(host),
        "address": row.address,
        "port": row.port,
        "storage_fqdn": storage["fqdn"],
        "error": row.error,
        "checked_at": row.checked_at.isoformat() if row.checked_at else None,
        "proxy": storage["proxy"] is not None,
    }


def _same(row: models.BackupReach, storage: Dict[str, Any]) -> bool:
    """The row is an answer for what hosts must reach now."""
    return row.address == storage["address"] and (row.port or PORT) == storage["port"]


def blocked(db: Session, host: models.Host) -> bool:
    """Known not to reach the storage, or behind NAT (unknown never blocks)."""
    found = state(db, host)
    return found is not None and (not found["reachable"] or bool(found["seen_as"]))


def message(db: Session, host: models.Host) -> str:
    """Why backups are not offered to this host."""
    found = state(db, host) or {}
    if found.get("proxy"):
        return _(
            "This host cannot reach the backup storage's restate-proxy "
            "(%(address)s, port %(port)s): %(error)s. Backups need a network "
            "path to it, and a certificate this host trusts."
        ) % {
            "address": found.get("address") or "",
            "port": found.get("port") or "",
            "error": found.get("error") or "",
        }
    if found.get("reachable") and found.get("seen_as"):
        return _(
            "This host is behind NAT: the backup storage (%(storage)s) sees "
            "it as %(seen)s, not %(address)s, so it refuses the mount. Put the "
            "host on the storage host's network (a bridged network for a "
            "virtual machine) instead of behind its NAT."
        ) % {
            "storage": found.get("storage_fqdn") or "",
            "seen": found["seen_as"],
            "address": jobs.host_address(host) or "",
        }
    return _(
        "This host cannot reach the backup storage (%(storage)s, %(address)s, "
        "NFS port %(port)s). Backups need a network path to it."
    ) % {
        "storage": found.get("storage_fqdn") or "",
        "address": found.get("address") or "",
        "port": found.get("port") or PORT,
    }


def due(db: Session, host: models.Host, now=None) -> bool:
    """A check is wanted: none for the current address, the last one is a
    day old, or one asked for went unanswered."""
    storage = storage_address(db)
    if storage is None or str(storage["host_id"]) == str(host.id):
        return False  # the storage host does not mount its own storage
    now = now or jobs.now()
    row = _row(db, host.id)
    if row is None or not _same(row, storage):
        return True
    if row.checked_at is None or row.requested_at > row.checked_at:
        return row.requested_at + ANSWER_WITHIN <= now
    return row.checked_at + RECHECK_AFTER <= now


def start(db: Session, host: models.Host, force: bool = False) -> Optional[str]:
    """Ask the host's agent to check; its command id, or None when it was
    not asked (no storage, no capability, or not due).  The caller commits."""
    # pylint: disable=import-outside-toplevel
    from backend.services.config_mgmt_dispatch import queue_command  # noqa: PLC0415
    from backend.websocket.messages import CommandType  # noqa: PLC0415

    storage = storage_address(db)
    if storage is None or not can_check(host) or not (force or due(db, host)):
        return None
    if str(storage["host_id"]) == str(host.id):
        return None
    parameters: Dict[str, Any] = {"address": storage["address"]}
    if storage["proxy"] is not None:
        parameters["proxy"] = storage["proxy"]
    elif _storage_lists_peers(db, storage["host_id"]):
        parameters["hold_seconds"] = HOLD_SECONDS
    command_id = queue_command(
        db, host.id, CommandType.CHECK_BACKUP_STORAGE, parameters
    )
    row = _row(db, host.id) or models.BackupReach(host_id=host.id)
    if not _same(row, storage):
        row.reachable, row.error, row.checked_at = None, None, None
        row.seen_as, row.nat_checked_at = None, None
    row.address, row.port = storage["address"], storage["port"]
    row.command_id, row.requested_at = command_id, jobs.now()
    row.local_port, row.peers_command_id = None, None
    db.add(row)
    db.flush()  # its answer finds it by command id
    return command_id


def record_result(db: Session, host_id: Any, message_data: Dict[str, Any]) -> bool:
    """The agent's answer.  False when it answers none of ours, or is not an
    answer (an invalid address the agent refused).  The caller commits."""
    command_id = message_data.get("command_id")
    row = (
        db.query(models.BackupReach)
        .filter(models.BackupReach.command_id == str(command_id))
        .first()
        if command_id
        else None
    )
    if row is None or str(row.host_id) != str(host_id):
        logger.warning(
            "check_backup_storage result from host %s for unknown command %s ignored",
            host_id,
            command_id,
        )
        return False
    outcome = message_data.get("result") or {}
    if isinstance(outcome.get("result"), dict):
        outcome = outcome["result"]  # the agent wraps its handler's answer
    if not isinstance(outcome.get("reachable"), bool):
        logger.warning(
            "check_backup_storage from host %s gave no answer: %s",
            host_id,
            outcome.get("error") or message_data.get("error"),
        )
        return False
    if outcome.get("port") not in (None, row.port):
        # An agent too old to check a proxy answered for NFS's port.
        logger.info(
            "check_backup_storage from host %s was for port %s, not %s: ignored",
            host_id,
            outcome.get("port"),
            row.port,
        )
        return False
    row.reachable = outcome["reachable"]
    row.error = str(outcome.get("error") or "")[:255] or None
    tls = outcome.get("tls")
    if row.reachable and isinstance(tls, dict) and tls.get("ok") is not True:
        # The port answers, but this host would refuse the certificate.
        row.reachable = False
        row.error = f"TLS: {tls.get('error') or 'failed'}"[:255]
    row.checked_at = jobs.now()
    port = outcome.get("local_port")
    if row.port != PORT:
        port = None  # restate-proxy: NAT does not apply
    if row.reachable and isinstance(port, int) and not isinstance(port, bool):
        row.local_port = port
        _ask_storage_for_peers(db, row)
    if not row.reachable:
        logger.info(
            "Host %s cannot reach its backup storage at %s:%s (%s)",
            host_id,
            row.address,
            row.port,
            row.error,
        )
    return True


def _storage_host(db: Session, host_id: Any) -> Optional[models.Host]:
    return db.query(models.Host).filter(models.Host.id == host_id).first()


def _storage_lists_peers(db: Session, storage_id: Any) -> bool:
    storage = _storage_host(db, storage_id)
    report = (capabilities.get_capability_report(storage) or {}) if storage else {}
    return PEERS_GROUP in (report.get("capabilities") or [])


def _ask_storage_for_peers(db: Session, row: models.BackupReach) -> None:
    """While the host holds its connection open: who does the storage host
    see on port 2049?  Asked only of a storage agent that can answer."""
    # pylint: disable=import-outside-toplevel
    from backend.services.config_mgmt_dispatch import queue_command  # noqa: PLC0415
    from backend.websocket.messages import CommandType  # noqa: PLC0415

    storage = storage_address(db)
    if storage is None or storage["address"] != row.address:
        return
    if not _storage_lists_peers(db, storage["host_id"]):
        return
    row.peers_command_id = queue_command(
        db, storage["host_id"], CommandType.LIST_NFS_PEERS, {}
    )


def _peers(outcome: Dict[str, Any]) -> Optional[list]:
    peers = outcome.get("peers")
    if not isinstance(peers, list):
        return None
    found = []
    for peer in peers[:500]:
        if not isinstance(peer, dict):
            continue
        address, port = peer.get("address"), peer.get("port")
        if isinstance(address, str) and isinstance(port, int):
            found.append((address[:255], port))
    return found


def record_peers(db: Session, storage_id: Any, message_data: Dict[str, Any]) -> bool:
    """The storage host's answer to ``list_nfs_peers``: the host's held
    connection, found by its source port, and the address it came from.
    False when it answers none of ours.  The caller commits."""
    command_id = message_data.get("command_id")
    row = (
        db.query(models.BackupReach)
        .filter(models.BackupReach.peers_command_id == str(command_id))
        .first()
        if command_id
        else None
    )
    storage = storage_address(db)
    if row is None or storage is None or str(storage["host_id"]) != str(storage_id):
        logger.warning(
            "list_nfs_peers result from host %s for unknown command %s ignored",
            storage_id,
            command_id,
        )
        return False
    outcome = message_data.get("result") or {}
    if isinstance(outcome.get("result"), dict):
        outcome = outcome["result"]  # the agent wraps its handler's answer
    peers = _peers(outcome)
    host = _storage_host(db, row.host_id)
    if peers is None or host is None:
        return False
    seen = sorted({address for address, port in peers if port == row.local_port})
    exported = jobs.host_address(host)
    # Only one address on that port is an answer; none, or several (two
    # hosts happen to share the port), is unknown, and unknown never blocks.
    row.seen_as = (
        seen[0] if len(seen) == 1 and exported and seen[0] != exported else None
    )
    row.nat_checked_at = jobs.now()
    if row.seen_as:
        logger.info(
            "Host %s is behind NAT: the storage host sees it as %s, not %s",
            row.host_id,
            row.seen_as,
            exported,
        )
    return True


def refuse_if_blocked(db: Session, host: models.Host) -> None:
    """HTTP 409 with the reason, for an action that needs the storage."""
    # pylint: disable=import-outside-toplevel
    from fastapi import HTTPException  # noqa: PLC0415

    if blocked(db, host):
        raise HTTPException(status_code=409, detail=message(db, host))
