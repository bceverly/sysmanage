# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Permission checking helpers for secrets API.
"""

from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from backend.i18n import _
from backend.persistence import db as db_module
from backend.persistence import models
from backend.security.roles import SecurityRoles


def check_user_permission(current_user: str, required_role: SecurityRoles):
    """
    Check if user has the required permission role.

    Args:
        current_user: User ID
        required_role: Required security role

    Raises:
        HTTPException: If user not found or lacks permission
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )
    with session_local() as session:
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail=_("User not found"))

        if user._role_cache is None:
            user.load_role_cache(session)

        if not user.has_role(required_role):
            raise HTTPException(
                status_code=403,
                # The role name is DATA, not part of the sentence: interpolating it
                # into the msgid would make every role a separate untranslatable
                # string.  Translate the template, then substitute.
                detail=_("Permission denied: %s role required") % required_role.name,
            )
