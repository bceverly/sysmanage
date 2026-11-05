# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Create the first administrator from the recovery account (2026-11-05).

A fresh installation has exactly one account: ``security.admin_userid`` in
``sysmanage.yaml``, the recovery account, which has no database row.  It can
sign in and look around, but every endpoint that resolves the caller to a
database user (``require_authenticated_user``) refuses it with "User not
found" -- approving the first host included -- and the Users page creates a
user with no password and emails a setup link, which needs SMTP configured.
On a fresh Ubuntu 24.04 install the evaluation stopped there: two hosts
waiting for approval and no way to approve them.

This endpoint is the way out, offered by the security banner while it
applies: the recovery account (and only it) creates one administrator with
a password it chooses and every security role, as long as no active
administrator exists yet.  After that, the banner's remaining steps apply --
sign in as the new administrator and remove the recovery credentials.
"""

from datetime import datetime, timezone
from typing import Optional

from argon2 import PasswordHasher
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session, sessionmaker

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.config import config
from backend.i18n import _
from backend.persistence import db, models
from backend.services.audit_service import AuditService, EntityType
from backend.utils.password_policy import password_policy

router = APIRouter(prefix="/security", tags=["security"])
_hasher = PasswordHasher()


class FirstAdminRequest(BaseModel):
    """The administrator to create."""

    userid: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    password: str
    confirm_password: str


def recovery_userid() -> Optional[str]:
    """``security.admin_userid``, when the recovery account is configured."""
    security = config.get_config().get("security", {})
    if security.get("admin_userid") and security.get("admin_password"):
        return security["admin_userid"]
    return None


def database_admin_exists(session: Session) -> bool:
    """Whether any active administrator has a database account."""
    return (
        session.query(models.User.id)
        .filter(models.User.is_admin.is_(True), models.User.active.is_(True))
        .first()
        is not None
    )


def needs_first_admin(current_user: str) -> bool:
    """True while the caller is the recovery account and no administrator
    exists -- the state the banner offers "Create your administrator" in."""
    if not current_user or current_user != recovery_userid():
        return False
    with sessionmaker(bind=db.get_engine())() as session:
        return not database_admin_exists(session)


@router.post("/first-admin", dependencies=[Depends(JWTBearer())])
async def create_first_admin(
    body: FirstAdminRequest, current_user: str = Depends(get_current_user)
):
    """Create the first administrator, with every security role."""
    recovery = recovery_userid()
    if not recovery or current_user != recovery:
        raise HTTPException(
            status_code=403,
            detail=_(
                "Only the recovery account in sysmanage.yaml can create the first administrator"
            ),
        )
    if body.userid == recovery:
        raise HTTPException(
            status_code=400,
            detail=_("Use a different email address from the recovery account"),
        )
    if body.password != body.confirm_password:
        raise HTTPException(
            status_code=400, detail=_("New password and confirmation do not match")
        )
    is_valid, errors = password_policy.validate_password(body.password, body.userid)
    if not is_valid:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    with sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )() as session:
        if database_admin_exists(session):
            raise HTTPException(
                status_code=409,
                detail=_(
                    "An administrator already exists. Sign in as that administrator to add more users."
                ),
            )
        if (
            session.query(models.User.id)
            .filter(models.User.userid == body.userid)
            .first()
        ):
            raise HTTPException(status_code=409, detail=_("User already exists"))
        user = models.User(
            userid=body.userid,
            active=True,
            first_name=body.first_name,
            last_name=body.last_name,
            hashed_password=_hasher.hash(body.password),
            is_admin=True,
            last_access=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(user)
        session.flush()
        roles = session.query(models.SecurityRole.id).all()
        for (role_id,) in roles:
            session.add(models.UserSecurityRole(user_id=user.id, role_id=role_id))
        session.commit()
        AuditService.log_create(
            db=session,
            user_id=None,  # the recovery account has no database row
            username=current_user,
            entity_type=EntityType.USER,
            entity_id=str(user.id),
            entity_name=body.userid,
            details={"is_admin": True, "roles": len(roles), "first_admin": True},
        )
        return {"id": str(user.id), "userid": body.userid, "roles": len(roles)}
