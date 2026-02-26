"""
Tag management API endpoints
"""

import asyncio
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.api.error_constants import (
    error_edit_tags_required,
    error_tag_already_exists,
    error_tag_not_found,
    error_user_not_found,
)
from backend.auth.auth_bearer import get_current_user
from backend.i18n import _
from backend.persistence import db as db_module
from backend.persistence import models
from backend.persistence.db import get_db
from backend.persistence.models import HostTag, Tag
from backend.security.roles import SecurityRoles

router = APIRouter()


class TagCreate(BaseModel):
    """Schema for creating a new tag"""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


class TagUpdate(BaseModel):
    """Schema for updating a tag"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


class TagResponse(BaseModel):
    """Schema for tag response"""

    id: str
    name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    host_count: int = 0

    class Config:
        from_attributes = True


class TagWithHostsResponse(BaseModel):
    """Schema for tag with associated hosts"""

    id: str
    name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    hosts: List[dict]

    class Config:
        from_attributes = True


class HostTagRequest(BaseModel):
    """Schema for adding/removing tag from host"""

    host_id: str
    tag_id: str


def _get_tags_sync():
    """
    Synchronous helper function to retrieve all tags.
    This runs in a thread pool to avoid blocking the event loop.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )

    with session_local() as session:
        try:
            # Query all tags with host count
            stmt = select(Tag).order_by(Tag.name)
            result = session.execute(stmt)
            tags = result.scalars().all()

            # Add host count to each tag
            tag_responses = []
            for tag in tags:
                try:
                    # Try to get host count, fallback to 0 if there's an issue
                    host_count = (
                        tag.hosts.count() if hasattr(tag, "hosts") and tag.hosts else 0
                    )
                except Exception:
                    # If relationship fails, default to 0
                    host_count = 0

                tag_dict = {
                    "id": str(tag.id),
                    "name": tag.name,
                    "description": tag.description,
                    "created_at": tag.created_at,
                    "updated_at": tag.updated_at,
                    "host_count": host_count,
                }
                tag_responses.append(tag_dict)

            return tag_responses
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=_("Failed to fetch tags: %(error)s") % {"error": str(e)},
            ) from e


@router.get("/tags", response_model=List[TagResponse])
async def get_tags(current_user: str = Depends(get_current_user)):
    """
    Get all tags.
    Runs the database query in a thread pool to avoid blocking the event loop.
    """
    # Run the synchronous database operation in a thread pool
    loop = asyncio.get_event_loop()
    tag_dicts = await loop.run_in_executor(None, _get_tags_sync)
    return [TagResponse(**tag_dict) for tag_dict in tag_dicts]


