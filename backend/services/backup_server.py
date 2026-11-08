# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The SysManage server backs itself up (ROADMAP 25.9, Community).

Production's server had no backup at all on 2026-11-02.  The server is
already a managed host (its own agent), so its backup is that host's policy,
marked ``server_preset`` and started from backup_server_paths.preset().

Which host is this server: the approved host whose name is this machine's
(``socket.getfqdn()`` or ``gethostname()``), or, failing a match, the one
the operator picks.  Only a suggestion -- the operator confirms it, and a
marked policy is what counts from then on.

:func:`status` is what the Backups page and the dashboard card warn on while
the server has no good backup.  Under multi-tenancy the server's host is in
one tenant only, so a tenant with no match and no marked policy is not
warned ("unknown").
"""

import socket
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.config import config
from backend.i18n import _
from backend.persistence import models
from backend.services import backup_escrow
from backend.services import backup_jobs as jobs
from backend.services import backup_server_paths as server_paths

# The server host's own backup states that count as a good backup.
GOOD_STATES = ("ok", "incomplete", "running", "waiting_window")


def _names() -> List[str]:
    names = []
    for name in (socket.getfqdn(), socket.gethostname()):
        name = (name or "").strip().rstrip(".").lower()
        if name and name not in ("localhost", "localhost.localdomain"):
            names.append(name)
    return names


def candidates(db: Session) -> List[models.Host]:
    """Approved hosts named as this machine is: the full name first, then
    the short name when no full name matches."""
    names = _names()
    if not names:
        return []
    hosts = (
        db.query(models.Host)
        .filter(models.Host.approval_status == "approved")
        .order_by(models.Host.fqdn)
        .all()
    )
    fqdn = [h for h in hosts if (h.fqdn or "").lower().rstrip(".") in names]
    if fqdn:
        return fqdn
    shorts = {n.split(".")[0] for n in names}
    return [h for h in hosts if (h.fqdn or "").lower().split(".")[0] in shorts]


def marked(db: Session) -> Optional[models.BackupPolicy]:
    return (
        db.query(models.BackupPolicy)
        .filter(models.BackupPolicy.server_preset.is_(True))
        .first()
    )


def mirror_roots(db: Session, host_id) -> List[str]:
    """Package mirrors kept on this host: fetched again, so left out."""
    rows = (
        db.query(models.MirrorPlatformConfig)
        .filter(models.MirrorPlatformConfig.host_id == host_id)
        .all()
    )
    return [r.mirror_root_path for r in rows if r.mirror_root_path]


def preset(db: Session, host_id) -> Dict[str, Any]:
    return server_paths.preset(mirror_roots(db, host_id))


def _multitenant() -> bool:
    return bool((config.get_multitenancy_config() or {}).get("enabled"))


def status(db: Session, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """``{"status", "host_id", "fqdn", "warn", "host_status"}``; status is
    ``ok``, ``no_good_backup`` (a marked policy, no good capture in time),
    ``no_policy`` (the server's host found, nothing marked) or ``unknown``."""
    by_id = {row["host_id"]: row for row in rows}
    policy = marked(db)
    found: Dict[str, Any] = {"host_id": None, "fqdn": None, "host_status": None}
    if policy is not None:
        row = by_id.get(str(policy.host_id))
        good = bool(row and row["last_good_capture"] and row["status"] in GOOD_STATES)
        found.update(
            host_id=str(policy.host_id),
            fqdn=row["fqdn"] if row else None,
            host_status=row["status"] if row else None,
            status="ok" if good else "no_good_backup",
        )
    else:
        hosts = candidates(db)
        found["status"] = "no_policy" if hosts else "unknown"
        if len(hosts) == 1:
            found.update(host_id=str(hosts[0].id), fqdn=hosts[0].fqdn)
    found["warn"] = found["status"] in ("no_good_backup", "no_policy") or (
        found["status"] == "unknown" and not _multitenant()
    )
    return found


def mark(db: Session, policy: models.BackupPolicy) -> Optional[models.BackupPolicy]:
    """Make ``policy`` the server's; returns the one it replaces, if any (the
    server moved to another machine), which goes back to an ordinary policy."""
    previous = marked(db)
    if previous is not None and previous.id != policy.id:
        previous.server_preset = False
        previous.config_version += 1
    else:
        previous = None
    policy.server_preset = True
    return previous


# Pro+ (25.9): the server's own backup is encrypted to the operator's
# break-glass escrow PUBLIC key -- never to a key in its own OpenBAO, which
# restoring OpenBAO would need first.
NO_ESCROW_KEY = _(
    "Save a break-glass escrow key first: the SysManage server's own backup is "
    "encrypted to it, so restoring OpenBAO never needs a key kept inside OpenBAO"
)


def encrypt_to_escrow(db: Session, engine, policy, host, target) -> Dict[str, Any]:
    """Point the server's policy at the escrow key (backup_engine)."""
    db.flush()  # a new policy needs its id for its key row
    return engine.escrow_encryption(
        db, policy, host, target, jobs.current_repository_has_snapshots(db, policy)
    )


def rekey_to_escrow(db: Session, target) -> Optional[models.BackupPolicy]:
    """A new escrow key saved: the server's policy moves to it (Pro+)."""
    engine = backup_escrow.backup_engine()
    policy = marked(db)
    if engine is None or policy is None or target is None:
        return None
    host = db.query(models.Host).filter(models.Host.id == policy.host_id).first()
    if host is None:
        return None
    encrypt_to_escrow(db, engine, policy, host, target)
    return policy


def encryption(db: Session) -> Dict[str, Any]:
    """What the server dialog says about encryption: Community (none), or
    Pro+ with the escrow key it uses, and whether the policy uses it yet."""
    if backup_escrow.backup_engine() is None:
        return {"available": False}
    target = jobs.the_target(db)
    policy = marked(db)
    escrow = getattr(target, "escrow_fingerprint", None) if target else None
    return {
        "available": True,
        "escrow_fingerprint": escrow,
        "encrypted": bool(
            policy is not None
            and jobs.escrow_keyed(policy)
            and policy.encrypt_fingerprint == escrow
        ),
    }


def refusal(error: Exception) -> Exception:
    """An engine refusal or key failure as the HTTP answer; anything else
    (an HTTPException from the policy checks included) as it was."""
    name = type(error).__name__
    if name == "EncryptionRefused":
        return HTTPException(status_code=409, detail=str(error))
    if name == "BackupKeyError":
        return HTTPException(status_code=503, detail=str(error))
    return error
