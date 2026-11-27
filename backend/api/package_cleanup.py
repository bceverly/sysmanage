# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Old kernels and unneeded packages on one host (ROADMAP 27.8, all editions).

``GET  /host/{id}/cleanup``        the kernels (running, installed, proven),
                                   what is protected and why, recent runs
``POST /host/{id}/cleanup/plan``   ask the agent what it would remove
``POST /host/{id}/cleanup/apply``  remove exactly the approved packages

Planning needs nothing beyond reading the host; applying needs Remove
Package.  The protections are the server's (``kernel_boots.protected``) and
are re-checked by the agent; an approved list never removes a protected
kernel.
"""

import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import kernel_boots, package_cleanup
from backend.services.audit_service import ActionType, AuditService, EntityType

router = APIRouter(dependencies=[Depends(JWTBearer())])


class ApplyBody(BaseModel):
    packages: List[str] = Field(..., min_length=1, max_length=5000)


def _host_or_404(db: Session, host_id: str) -> models.Host:
    try:
        key = uuid.UUID(host_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": "host_not_found"}) from exc
    host = db.get(models.Host, key)
    if host is None or host.approval_status != "approved":
        raise HTTPException(status_code=404, detail={"code": "host_not_found"})
    return host


def _audit(db, current_user, host, description: str, details) -> None:
    AuditService.log(
        db=db, action_type=ActionType.EXECUTE, entity_type=EntityType.HOST,
        entity_id=str(host.id), entity_name=host.fqdn, description=description,
        user_id=current_user.id, username=current_user.userid, details=details,
    )  # fmt: skip


@router.get("/host/{host_id}/cleanup")
def cleanup_state(
    host_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),  # pylint: disable=unused-argument
) -> Dict[str, Any]:
    """Kernels, protections and recent cleanup runs for one host."""
    host = _host_or_404(db, host_id)
    installed = sorted(package_cleanup.installed_kernels(db, host),
                       key=kernel_boots.version_key, reverse=True)  # fmt: skip
    refusal, keep = kernel_boots.protected(db, host, installed)
    proven = sorted({b.kernel_release for b in kernel_boots.history(db, host.id)
                     if b.proven_at is not None}, key=kernel_boots.version_key, reverse=True)  # fmt: skip
    return {
        "running_kernel": kernel_boots.running_kernel(db, host),
        "installed_kernels": installed,
        "proven_kernels": proven,
        "protected": keep,
        "refusal": refusal,
        "runs": [
            package_cleanup.to_dict(r) for r in package_cleanup.latest(db, host.id)
        ],
    }


@router.post("/host/{host_id}/cleanup/plan")
def plan_cleanup(
    host_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Ask the agent what a cleanup would remove; nothing is removed."""
    host = _host_or_404(db, host_id)
    run = package_cleanup.request(db, host, "plan", current_user.userid)
    db.commit()
    return package_cleanup.to_dict(run)


@router.post("/host/{host_id}/cleanup/apply")
def apply_cleanup(
    host_id: str,
    body: ApplyBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Remove exactly ``packages`` (from a reviewed plan)."""
    if not current_user.has_role(SecurityRoles.REMOVE_PACKAGE):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: %s role required")
            % SecurityRoles.REMOVE_PACKAGE.value,
        )
    host = _host_or_404(db, host_id)
    names = sorted({str(n).strip() for n in body.packages if str(n).strip()})
    run = package_cleanup.request(
        db, host, "apply", current_user.userid, approved=names
    )
    _audit(db, current_user, host, _("Package cleanup requested"),
           {"run_id": str(run.id), "packages": names, "protected": run.protected,
            "status": run.status})  # fmt: skip
    db.commit()
    return package_cleanup.to_dict(run)
