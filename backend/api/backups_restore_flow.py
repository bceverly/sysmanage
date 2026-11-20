# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Sending a restore, once it has been checked and (with four-eyes approval,
27.2) approved.  One path for both: ``POST /host/{id}/backup-restore`` when
no approval is needed, and the approval of a held request -- so an approved
restore is exactly the restore that was asked for."""

from typing import Any, Dict, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_views as views
from backend.services.audit_service import EntityType


def perform(  # pylint: disable=too-many-arguments
    db: Session,
    current_user,
    host: models.Host,
    policy: models.BackupPolicy,
    body,
    approved_by: Optional[str] = None,
) -> Dict[str, Any]:
    """Queue the restore ``body`` describes; the caller has checked the host,
    the policy and the body.  ``approved_by``: the second person who
    approved it (four-eyes), recorded in the audit entry."""
    # pylint: disable-next=import-outside-toplevel
    from backend.api.backups import (
        _audit,
        _readable_repository,
        _restore_audit_text,
        key_needed,
    )

    snapshot = (
        db.query(models.BackupSnapshot)
        .filter(
            models.BackupSnapshot.policy_id == policy.id,
            models.BackupSnapshot.name == body.snapshot,
            models.BackupSnapshot.gone_at.is_(None),
        )
        .first()
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail=_("Snapshot not found"))
    where = _readable_repository(snapshot, policy, host)
    # Only a real restore needs the operator to accept an unsigned snapshot: a
    # preview (dry run) writes nothing on the host (Bryan, 2026-10-30).
    if not snapshot.signed and not body.dry_run and not body.acknowledge_unsigned:
        raise HTTPException(
            status_code=409,
            detail=_("This snapshot is not signed; confirm to restore it anyway"),
        )
    run = jobs.queue_restore(
        db,
        policy,
        host,
        snapshot.name,
        body.include,
        body.dry_run,
        allow_unverified=not snapshot.signed,
        actor=current_user.userid,
        exclude=body.exclude,
        in_place=body.in_place,
        previous=where == jobs.PREVIOUS,
        needs_key=key_needed(where, policy),
        packages=body.packages,
    )
    details = {
        "run_id": str(run.id),
        "snapshot": snapshot.name,
        "include": body.include,
        "exclude": body.exclude,
        "dry_run": body.dry_run,
        "in_place": body.in_place,
        "packages": body.packages,
        "unsigned_acknowledged": not snapshot.signed and body.acknowledge_unsigned,
    }
    if approved_by:
        details["approved_by"] = approved_by
    _audit(
        db,
        current_user,
        EntityType.HOST,
        host.id,
        host.fqdn,
        _restore_audit_text(body),
        details,
    )
    db.commit()
    out = views.run_dict(run)
    out["in_place"] = body.in_place
    out["staging_path"] = None if body.in_place else jobs.staging_dir(run.id)
    return out