@router.post("/tags", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(
    tag_data: TagCreate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Create a new tag"""
    try:
        # Check if user has permission to edit tags
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
                raise HTTPException(status_code=401, detail=error_user_not_found())

            if user._role_cache is None:
                user.load_role_cache(session)

            if not user.has_role(SecurityRoles.EDIT_TAGS):
                raise HTTPException(
                    status_code=403,
                    detail=error_edit_tags_required(),
                )

        # Check if tag with same name already exists
        existing_tag = db.query(Tag).filter(Tag.name == tag_data.name).first()
        if existing_tag:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_tag_already_exists(),
            )

        # Create new tag
        new_tag = Tag(
            name=tag_data.name,
            description=tag_data.description,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        db.add(new_tag)
        db.commit()
        db.refresh(new_tag)

        # Audit log tag creation
        from backend.services.audit_service import (
            ActionType,
            AuditService,
            EntityType,
            Result,
        )

        with session_local() as audit_session:
            AuditService.log_create(
                db=audit_session,
                user_id=user.id,
                username=current_user,
                entity_type=EntityType.TAG,
                entity_id=str(new_tag.id),
                entity_name=new_tag.name,
                details={"description": new_tag.description},
            )

        return TagResponse(
            id=str(new_tag.id),
            name=new_tag.name,
            description=new_tag.description,
            created_at=new_tag.created_at,
            updated_at=new_tag.updated_at,
            host_count=0,
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tag with this name already exists",
        ) from exc
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_("Failed to create tag: %(error)s") % {"error": str(e)},
        ) from e


@router.put("/tags/{tag_id}", response_model=TagResponse)
async def update_tag(
    tag_id: str,
    tag_data: TagUpdate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Update an existing tag"""
    try:
        # Check if user has permission to edit tags
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
                raise HTTPException(status_code=401, detail=error_user_not_found())

            if user._role_cache is None:
                user.load_role_cache(session)

            if not user.has_role(SecurityRoles.EDIT_TAGS):
                raise HTTPException(
                    status_code=403,
                    detail=error_edit_tags_required(),
                )

        # Find the tag
        tag = db.query(Tag).filter(Tag.id == tag_id).first()
        if not tag:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=error_tag_not_found()
            )

        # Check if new name conflicts with existing tag
        if tag_data.name and tag_data.name != tag.name:
            existing_tag = db.query(Tag).filter(Tag.name == tag_data.name).first()
            if existing_tag:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_tag_already_exists(),
                )
            tag.name = tag_data.name

        if tag_data.description is not None:
            tag.description = tag_data.description

        tag.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

        db.commit()
        db.refresh(tag)

        # Audit log tag update
        from backend.services.audit_service import (
            ActionType,
            AuditService,
            EntityType,
            Result,
        )

        with session_local() as audit_session:
            AuditService.log_update(
                db=audit_session,
                user_id=user.id,
                username=current_user,
                entity_type=EntityType.TAG,
                entity_id=tag_id,
                entity_name=tag.name,
                details={"description": tag.description},
            )

        # Get host count safely
        try:
            host_count = tag.hosts.count() if hasattr(tag, "hosts") and tag.hosts else 0
        except Exception:
            host_count = 0

        return TagResponse(
            id=str(tag.id),
            name=tag.name,
            description=tag.description,
            created_at=tag.created_at,
            updated_at=tag.updated_at,
            host_count=host_count,
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_("Failed to update tag: %(error)s") % {"error": str(e)},
        ) from e


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Delete a tag"""
    try:
        # Check if user has permission to edit tags
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
                raise HTTPException(status_code=401, detail=error_user_not_found())

            if user._role_cache is None:
                user.load_role_cache(session)

            if not user.has_role(SecurityRoles.EDIT_TAGS):
                raise HTTPException(
                    status_code=403,
                    detail=error_edit_tags_required(),
                )

        # Find the tag
        tag = db.query(Tag).filter(Tag.id == tag_id).first()
        if not tag:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=error_tag_not_found()
            )

        # Use SQL directly to avoid ORM relationship issues
        from sqlalchemy import text

        # Delete associated host_tags entries first
        db.execute(
            text("DELETE FROM host_tags WHERE tag_id = :tag_id"), {"tag_id": tag_id}
        )

        # Store tag name for audit log before deletion
        tag_name = tag.name

        # Now delete the tag
        db.execute(text("DELETE FROM tags WHERE id = :tag_id"), {"tag_id": tag_id})
        db.commit()

        # Audit log tag deletion
        from backend.services.audit_service import (
            ActionType,
            AuditService,
            EntityType,
            Result,
        )

        with session_local() as audit_session:
            AuditService.log_delete(
                db=audit_session,
                user_id=user.id,
                username=current_user,
                entity_type=EntityType.TAG,
                entity_id=tag_id,
                entity_name=tag_name,
            )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_("Failed to delete tag: %(error)s") % {"error": str(e)},
        ) from e


def _get_tag_hosts_sync(tag_id: str):
    """
    Synchronous helper function to retrieve hosts for a tag.
    This runs in a thread pool to avoid blocking the event loop.
    """
    from sqlalchemy import text

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )

    with session_local() as session:
        try:
            # Find the tag using raw SQL
            tag_result = session.execute(
                text(
                    "SELECT id, name, description, created_at, updated_at FROM tags WHERE id = :tag_id"
                ),
                {"tag_id": tag_id},
            ).first()
            if not tag_result:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail=error_tag_not_found()
                )

            # Get associated hosts using raw SQL to avoid ORM issues
            host_results = session.execute(
                text("""
                SELECT h.id, h.fqdn, h.ipv4, h.ipv6, h.active, h.status
                FROM host h
                JOIN host_tags ht ON h.id = ht.host_id
                WHERE ht.tag_id = :tag_id
            """),
                {"tag_id": tag_id},
            ).fetchall()

            host_list = []
            for host_row in host_results:
                host_list.append(
                    {
                        "id": str(host_row.id),
                        "fqdn": host_row.fqdn,
                        "ipv4": host_row.ipv4,
                        "ipv6": host_row.ipv6,
                        "active": host_row.active,
                        "status": host_row.status,
                    }
                )

            return {
                "id": str(tag_result.id),
                "name": tag_result.name,
                "description": tag_result.description,
                "created_at": tag_result.created_at,
                "updated_at": tag_result.updated_at,
                "hosts": host_list,
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=_("Failed to fetch tag hosts: %(error)s") % {"error": str(e)},
            ) from e


@router.get("/tags/{tag_id}/hosts", response_model=TagWithHostsResponse)
async def get_tag_hosts(
    tag_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Get all hosts associated with a specific tag.
    Runs the database query in a thread pool to avoid blocking the event loop.
    """
    # Run the synchronous database operation in a thread pool
    loop = asyncio.get_event_loop()
    tag_with_hosts = await loop.run_in_executor(None, _get_tag_hosts_sync, tag_id)
    return TagWithHostsResponse(**tag_with_hosts)


