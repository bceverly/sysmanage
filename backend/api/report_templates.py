"""
Custom report templates API (Phase 8.7).

Admin-defined layouts that the Pro+ ``reporting_engine`` reads at
render time to filter columns and reorder them.  The OSS server owns
the schema + REST CRUD;  Pro+ owns the actual rendering with logo and
header injection.

Endpoints:

  GET  /api/report-templates                       list templates
  POST /api/report-templates                       create
  GET  /api/report-templates/{id}                  read one
  PUT  /api/report-templates/{id}                  update
  DELETE /api/report-templates/{id}                delete
  GET  /api/report-templates/fields/{base_type}    available field codes for a base report type
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.db import get_db
from backend.services.audit_service import ActionType, AuditService, EntityType, Result

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/report-templates",
    tags=["report-templates"],
    dependencies=[Depends(JWTBearer())],
)


# Reused 404 detail string — extracted so the wording can't drift
# between handlers and so SonarQube's duplication scanner is happy.
_ERR_TEMPLATE_NOT_FOUND = "Report template not found"

# Column labels reused across multiple base report types (firewall +
# antivirus reports all carry an IP Address / OS Version column).
_LABEL_IP_ADDRESS = "IP Address"
_LABEL_OS_VERSION = "OS Version"


# Catalog of base report types and the field codes the renderer
# understands for each.  Kept in sync with the Pro+ reporting_engine —
# adding a field on either side without updating the other is a bug.
# Map: base_report_type -> [(field_code, default_label_msgid)]
_BASE_REPORTS: Dict[str, List[Dict[str, str]]] = {
    "registered-hosts": [
        {"code": "hostname", "label": "Hostname"},
        {"code": "fqdn", "label": "FQDN"},
        {"code": "ipv4", "label": "IPv4"},
        {"code": "ipv6", "label": "IPv6"},
        {"code": "os", "label": "OS"},
        {"code": "os_version", "label": "Version"},
        {"code": "status", "label": "Status"},
        {"code": "last_seen", "label": "Last Seen"},
    ],
    "hosts-with-tags": [
        {"code": "hostname", "label": "Hostname"},
        {"code": "fqdn", "label": "FQDN"},
        {"code": "status", "label": "Status"},
        {"code": "tags", "label": "Tags"},
        {"code": "last_seen", "label": "Last Seen"},
    ],
    # Catalog mirrors the Pro+ ``reporting_engine`` generators exactly.
    # Adding/removing a code here MUST be paired with the matching
    # generator's ``codes`` list, otherwise templates can reference
    # phantom columns or the renderer drops valid ones.
    "users-list": [
        {"code": "userid", "label": "User ID"},
        {"code": "first_name", "label": "First Name"},
        {"code": "last_name", "label": "Last Name"},
        {"code": "status", "label": "Status"},
        {"code": "last_access", "label": "Last Access"},
        {"code": "account_security", "label": "Account Security"},
    ],
    "firewall-status": [
        {"code": "hostname", "label": "Hostname"},
        {"code": "ip_address", "label": _LABEL_IP_ADDRESS},
        {"code": "os", "label": "OS"},
        {"code": "os_version", "label": _LABEL_OS_VERSION},
        {"code": "firewall_name", "label": "Firewall Software"},
        {"code": "ipv4_ports", "label": "IPv4 Ports"},
        {"code": "ipv6_ports", "label": "IPv6 Ports"},
        {"code": "firewall_status", "label": "Status"},
    ],
    "antivirus-opensource": [
        {"code": "hostname", "label": "Hostname"},
        {"code": "ip_address", "label": _LABEL_IP_ADDRESS},
        {"code": "os", "label": "OS"},
        {"code": "os_version", "label": _LABEL_OS_VERSION},
        {"code": "av_software", "label": "Antivirus Software"},
        {"code": "av_version", "label": "Version"},
        {"code": "install_path", "label": "Install Path"},
        {"code": "last_updated", "label": "Last Updated"},
        {"code": "av_status", "label": "Status"},
    ],
    "antivirus-commercial": [
        {"code": "hostname", "label": "Hostname"},
        {"code": "ip_address", "label": _LABEL_IP_ADDRESS},
        {"code": "os", "label": "OS"},
        {"code": "os_version", "label": _LABEL_OS_VERSION},
        {"code": "product_name", "label": "Product Name"},
        {"code": "product_version", "label": "Product Version"},
        {"code": "signature_version", "label": "Signature Version"},
        {"code": "last_updated", "label": "Last Updated"},
        {"code": "realtime_protection", "label": "Real-Time Protection"},
        {"code": "service_status", "label": "Service Status"},
    ],
    "user-rbac": [
        {"code": "userid", "label": "User"},
        {"code": "role_groups", "label": "Role Groups"},
        {"code": "roles", "label": "Roles"},
    ],
    "audit-log": [
        {"code": "timestamp", "label": "Timestamp"},
        {"code": "username", "label": "User"},
        {"code": "action_type", "label": "Action"},
        {"code": "entity_type", "label": "Entity Type"},
        {"code": "entity_name", "label": "Entity Name"},
        {"code": "result", "label": "Result"},
        {"code": "description", "label": "Description"},
    ],
}

_VALID_BASE_TYPES = tuple(_BASE_REPORTS.keys())


class TemplateCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    base_report_type: str
    selected_fields: List[str] = Field(default_factory=list)
    enabled: bool = True


class TemplateUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    base_report_type: Optional[str] = None
    selected_fields: Optional[List[str]] = None
    enabled: Optional[bool] = None


class TemplateResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    base_report_type: str
    selected_fields: List[str] = []
    enabled: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


def _get_user(db: Session, current_user: str) -> models.User:
    user = db.query(models.User).filter(models.User.userid == current_user).first()
    if not user:
        raise HTTPException(status_code=401, detail=_("User not found"))
    return user


def _parse_uuid_or_400(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_("Invalid UUID for %s: %s") % (field, value),
        ) from exc


def _validate_template_payload(
    base_report_type: Optional[str], selected_fields: Optional[List[str]]
) -> None:
    """Reject base types we don't recognize and field codes that don't
    match the base type.  Kept strict because a typo here means the
    Pro+ renderer silently produces an empty column."""
    if base_report_type is not None:
        if base_report_type not in _VALID_BASE_TYPES:
            raise HTTPException(
                status_code=400,
                detail=_("Unknown base_report_type: %s") % base_report_type,
            )
        if selected_fields is not None:
            valid_codes = {f["code"] for f in _BASE_REPORTS[base_report_type]}
            unknown = [c for c in selected_fields if c not in valid_codes]
            if unknown:
                raise HTTPException(
                    status_code=400,
                    detail=_("Unknown field code(s) for %s: %s")
                    % (base_report_type, ", ".join(unknown)),
                )


@router.get("", response_model=List[TemplateResponse])
async def list_templates(db: Session = Depends(get_db)):
    rows = db.query(models.ReportTemplate).order_by(models.ReportTemplate.name).all()
    return [TemplateResponse(**r.to_dict()) for r in rows]


@router.post("", response_model=TemplateResponse)
async def create_template(
    request: TemplateCreateRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    user = _get_user(db, current_user)
    _validate_template_payload(request.base_report_type, request.selected_fields)

    template = models.ReportTemplate(
        name=request.name.strip(),
        description=(request.description or "").strip() or None,
        base_report_type=request.base_report_type,
        selected_fields=list(request.selected_fields or []),
        enabled=request.enabled,
        created_by=user.id,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    AuditService.log(
        db=db,
        action_type=ActionType.CREATE,
        entity_type=EntityType.SETTING,
        entity_id=str(template.id),
        entity_name=template.name,
        description=_("Created report template '%s'") % template.name,
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return TemplateResponse(**template.to_dict())


@router.get("/fields/{base_report_type}")
async def list_fields_for_base_type(base_report_type: str):
    """Return the catalog of field codes the renderer recognizes for
    the given base report type.  The frontend uses this to populate the
    field-picker UI."""
    if base_report_type not in _VALID_BASE_TYPES:
        raise HTTPException(
            status_code=404,
            detail=_("Unknown base_report_type: %s") % base_report_type,
        )
    return {
        "base_report_type": base_report_type,
        "fields": _BASE_REPORTS[base_report_type],
    }


@router.get("/base-types")
async def list_base_types():
    """List the base report types that templates can be built on."""
    return {"base_types": list(_VALID_BASE_TYPES)}


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: str, db: Session = Depends(get_db)):
    tid = _parse_uuid_or_400(template_id, "template_id")
    template = (
        db.query(models.ReportTemplate).filter(models.ReportTemplate.id == tid).first()
    )
    if not template:
        raise HTTPException(status_code=404, detail=_(_ERR_TEMPLATE_NOT_FOUND))
    return TemplateResponse(**template.to_dict())


@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: str,
    request: TemplateUpdateRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    user = _get_user(db, current_user)
    tid = _parse_uuid_or_400(template_id, "template_id")
    template = (
        db.query(models.ReportTemplate).filter(models.ReportTemplate.id == tid).first()
    )
    if not template:
        raise HTTPException(status_code=404, detail=_(_ERR_TEMPLATE_NOT_FOUND))

    new_base = (
        request.base_report_type
        if request.base_report_type is not None
        else template.base_report_type
    )
    new_fields = (
        request.selected_fields
        if request.selected_fields is not None
        else template.selected_fields
    )
    _validate_template_payload(new_base, new_fields)

    if request.name is not None:
        template.name = request.name.strip()
    if request.description is not None:
        template.description = request.description.strip() or None
    if request.base_report_type is not None:
        template.base_report_type = request.base_report_type
    if request.selected_fields is not None:
        template.selected_fields = list(request.selected_fields)
    if request.enabled is not None:
        template.enabled = request.enabled
    template.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(template)

    AuditService.log(
        db=db,
        action_type=ActionType.UPDATE,
        entity_type=EntityType.SETTING,
        entity_id=str(template.id),
        entity_name=template.name,
        description=_("Updated report template '%s'") % template.name,
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return TemplateResponse(**template.to_dict())


@router.delete("/{template_id}")
async def delete_template(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    user = _get_user(db, current_user)
    tid = _parse_uuid_or_400(template_id, "template_id")
    template = (
        db.query(models.ReportTemplate).filter(models.ReportTemplate.id == tid).first()
    )
    if not template:
        raise HTTPException(status_code=404, detail=_(_ERR_TEMPLATE_NOT_FOUND))
    name = template.name
    db.delete(template)
    db.commit()

    AuditService.log(
        db=db,
        action_type=ActionType.DELETE,
        entity_type=EntityType.SETTING,
        entity_id=str(tid),
        entity_name=name,
        description=_("Deleted report template '%s'") % name,
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return {"message": _("Report template deleted"), "id": str(tid)}
