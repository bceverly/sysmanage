"""
Queue Management API endpoints for managing message queues.
"""

import asyncio
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, sessionmaker

from backend.auth.auth_bearer import get_current_user
from backend.i18n import _
from backend.persistence import db, models
from backend.persistence.db import get_db
from backend.persistence.models import MessageQueue
from backend.security.roles import SecurityRoles
from backend.websocket.queue_manager import server_queue_manager

router = APIRouter()


def _get_failed_messages_sync() -> List[Dict[str, Any]]:
    """
    Synchronous helper function to retrieve failed messages.
    This runs in a thread pool to avoid blocking the event loop.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        try:
            # Query for expired messages
            failed_messages = (
                session.query(MessageQueue)
                .filter(MessageQueue.expired_at.is_not(None))
                .order_by(MessageQueue.expired_at.desc())
                .all()
            )

            result = []
            for message in failed_messages:
                # Deserialize message data to get type information
                try:
                    message_data = server_queue_manager.deserialize_message_data(
                        message
                    )
                    message_type = message_data.get("type", "unknown")
                except Exception:
                    message_type = "unknown"

                result.append(
                    {
                        "id": message.message_id,
                        "type": message_type,
                        "direction": (
                            message.direction.value
                            if hasattr(message.direction, "value")
                            else message.direction
                        ),
                        "timestamp": (
                            message.expired_at.isoformat()
                            if message.expired_at
                            else None
                        ),
                        "created_at": (
                            message.created_at.isoformat()
                            if message.created_at
                            else None
                        ),
                        "host_id": message.host_id,
                        "priority": message.priority,
                        "data": message.message_data,  # Raw message data for viewing
                    }
                )

            return result
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch failed messages: {str(e)}",
            ) from e


@router.get("/failed")
async def get_failed_messages(
    current_user=Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """
    Get all expired/failed messages from the queue.
    Runs the database query in a thread pool to avoid blocking the event loop.
    """
    # Run the synchronous database operation in a thread pool
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _get_failed_messages_sync)


@router.delete("/failed")
async def delete_failed_messages(
    message_ids: List[str],
    db_session: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Delete selected failed messages from the queue.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_session.get_bind()
    )
    with session_local() as session:
        # Check if user has permission to delete queue messages
        auth_user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not auth_user:
            raise HTTPException(status_code=401, detail=_("User not found"))
        if auth_user._role_cache is None:
            auth_user.load_role_cache(session)
        if not auth_user.has_role(SecurityRoles.DELETE_QUEUE_MESSAGE):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: DELETE_QUEUE_MESSAGE role required"),
            )
    try:
        if not message_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No message IDs provided",
            )

        # Delete the specified messages
        deleted_count = (
            db_session.query(MessageQueue)
            .filter(
                MessageQueue.message_id.in_(message_ids),
                MessageQueue.expired_at.is_not(
                    None
                ),  # Only allow deleting expired messages
            )
            .delete(synchronize_session=False)
        )

        db_session.commit()

        return {
            "deleted_count": deleted_count,
            "message": f"Successfully deleted {deleted_count} expired messages",
        }
    except Exception as e:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete failed messages: {str(e)}",
        ) from e


def _get_message_details_sync(message_id: str) -> Dict[str, Any]:
    """
    Synchronous helper function to retrieve message details.
    This runs in a thread pool to avoid blocking the event loop.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        try:
            message = (
                session.query(MessageQueue)
                .filter(
                    MessageQueue.message_id == message_id,
                    MessageQueue.expired_at.is_not(None),
                )
                .first()
            )

            if not message:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Message not found or not expired",
                )

            # Deserialize and format message data for display
            try:
                message_data = server_queue_manager.deserialize_message_data(message)
            except Exception as e:
                # Log the full error for debugging but don't expose details to external users
                from backend.utils.verbosity_logger import get_logger

                logger = get_logger(__name__)
                logger.error(
                    f"Failed to deserialize message {message.message_id}: {str(e)}"
                )
                message_data = {
                    "error": "Failed to deserialize message data",
                    "type": "deserialization_error",
                }

            return {
                "id": message.message_id,
                "type": message_data.get("type", "unknown"),
                "direction": (
                    message.direction.value
                    if hasattr(message.direction, "value")
                    else message.direction
                ),
                "status": (
                    message.status.value
                    if hasattr(message.status, "value")
                    else message.status
                ),
                "priority": message.priority,
                "host_id": message.host_id,
                "created_at": (
                    message.created_at.isoformat() if message.created_at else None
                ),
                "expired_at": (
                    message.expired_at.isoformat() if message.expired_at else None
                ),
                "started_at": (
                    message.started_at.isoformat() if message.started_at else None
                ),
                "completed_at": (
                    message.completed_at.isoformat() if message.completed_at else None
                ),
                "scheduled_at": (
                    message.scheduled_at.isoformat() if message.scheduled_at else None
                ),
                "data": message_data,  # Parsed message data
            }
        except HTTPException:
            raise
        except Exception as e:
            # Log the full error for debugging but don't expose details to external users
            from backend.utils.verbosity_logger import get_logger

            logger = get_logger(__name__)
            logger.error(
                f"Failed to fetch message details for message {message_id}: {str(e)}"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch message details",
            ) from e


@router.get("/failed/{message_id}")
async def get_message_details(
    message_id: str,
    current_user=Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get detailed information about a specific message.
    Runs the database query in a thread pool to avoid blocking the event loop.
    """
    # Run the synchronous database operation in a thread pool
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _get_message_details_sync, message_id)
