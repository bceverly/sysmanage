# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Inventories: naming the set of hosts a fleet job runs against (Phase 20.1).

Job templates and the jobs themselves live in ``config_mgmt_jobs``. Split
because together they exceed this project's 1000-line file ceiling, and the
seam is a real one: an inventory is a reusable noun that outlives any
particular run, which is exactly why it is worth storing separately.

LICENCE-GATED AT THE ROUTER, like the profiles and drift routers and for the
same reason: an endpoint added here is gated by default, which is the safe
direction to fail.

ROLES reuse the SCRIPT entitlements, as profiles do. Authoring an inventory or
a template is EDIT_SCRIPT-class work; LAUNCHING one runs executable content on
every host it names, so it is RUN_SCRIPT -- the same permission as applying a
profile to one host, because it is that operation with a larger blast radius
rather than a different one.
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.licensing.feature_gate import require_module_loaded
from backend.licensing.features import ModuleCode
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import config_mgmt_fleet as fleet

logger = logging.getLogger(__name__)

router = APIRouter(
    dependencies=[
        Depends(JWTBearer()),
        Depends(require_module_loaded(ModuleCode.CONFIG_MANAGEMENT_ENGINE)),
    ]
)

# --- request/response shapes -------------------------------------------------


class InventoryRequest(BaseModel):
    """A named set of hosts."""

    name: str
    description: Optional[str] = None
    all_hosts: bool = False


class InventoryUpdateRequest(BaseModel):
    """Fields to change. Omitted fields are left alone."""

    name: Optional[str] = None
    description: Optional[str] = None
    all_hosts: Optional[bool] = None


class InventoryResponse(BaseModel):
    """A stored inventory."""

    id: str
    name: str
    description: Optional[str] = None
    all_hosts: bool
    # Resolved live, so it is right after a host is tagged or retired.
    host_count: Optional[int] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MemberRequest(BaseModel):
    """One selector to add. Exactly one target."""

    host_id: Optional[str] = None
    tag_id: Optional[str] = None
    site_id: Optional[str] = None


class MemberResponse(BaseModel):
    """One selector in an inventory."""

    id: str
    inventory_id: str
    host_id: Optional[str] = None
    tag_id: Optional[str] = None
    site_id: Optional[str] = None
    created_at: Optional[datetime] = None


# --- helpers -----------------------------------------------------------------


def _require_role(user, role) -> None:
    if not user.has_role(role):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: %s role required") % role.value,
        )


def _as_uuid(value: str, message: str) -> uuid.UUID:
    """Parse an ID, or 400 with a fully-spelled message.

    The message arrives already translated rather than built from an
    interpolated noun, matching the profiles router: an interpolated noun ships
    in English inside an otherwise translated sentence and assumes a word order
    not every language has.
    """
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=message) from exc


