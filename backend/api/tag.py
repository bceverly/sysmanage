"""
Tag management API endpoints
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import get_current_user
from backend.persistence.db import get_db
from backend.persistence.models import Tag, Host, HostTag
from backend.i18n import _

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

    id: int
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    host_count: int = 0

    class Config:
        from_attributes = True


class TagWithHostsResponse(BaseModel):
    """Schema for tag with associated hosts"""

    id: int
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    hosts: List[dict]

    class Config:
        from_attributes = True


class HostTagRequest(BaseModel):
    """Schema for adding/removing tag from host"""

    host_id: int
    tag_id: int


@router.get("/tags", response_model=List[TagResponse])
async def get_tags(
    db: Session = Depends(get_db), current_user: str = Depends(get_current_user)
):
    """Get all tags"""
    try:
        # Query all tags with host count
        stmt = select(Tag).order_by(Tag.name)
        result = db.execute(stmt)
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
                "id": tag.id,
                "name": tag.name,
                "description": tag.description,
                "created_at": tag.created_at,
                "updated_at": tag.updated_at,
                "host_count": host_count,
            }
            tag_responses.append(TagResponse(**tag_dict))

        return tag_responses
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_("Failed to fetch tags: %(error)s") % {"error": str(e)},
        ) from e


@router.post("/tags", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(
    tag_data: TagCreate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Create a new tag"""
    try:
        # Check if tag with same name already exists
        existing_tag = db.query(Tag).filter(Tag.name == tag_data.name).first()
        if existing_tag:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_("Tag with this name already exists"),
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

        return TagResponse(
            id=new_tag.id,
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
    tag_id: int,
    tag_data: TagUpdate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Update an existing tag"""
    try:
        # Find the tag
        tag = db.query(Tag).filter(Tag.id == tag_id).first()
        if not tag:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_("Tag not found")
            )

        # Check if new name conflicts with existing tag
        if tag_data.name and tag_data.name != tag.name:
            existing_tag = db.query(Tag).filter(Tag.name == tag_data.name).first()
            if existing_tag:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=_("Tag with this name already exists"),
                )
            tag.name = tag_data.name

        if tag_data.description is not None:
            tag.description = tag_data.description

        tag.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(tag)

        # Get host count safely
        try:
            host_count = tag.hosts.count() if hasattr(tag, "hosts") and tag.hosts else 0
        except Exception:
            host_count = 0

        return TagResponse(
            id=tag.id,
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
    tag_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Delete a tag"""
    try:
        # Find the tag
        tag = db.query(Tag).filter(Tag.id == tag_id).first()
        if not tag:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_("Tag not found")
            )

        db.delete(tag)
        db.commit()
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_("Failed to delete tag: %(error)s") % {"error": str(e)},
        ) from e


@router.get("/tags/{tag_id}/hosts", response_model=TagWithHostsResponse)
async def get_tag_hosts(
    tag_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Get all hosts associated with a specific tag"""
    try:
        # Find the tag with hosts
        tag = db.query(Tag).filter(Tag.id == tag_id).first()
        if not tag:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_("Tag not found")
            )

        # Get associated hosts
        hosts = tag.hosts.all()
        host_list = []
        for host in hosts:
            host_list.append(
                {
                    "id": host.id,
                    "fqdn": host.fqdn,
                    "ipv4": host.ipv4,
                    "ipv6": host.ipv6,
                    "active": host.active,
                    "status": host.status,
                }
            )

        return TagWithHostsResponse(
            id=tag.id,
            name=tag.name,
            description=tag.description,
            created_at=tag.created_at,
            updated_at=tag.updated_at,
            hosts=host_list,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_("Failed to fetch tag hosts: %(error)s") % {"error": str(e)},
        ) from e


@router.post("/hosts/{host_id}/tags/{tag_id}", status_code=status.HTTP_201_CREATED)
async def add_tag_to_host(
    host_id: int,
    tag_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Add a tag to a host"""
    try:
        # Verify host exists
        host = db.query(Host).filter(Host.id == host_id).first()
        if not host:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_("Host not found")
            )

        # Verify tag exists
        tag = db.query(Tag).filter(Tag.id == tag_id).first()
        if not tag:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_("Tag not found")
            )

        # Check if association already exists
        existing = (
            db.query(HostTag)
            .filter(and_(HostTag.host_id == host_id, HostTag.tag_id == tag_id))
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_("Tag already associated with this host"),
            )

        # Create association
        host_tag = HostTag(
            host_id=host_id, tag_id=tag_id, created_at=datetime.now(timezone.utc)
        )
        db.add(host_tag)
        db.commit()

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
    host_id: int,
    tag_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Remove a tag from a host"""
    try:
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

        db.delete(host_tag)
        db.commit()
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
    host_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Get all tags for a specific host"""
    try:
        # Verify host exists
        host = db.query(Host).filter(Host.id == host_id).first()
        if not host:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_("Host not found")
            )

        # Get tags for this host
        tags = host.tags.all()
        tag_responses = []
        for tag in tags:
            # Get host count safely
            try:
                host_count = (
                    tag.hosts.count() if hasattr(tag, "hosts") and tag.hosts else 0
                )
            except Exception:
                host_count = 0

            tag_responses.append(
                TagResponse(
                    id=tag.id,
                    name=tag.name,
                    description=tag.description,
                    created_at=tag.created_at,
                    updated_at=tag.updated_at,
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