@router.post("/hosts/{host_id}/tags/{tag_id}", status_code=status.HTTP_201_CREATED)
async def add_tag_to_host(
    host_id: str,
    tag_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Add a tag to a host"""
    try:
        # Check if user has permission to edit tags
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
                raise HTTPException(status_code=401, detail=error_user_not_found())

            if user._role_cache is None:
                user.load_role_cache(session)

            if not user.has_role(SecurityRoles.EDIT_TAGS):
                raise HTTPException(
                    status_code=403,
                    detail=error_edit_tags_required(),
                )

        from sqlalchemy import text

        # Verify host exists using raw SQL to avoid ORM issues
        host_result = db.execute(
            text("SELECT id FROM host WHERE id = :host_id"), {"host_id": host_id}
        ).first()
        if not host_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_("Host not found")
            )

        # Verify tag exists using raw SQL
        tag_result = db.execute(
            text("SELECT id FROM tags WHERE id = :tag_id"), {"tag_id": tag_id}
        ).first()
        if not tag_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=error_tag_not_found()
            )

        # Check if association already exists using raw SQL
        existing = db.execute(
            text(
                "SELECT 1 FROM host_tags WHERE host_id = :host_id AND tag_id = :tag_id"
            ),
            {"host_id": host_id, "tag_id": tag_id},
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_("Tag already associated with this host"),
            )

        # Get tag and host names for audit log
        tag_name = db.execute(
            text("SELECT name FROM tags WHERE id = :tag_id"), {"tag_id": tag_id}
        ).scalar()
        host_fqdn = db.execute(
            text("SELECT fqdn FROM host WHERE id = :host_id"), {"host_id": host_id}
        ).scalar()

        # Create association
        host_tag = HostTag(
            host_id=host_id, tag_id=tag_id, created_at=datetime.now(timezone.utc)
        )
        db.add(host_tag)
        db.commit()

        # Audit log tag addition to host
        from backend.services.audit_service import (
            ActionType,
            AuditService,
            EntityType,
            Result,
        )

        with session_local() as audit_session:
            AuditService.log(
                db=audit_session,
                user_id=user.id,
                username=current_user,
                action_type=ActionType.UPDATE,
                entity_type=EntityType.TAG,
                entity_id=tag_id,
                entity_name=tag_name,
                description=f"Added tag '{tag_name}' to host {host_fqdn}",
                result=Result.SUCCESS,
                details={"host_id": host_id, "host_fqdn": host_fqdn},
            )

        return {"message": _("Tag added to host successfully")}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_("Failed to add tag to host: %(error)s") % {"error": str(e)},
        ) from e


@router.delete("/hosts/{host_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_tag_from_host(
    host_id: str,
    tag_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Remove a tag from a host"""
    try:
        # Check if user has permission to edit tags
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
                raise HTTPException(status_code=401, detail=error_user_not_found())

            if user._role_cache is None:
                user.load_role_cache(session)

            if not user.has_role(SecurityRoles.EDIT_TAGS):
                raise HTTPException(
                    status_code=403,
                    detail=error_edit_tags_required(),
                )

        # Find the association
        host_tag = (
            db.query(HostTag)
            .filter(and_(HostTag.host_id == host_id, HostTag.tag_id == tag_id))
            .first()
        )

        if not host_tag:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_("Tag not associated with this host"),
            )

        # Get tag and host names for audit log
        from sqlalchemy import text

        tag_name = db.execute(
            text("SELECT name FROM tags WHERE id = :tag_id"), {"tag_id": tag_id}
        ).scalar()
        host_fqdn = db.execute(
            text("SELECT fqdn FROM host WHERE id = :host_id"), {"host_id": host_id}
        ).scalar()

        db.delete(host_tag)
        db.commit()

        # Audit log tag removal from host
        from backend.services.audit_service import (
            ActionType,
            AuditService,
            EntityType,
            Result,
        )

        with session_local() as audit_session:
            AuditService.log(
                db=audit_session,
                user_id=user.id,
                username=current_user,
                action_type=ActionType.UPDATE,
                entity_type=EntityType.TAG,
                entity_id=tag_id,
                entity_name=tag_name,
                description=f"Removed tag '{tag_name}' from host {host_fqdn}",
                result=Result.SUCCESS,
                details={"host_id": host_id, "host_fqdn": host_fqdn},
            )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_("Failed to remove tag from host: %(error)s") % {"error": str(e)},
        ) from e