def _load_inventory(db_session: Session, inventory_id: str):
    row = (
        db_session.query(models.ConfigInventory)
        .filter(
            models.ConfigInventory.id
            == _as_uuid(inventory_id, _("Invalid inventory ID format"))
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=_("Inventory not found"))
    return row


def _member_count(db_session: Session, inventory_id) -> int:
    return (
        db_session.query(models.ConfigInventoryMember)
        .filter(models.ConfigInventoryMember.inventory_id == inventory_id)
        .count()
    )


def _name_taken(db_session: Session, model, name: str, exclude_id=None) -> bool:
    query = db_session.query(model).filter(model.name == (name or "").strip())
    if exclude_id is not None:
        query = query.filter(model.id != exclude_id)
    return query.first() is not None


# --- inventories -------------------------------------------------------------


@router.get("/config-management/inventories", response_model=List[InventoryResponse])
async def list_inventories(db_session: Session = Depends(get_tenant_db)):
    """Every inventory, with the host count each currently resolves to."""
    rows = (
        db_session.query(models.ConfigInventory)
        .order_by(models.ConfigInventory.name.asc())
        .all()
    )
    return [
        InventoryResponse(
            **fleet.inventory_to_dict(
                row, host_count=fleet.inventory_host_count(db_session, row)
            )
        )
        for row in rows
    ]


@router.post("/config-management/inventories", response_model=InventoryResponse)
async def create_inventory(
    request: InventoryRequest,
    db_session: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Create an inventory.

    A new inventory has no members yet, so it is only acceptable at creation
    when it says ``all_hosts``; otherwise members are added and the emptiness
    rule is enforced at LAUNCH. Refusing creation outright would make building
    a multi-tag inventory impossible -- there would be no valid first step.
    """
    _require_role(current_user, SecurityRoles.ADD_SCRIPT)

    # ``all_hosts=True`` is passed regardless of what was requested, which
    # validates the NAME and deliberately skips the emptiness rule: a new
    # inventory has no members yet, so enforcing it here would make a
    # multi-tag inventory impossible to build -- there would be no valid first
    # step. Emptiness is enforced on update and again at launch.
    problem = fleet.validate_inventory(request.name, True, 0)
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    if _name_taken(db_session, models.ConfigInventory, request.name):
        raise HTTPException(
            status_code=409,
            detail=_("An inventory named '%s' already exists") % request.name,
        )

    now = fleet.now_naive()
    row = models.ConfigInventory(
        name=request.name.strip(),
        description=request.description,
        all_hosts=bool(request.all_hosts),
        created_by=current_user.userid,
        updated_by=current_user.userid,
        created_at=now,
        updated_at=now,
    )
    db_session.add(row)
    db_session.commit()
    logger.info("Config inventory created: %s", row.name)
    return InventoryResponse(**fleet.inventory_to_dict(row, host_count=0))


@router.get(
    "/config-management/inventories/{inventory_id}", response_model=InventoryResponse
)
async def get_inventory(
    inventory_id: str, db_session: Session = Depends(get_tenant_db)
):
    """One inventory."""
    row = _load_inventory(db_session, inventory_id)
    return InventoryResponse(
        **fleet.inventory_to_dict(
            row, host_count=fleet.inventory_host_count(db_session, row)
        )
    )


@router.put(
    "/config-management/inventories/{inventory_id}", response_model=InventoryResponse
)
async def update_inventory(
    inventory_id: str,
    request: InventoryUpdateRequest,
    db_session: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Change an inventory."""
    _require_role(current_user, SecurityRoles.EDIT_SCRIPT)
    row = _load_inventory(db_session, inventory_id)
    changes = request.model_dump(exclude_unset=True)

    merged_name = changes.get("name", row.name)
    merged_all = changes.get("all_hosts", row.all_hosts)
    problem = fleet.validate_inventory(
        merged_name, merged_all, _member_count(db_session, row.id)
    )
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    if "name" in changes and _name_taken(
        db_session, models.ConfigInventory, changes["name"], exclude_id=row.id
    ):
        raise HTTPException(
            status_code=409,
            detail=_("An inventory named '%s' already exists") % changes["name"],
        )

    for field in ("name", "description", "all_hosts"):
        if field in changes:
            value = changes[field]
            setattr(row, field, value.strip() if field == "name" and value else value)
    row.updated_by = current_user.userid
    row.updated_at = fleet.now_naive()
    db_session.commit()
    return InventoryResponse(
        **fleet.inventory_to_dict(
            row, host_count=fleet.inventory_host_count(db_session, row)
        )
    )


@router.delete("/config-management/inventories/{inventory_id}")
async def delete_inventory(
    inventory_id: str,
    db_session: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Delete an inventory and its members.

    Refused while a template still names it. The foreign key is CASCADE, so
    allowing this would silently delete every template built on the inventory
    -- and with them their schedules, which would stop firing with nothing to
    show for it.
    """
    _require_role(current_user, SecurityRoles.DELETE_SCRIPT)
    row = _load_inventory(db_session, inventory_id)

    in_use = (
        db_session.query(models.ConfigJobTemplate)
        .filter(models.ConfigJobTemplate.inventory_id == row.id)
        .count()
    )
    if in_use:
        raise HTTPException(
            status_code=409,
            detail=_("This inventory is used by %d job template(s)") % in_use,
        )

    name = row.name
    db_session.delete(row)
    db_session.commit()
    logger.info("Config inventory deleted: %s", name)
    return {"success": True, "message": _("Inventory deleted")}


@router.get(
    "/config-management/inventories/{inventory_id}/members",
    response_model=List[MemberResponse],
)
async def list_members(inventory_id: str, db_session: Session = Depends(get_tenant_db)):
    """The selectors this inventory is built from."""
    row = _load_inventory(db_session, inventory_id)
    members = (
        db_session.query(models.ConfigInventoryMember)
        .filter(models.ConfigInventoryMember.inventory_id == row.id)
        .all()
    )
    return [MemberResponse(**fleet.member_to_dict(m)) for m in members]


@router.post(
    "/config-management/inventories/{inventory_id}/members",
    response_model=MemberResponse,
)
async def add_member(
    inventory_id: str,
    request: MemberRequest,
    db_session: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Add a host, a tag or a site to an inventory."""
    _require_role(current_user, SecurityRoles.EDIT_SCRIPT)
    inventory = _load_inventory(db_session, inventory_id)

    problem = fleet.validate_inventory_member(
        request.host_id, request.tag_id, request.site_id
    )
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    member = models.ConfigInventoryMember(
        inventory_id=inventory.id,
        host_id=(
            _as_uuid(request.host_id, _("Invalid host ID format"))
            if request.host_id
            else None
        ),
        tag_id=(
            _as_uuid(request.tag_id, _("Invalid tag ID format"))
            if request.tag_id
            else None
        ),
        site_id=(
            _as_uuid(request.site_id, _("Invalid site ID format"))
            if request.site_id
            else None
        ),
        created_at=fleet.now_naive(),
    )
    db_session.add(member)
    db_session.commit()
    return MemberResponse(**fleet.member_to_dict(member))


@router.delete("/config-management/inventory-members/{member_id}")
async def delete_member(
    member_id: str,
    db_session: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Remove one selector from an inventory."""
    _require_role(current_user, SecurityRoles.EDIT_SCRIPT)
    row = (
        db_session.query(models.ConfigInventoryMember)
        .filter(
            models.ConfigInventoryMember.id
            == _as_uuid(member_id, _("Invalid inventory member ID format"))
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=_("Inventory member not found"))
    db_session.delete(row)
    db_session.commit()
    return {"success": True, "message": _("Inventory member removed")}


@router.get(
    "/config-management/inventories/{inventory_id}/hosts",
    response_model=List[str],
)
async def preview_inventory(
    inventory_id: str, db_session: Session = Depends(get_tenant_db)
):
    """The hostnames this inventory resolves to right now.

    A preview, and the reason resolution is never cached: it answers "who am I
    about to change" at the moment the operator asks, which is the question
    they need answered before launching against four thousand machines.
    """
    inventory = _load_inventory(db_session, inventory_id)
    return sorted(
        host.fqdn or str(host.id) for host in fleet.resolve_hosts(db_session, inventory)
    )
