# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Advisory action API (Phase 14.1) — "install by advisory".

OSS orchestration: resolve an advisory's applicable packages for a host (from the
tenant ``host_applicable_advisory`` rows the Pro+ engine computed) and dispatch an
install through the EXISTING package-install path.  Gated behind the Professional
``ADVISORY_MANAGEMENT`` feature (defence in depth; the UI hides it when unlicensed).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.packages_models import PackageInstallRequest
from backend.api.packages_operations import install_packages_operation
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.licensing.features import FeatureCode
from backend.licensing.license_service import license_service
from backend.persistence.models import HostApplicableAdvisory
from backend.persistence.partitions import get_tenant_db
from backend.utils.verbosity_logger import get_logger

logger = get_logger(__name__)

router = APIRouter(dependencies=[Depends(JWTBearer())])


def _dispatch_openbsd_syspatch(host_id, rows, db, current_user):
    """Remediate an OpenBSD errata advisory by queueing a ``syspatch`` apply.

    OpenBSD base errata are applied with syspatch(8), NOT a package manager, so we
    can't reuse ``install_packages_operation`` (that would try to ``pkg_add`` the
    patch ids).  Instead enqueue the same ``apply_updates`` command the Updates page
    uses — the agent routes package_manager ``syspatch`` to its syspatch executor
    (which applies all pending, all-or-nothing).  Enqueued OUTBOUND so Phase 14.2
    maintenance-window gating applies at release time automatically."""
    from backend.websocket.messages import create_command_message  # noqa: PLC0415
    from backend.websocket.queue_enums import QueueDirection  # noqa: PLC0415
    from backend.websocket.queue_operations import QueueOperations  # noqa: PLC0415

    packages = [
        {"package_name": r.package_name, "package_manager": "syspatch"}
        for r in rows
        if r.package_name
    ]
    command_message = create_command_message("apply_updates", {"packages": packages})
    QueueOperations().enqueue_message(
        message_type="command",
        message_data=command_message,
        direction=QueueDirection.OUTBOUND,
        host_id=host_id,
        db=db,
    )
    db.commit()
    logger.info(
        "Queued syspatch apply for %d OpenBSD erratum/errata on host %s (by %s)",
        len(packages),
        host_id,
        current_user,
    )
    return {
        "success": True,
        "message": _("syspatch apply queued"),
        "packages_count": len(packages),
    }


class AdvisoryInstallRequest(BaseModel):
    """Install every applicable package for one advisory on a host."""

    advisory_id: str  # shared_advisory.id (as stored on host_applicable_advisory)


def _require_advisory_license() -> None:
    if not license_service.has_feature(FeatureCode.ADVISORY_MANAGEMENT):
        raise HTTPException(
            status_code=402,
            detail=_("Advisory management requires a SysManage Professional license."),
        )


@router.post("/advisory/host/{host_id}/install")
async def install_by_advisory(
    host_id: str,
    body: AdvisoryInstallRequest,
    db: Session = Depends(get_tenant_db),
    current_user: str = Depends(get_current_user),
):
    """Queue installation of every package an advisory fixes on this host.

    The applicable package set is read from ``host_applicable_advisory`` (computed
    by the advisory engine); the actual dispatch reuses ``install_packages_operation``
    so agent delivery, audit, and maintenance-window gating all apply unchanged.
    """
    _require_advisory_license()

    rows = (
        db.query(HostApplicableAdvisory)
        .filter(
            HostApplicableAdvisory.host_id == host_id,
            HostApplicableAdvisory.advisory_id == body.advisory_id,
            HostApplicableAdvisory.status == "applicable",
        )
        .all()
    )
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=_("No applicable packages for this advisory on this host."),
        )

    # OpenBSD errata are remediated with syspatch, not a package manager.
    if any(r.source == "openbsd" for r in rows):
        return _dispatch_openbsd_syspatch(host_id, rows, db, current_user)

    package_names = sorted({r.package_name for r in rows if r.package_name})
    request = PackageInstallRequest(
        package_names=package_names, requested_by=current_user
    )
    return await install_packages_operation(host_id, request, db, current_user)