@router.get("/hosts/{host_id}/tags", response_model=List[TagResponse])
async def get_host_tags(
    host_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Get all tags for a specific host"""
    try:
        from sqlalchemy import text

        # Verify host exists using raw SQL
        host_result = db.execute(
            text("SELECT id FROM host WHERE id = :host_id"), {"host_id": host_id}
        ).first()
        if not host_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_("Host not found")
            )

        # Get tags for this host using raw SQL to avoid ORM issues
        tag_results = db.execute(
            text("""
            SELECT t.id, t.name, t.description, t.created_at, t.updated_at
            FROM tags t
            JOIN host_tags ht ON t.id = ht.tag_id
            WHERE ht.host_id = :host_id
        """),
            {"host_id": host_id},
        ).fetchall()

        tag_responses = []
        for tag_row in tag_results:
            # Get host count for this tag using raw SQL
            try:
                host_count_result = db.execute(
                    text("SELECT COUNT(*) FROM host_tags WHERE tag_id = :tag_id"),
                    {"tag_id": tag_row.id},
                ).scalar()
                host_count = host_count_result or 0
            except Exception:
                host_count = 0

            tag_responses.append(
                TagResponse(
                    id=str(tag_row.id),
                    name=tag_row.name,
                    description=tag_row.description,
                    created_at=tag_row.created_at,
                    updated_at=tag_row.updated_at,
                    host_count=host_count,
                )
            )

        return tag_responses
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_("Failed to fetch host tags: %(error)s") % {"error": str(e)},
        ) from e
