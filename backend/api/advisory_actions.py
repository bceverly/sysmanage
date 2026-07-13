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

router = APIRouter(dependencies=[Depends(JWTBearer())])


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

    package_names = sorted({r.package_name for r in rows if r.package_name})
    request = PackageInstallRequest(
        package_names=package_names, requested_by=current_user
    )
    return await install_packages_operation(host_id, request, db, current_user)
