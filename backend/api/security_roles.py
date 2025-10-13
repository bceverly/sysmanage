"""
API endpoints for managing security roles and user permissions.
"""

from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.persistence.db import get_db
from backend.persistence.models import (
    SecurityRole,
    SecurityRoleGroup,
    User,
    UserSecurityRole,
)
from backend.auth.auth_bearer import get_current_user
from backend.security.roles import SecurityRoles, check_user_has_role
from backend.services.audit_service import ActionType, AuditService, EntityType

router = APIRouter(prefix="/api/security-roles", tags=["security-roles"])


class SecurityRoleResponse(BaseModel):
    """Response model for a security role."""

    id: UUID
    name: str
    description: str | None
    group_id: UUID
    group_name: str

    class Config:
        from_attributes = True


class SecurityRoleGroupResponse(BaseModel):
    """Response model for a security role group with its roles."""

    id: UUID
    name: str
    description: str | None
    roles: List[SecurityRoleResponse]

    class Config:
        from_attributes = True


class UserRolesRequest(BaseModel):
    """Request model for updating user security roles."""

    role_ids: List[str]  # Accept string UUIDs from frontend


class UserRolesResponse(BaseModel):
    """Response model for user security roles."""

    user_id: UUID
    role_ids: List[str]  # Return string UUIDs to frontend

    class Config:
        from_attributes = True


@router.get("/groups", response_model=List[SecurityRoleGroupResponse])
async def get_all_role_groups(
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Get all security role groups with their roles.
    Requires VIEW_USER_SECURITY_ROLES permission.
    """
    # Check if current user has permission to view user security roles
    current_user_obj = db.query(User).filter(User.userid == current_user).first()
    if not current_user_obj:
        raise HTTPException(status_code=401, detail="Current user not found")

    if not check_user_has_role(
        db, current_user_obj.id, SecurityRoles.VIEW_USER_SECURITY_ROLES
    ):
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to view user security roles",
        )

    groups = db.query(SecurityRoleGroup).order_by(SecurityRoleGroup.id).all()

    result = []
    for group in groups:
        roles = (
            db.query(SecurityRole)
            .filter(SecurityRole.group_id == group.id)
            .order_by(SecurityRole.id)
            .all()
        )

        role_responses = [
            SecurityRoleResponse(
                id=role.id,
                name=role.name,
                description=role.description,
                group_id=role.group_id,
                group_name=group.name,
            )
            for role in roles
        ]

        result.append(
            SecurityRoleGroupResponse(
                id=group.id,
                name=group.name,
                description=group.description,
                roles=role_responses,
            )
        )

    return result


@router.get("/user/{user_id}", response_model=UserRolesResponse)
async def get_user_roles(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Get all security roles for a specific user.
    Requires VIEW_USER_SECURITY_ROLES permission.
    """
    # Check if current user has permission to view user security roles
    current_user_obj = db.query(User).filter(User.userid == current_user).first()
    if not current_user_obj:
        raise HTTPException(status_code=401, detail="Current user not found")

    if not check_user_has_role(
        db, current_user_obj.id, SecurityRoles.VIEW_USER_SECURITY_ROLES
    ):
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to view user security roles",
        )

    # Verify user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get user's role IDs
    user_roles = (
        db.query(UserSecurityRole.role_id)
        .filter(UserSecurityRole.user_id == user_id)
        .all()
    )

    role_ids = [str(role[0]) for role in user_roles]

    return UserRolesResponse(user_id=user_id, role_ids=role_ids)


@router.put("/user/{user_id}", response_model=UserRolesResponse)
async def update_user_roles(
    user_id: UUID,
    request: UserRolesRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Update security roles for a specific user.
    Requires EDIT_USER_SECURITY_ROLES permission.
    """
    # Get current user's UUID from their userid (email)
    current_user_obj = db.query(User).filter(User.userid == current_user).first()
    if not current_user_obj:
        raise HTTPException(status_code=401, detail="Current user not found")
    current_user_uuid = current_user_obj.id

    # Check if current user has permission to edit user security roles
    if not check_user_has_role(
        db, current_user_uuid, SecurityRoles.EDIT_USER_SECURITY_ROLES
    ):
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to edit user security roles",
        )

    # Verify user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Convert string UUIDs to UUID objects and verify all role IDs exist
    role_uuids = []
    for role_id_str in request.role_ids:
        try:
            role_uuid = UUID(role_id_str)
            role_uuids.append(role_uuid)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid UUID format: {role_id_str}"
            ) from exc

        role = db.query(SecurityRole).filter(SecurityRole.id == role_uuid).first()
        if not role:
            raise HTTPException(
                status_code=400, detail=f"Role with ID {role_id_str} does not exist"
            )

    # Delete existing user roles
    db.query(UserSecurityRole).filter(UserSecurityRole.user_id == user_id).delete()

    # Add new user roles
    for role_uuid in role_uuids:
        user_role = UserSecurityRole(
            user_id=user_id,
            role_id=role_uuid,
            granted_by=current_user_uuid,
        )
        db.add(user_role)

    db.commit()

    # Audit log role assignment
    role_names = [
        db.query(SecurityRole).filter(SecurityRole.id == role_uuid).first().name
        for role_uuid in role_uuids
    ]
    AuditService.log(
        db=db,
        user_id=current_user_uuid,
        username=current_user,
        action_type=ActionType.UPDATE,
        entity_type=EntityType.USER_ROLE,
        entity_id=str(user_id),
        entity_name=user.userid,
        description=f"Security roles updated for user {user.userid} by {current_user}",
        details={"roles": role_names, "role_ids": [str(r) for r in role_uuids]},
    )

    return UserRolesResponse(user_id=user_id, role_ids=request.role_ids)
