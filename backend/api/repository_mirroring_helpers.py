# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Private helpers + shared constants for the Repository Mirroring API.

Extracted from ``backend.api.repository_mirroring`` to keep that module under
the line-count cap.  Everything here is re-imported back into that module so
its public surface is unchanged.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import models

logger = logging.getLogger(__name__)

# i18n message keys reused by multiple 404 raises.  Extracting them as
# module constants both deduplicates the strings (Sonar S1192) and
# keeps the translation catalog source consistent — every call site
# produces the same locale lookup key.
_MIRROR_NOT_FOUND = "Mirror not found"
_PLATFORM_CONFIG_NOT_FOUND = "Platform config not found"

# A mirror that fails this many syncs in a row is auto-disabled by the
# tick so it stops re-dispatching every cron cycle — a mirror too large
# to sync without OOMing its host would otherwise fail forever.  The
# counter resets to 0 on any successful sync (see proplus_dispatch).
_MIRROR_MAX_SYNC_FAILURES = 5


# ---------------------------------------------------------------------
# Module gate + dispatch helpers
# ---------------------------------------------------------------------


def _check_mirror_module():
    engine = module_loader.get_module("repository_mirroring_engine")
    if engine is None:
        raise HTTPException(
            status_code=402,
            detail=_(
                "Repository mirroring requires a SysManage Professional+ license. "
                "Please upgrade to access this feature."
            ),
        )
    return engine


def _check_snap_proxy_module():
    engine = module_loader.get_module("snap_proxy_engine")
    if engine is None:
        raise HTTPException(
            status_code=402,
            detail=_(
                "Snap store proxy requires a SysManage Professional+ license. "
                "Please upgrade to access this feature."
            ),
        )
    return engine


def _get_settings(db: Session) -> models.MirrorSettings:
    row = (
        db.query(models.MirrorSettings)
        .filter(models.MirrorSettings.id == models.SINGLETON_MIRROR_SETTINGS_ID)
        .first()
    )
    if row is not None:
        return row
    return models.MirrorSettings(
        id=models.SINGLETON_MIRROR_SETTINGS_ID,
        mirror_root_path="/var/mirror",
        integrity_check_cadence_hours=24,
        retention_window_days=30,
        default_bandwidth_cap_kbps=0,
        snapshot_count_to_keep=10,
    )


def _config_from_row(row: models.MirrorRepository) -> dict:
    """Project a MirrorRepository row into the dict shape the engine accepts."""
    return {
        "name": row.name,
        "package_manager": row.package_manager,
        "upstream_url": row.upstream_url,
        "suite": row.suite,
        "components": row.components,
        "architectures": row.architectures,
        "repoid": row.repoid,
        "gpgkey_url": row.gpgkey_url,
        "repo_alias": row.repo_alias,
        "release": row.release,
        "signing_key_url": row.signing_key_url,
        "bandwidth_cap_kbps": row.bandwidth_cap_kbps,
    }


def _dispatch_plan(
    plan: dict, host_id: str, action: str = "", mirror_id: str = "", timeout: int = 8400
) -> str:
    """Enqueue the plan via the standard proplus_dispatch path and register
    a result correlation so the agent's command_result lands back in the
    right OSS row (mirror_repository or mirror_setup_status).

    ``action`` and ``mirror_id`` are stamped into the correlation's
    primary_id (``"<action>:<mirror_id>"``) so the result handler in
    ``proplus_dispatch._apply_repo_mirror_op_result`` knows which row to
    update.  ``mirror_id`` is empty for host-level setup operations.
    """
    from backend.services.proplus_dispatch import (
        enqueue_apply_plan,
        register_repo_mirror_correlation,
    )

    msg_id = enqueue_apply_plan(host_id=str(host_id), plan=plan, timeout=timeout)
    if action:
        register_repo_mirror_correlation(
            msg_id, action, str(host_id), str(mirror_id) if mirror_id else ""
        )
    return msg_id


def _parse_uuid(value: Optional[str], field: str) -> Optional[uuid.UUID]:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_("Invalid UUID for %(field)s: %(value)s")
            % {"field": field, "value": value},
        ) from exc


def _platform_for_pm(pm: str) -> str:
    """Phase 10.4.3: platform == package_manager.  Each tab in the new
    UI is keyed to one PM (Ubuntu/Debian → apt, RHEL/Fedora → dnf,
    openSUSE/SLES → zypper, FreeBSD → pkg) so the platform_config
    vocabulary mirrors that 1:1."""
    return (pm or "").lower()


def _tick_mirrors_one_db(session, engine, automation, now):
    """Run the mirror tick against a SINGLE host database.

    Returns ``(fired, disabled)`` for this database.  Selecting due mirrors,
    dispatching, and recomputing ``next_sync_at`` all happen on ``session`` so a
    tenant host's mirror rows update in that tenant's DB and the sync plan is
    enqueued into that tenant's queue (``_dispatch_plan`` → ``enqueue_apply_plan``
    routes the outbound message by host_id).  Commits ``session`` on the way out.
    """
    settings = _get_settings(session)
    due = (
        session.query(models.MirrorRepository)
        .filter(models.MirrorRepository.enabled.is_(True))
        .all()
    )
    fired = []
    disabled = []
    for row in due:
        if row.next_sync_at is not None and row.next_sync_at > now:
            continue
        if (row.consecutive_sync_failures or 0) >= _MIRROR_MAX_SYNC_FAILURES:
            # Too many consecutive failures — stop re-dispatching.
            # Disable the mirror and surface why; an operator must fix
            # the root cause and re-enable it to resume syncing.
            row.enabled = False
            row.last_sync_status = "DISABLED"
            row.last_sync_error = (
                f"Auto-disabled after {row.consecutive_sync_failures} consecutive "
                "sync failures; re-enable once the cause is addressed (check host "
                "resources / prior last_sync_error)."
            )
            row.last_sync_message_id = None
            row.next_sync_at = None
            disabled.append({"mirror_id": str(row.id), "name": row.name})
            continue
        try:
            config = _config_from_row(row)
            builder = {
                "apt": engine.build_apt_mirror_sync_plan,
                "dnf": engine.build_dnf_mirror_sync_plan,
                "zypper": engine.build_zypper_mirror_sync_plan,
                "pkg": engine.build_pkg_mirror_sync_plan,
            }.get(row.package_manager)
            if builder is None:
                row.last_sync_status = "FAILURE"
                row.last_sync_error = (
                    f"unsupported package_manager: {row.package_manager}"
                )
                continue
            plan = builder(config, settings.mirror_root_path)
            msg_id = _dispatch_plan(
                plan, row.host_id, action="sync", mirror_id=str(row.id)
            )
            row.last_sync_at = now
            row.last_sync_status = "DISPATCHED"
            row.last_sync_error = None
            row.next_sync_at = automation.next_run_from_cron(
                row.sync_cron, datetime.now(timezone.utc)
            )
            fired.append(
                {
                    "mirror_id": str(row.id),
                    "name": row.name,
                    "message_id": msg_id,
                    "next_sync_at": row.next_sync_at.isoformat(),
                }
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception("Mirror tick failed for %s: %s", row.name, exc)
            row.last_sync_status = "FAILURE"
            row.last_sync_error = str(exc)
    session.commit()
    return fired, disabled
