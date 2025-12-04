"""
Helper functions for child host API endpoints.
"""

from fastapi import HTTPException

from backend.i18n import _
from backend.persistence import models
from backend.security.roles import SecurityRoles


def get_user_with_role_check(session, current_user: str, required_role: SecurityRoles):
    """Get user and verify they have the required role."""
    user = session.query(models.User).filter(models.User.userid == current_user).first()
    if not user:
        raise HTTPException(status_code=401, detail=_("User not found"))

    if user._role_cache is None:
        user.load_role_cache(session)

    if not user.has_role(required_role):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: {} role required").format(required_role.value),
        )

    return user


def get_host_or_404(session, host_id: str):
    """Get host by ID or raise 404."""
    host = session.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=_("Host not found"))
    return host


def verify_host_active(host):
    """Verify the host is active."""
    if not host.active:
        raise HTTPException(status_code=400, detail=_("Host is not active"))


def audit_log(
    session,
    user,
    username: str,
    action: str,
    host_id: str,
    host_fqdn: str,
    description: str,
):
    """Log an audit entry."""
    from backend.services.audit_service import (
        ActionType,
        AuditService,
        EntityType,
        Result,
    )

    action_type = {
        "CREATE": ActionType.CREATE,
        "UPDATE": ActionType.UPDATE,
        "DELETE": ActionType.DELETE,
    }.get(action, ActionType.UPDATE)

    AuditService.log(
        db=session,
        user_id=user.id,
        username=username,
        action_type=action_type,
        entity_type=EntityType.HOST,
        entity_id=host_id,
        entity_name=host_fqdn,
        description=description,
        result=Result.SUCCESS,
    )
