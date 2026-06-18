"""
Helper functions for child host API endpoints.
"""

from fastapi import HTTPException

from backend.i18n import _
from backend.persistence import models
from backend.security.roles import SecurityRoles


def raise_engine_declined() -> None:
    """Surface a 502 to the client when the Pro+ engine declined the request.

    Centralized so the user-facing message is defined once (and the
    gettext extractor sees it once).  Each child-host route raises this
    when its ``_try_*`` helper returns False.
    """
    raise HTTPException(
        status_code=502,
        detail=_("Child host engine could not dispatch this request."),
    )


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


def authorize_on_main(current_user: str, required_role: SecurityRoles):
    """Authn/authz against the server-global (bootstrap) engine.

    User and role data is server-global — it lives in the bootstrap database,
    never in a per-tenant database — so authorization must NOT run on a tenant
    session.  This runs the role check on a ``db.get_engine()`` session and
    returns the ``User``.  Its ``id`` / ``userid`` / role-cache are loaded
    while the session is open, so the detached object is safe to use afterward
    for ``audit_log`` writes on the tenant session.

    Use this in host-scoped (data-plane) handlers: call it BEFORE opening the
    ``request_sessionmaker()`` tenant session that serves the host data, e.g.::

        user = authorize_on_main(current_user, SecurityRoles.VIEW_CHILD_HOST)
        with request_sessionmaker()() as session:
            host = get_host_or_404(session, host_id)
            ...
    """
    # Imported here to avoid a module-level import cycle (db imports models).
    from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

    from backend.persistence import db  # noqa: PLC0415

    auth_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())
    with auth_local() as auth_session:
        user = get_user_with_role_check(auth_session, current_user, required_role)
        # Touch the attributes used after the session closes (audit_log reads
        # user.id; handlers reference user.userid) so they are loaded before the
        # instance detaches — avoids DetachedInstanceError on later access.
        _ = (user.id, user.userid)
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
    user,
    username: str,
    action: str,
    host_id: str,
    host_fqdn: str,
    description: str,
    details: dict = None,
):
    """Log an audit entry on the server-global (bootstrap) engine.

    The audit trail is server-global, like authorization — it lives in the
    bootstrap database, never in a per-tenant database — so it is written on its
    own ``db.get_engine()`` session regardless of which tenant database served
    the host data for this request.  (Mirrors diagnostics.py, which audits on
    the MAIN engine after committing the host work.)  ``AuditService.log``
    commits this session.
    """
    # Imported here to avoid a module-level import cycle (db imports models).
    from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

    from backend.persistence import db  # noqa: PLC0415
    from backend.services.audit_service import (
        ActionType,  # noqa: PLC0415
        AuditService,
        EntityType,
        Result,
    )

    action_type = {
        "CREATE": ActionType.CREATE,
        "UPDATE": ActionType.UPDATE,
        "DELETE": ActionType.DELETE,
    }.get(action, ActionType.UPDATE)

    audit_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())
    with audit_local() as audit_session:
        AuditService.log(
            db=audit_session,
            user_id=user.id,
            username=username,
            action_type=action_type,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host_fqdn,
            description=description,
            result=Result.SUCCESS,
            details=details,
        )
