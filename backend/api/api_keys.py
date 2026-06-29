"""
API-key management endpoints — Phase 13.2 (API Completeness).

CRUD for a user's own programmatic-access keys:

  * ``POST   /api/api-keys``        — mint a key (plaintext returned ONCE)
  * ``GET    /api/api-keys``        — list the caller's keys (never the secret)
  * ``GET    /api/api-keys/{id}``   — fetch one of the caller's keys
  * ``DELETE /api/api-keys/{id}``   — revoke a key

Keys are scoped to the authenticated user and inherit that user's permissions.
Management actions (create/revoke) deliberately reject API-key authentication —
a key cannot mint or revoke keys — so an automation credential can't escalate
into self-replication or lock out its owner.  Reads are allowed under either
auth type.
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import sessionmaker

from backend.auth.api_key import API_KEY_PREFIX, generate_api_key, looks_like_api_key
from backend.auth.auth_bearer import JWTBearer, get_current_tenant, get_current_user
from backend.i18n import _
from backend.persistence import db, models

router = APIRouter()


class ApiKeyCreate(BaseModel):
    """Request body for minting a new API key."""

    name: str = Field(..., min_length=1, max_length=120)
    expires_at: Optional[datetime] = None
    scopes: Optional[str] = None


class ApiKeyOut(BaseModel):
    """An API key as returned to clients — never carries the secret."""

    id: str
    user_id: str
    name: str
    key_prefix: str
    scopes: Optional[str] = None
    tenant_id: Optional[str] = None
    is_active: bool
    created_at: Optional[str] = None
    last_used_at: Optional[str] = None
    expires_at: Optional[str] = None
    revoked_at: Optional[str] = None


class ApiKeyCreated(ApiKeyOut):
    """Creation response — includes the plaintext key shown exactly once."""

    key: str = Field(
        ...,
        description=(
            "The plaintext API key. Shown only at creation — store it now; "
            "it cannot be retrieved again."
        ),
    )


def forbid_api_key_auth(request: Request) -> None:
    """Reject the request when it is authenticated with an API key.

    Guards key-management actions so an API key cannot create or revoke keys
    (no privilege self-replication, no locking out the owner).
    """
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and looks_like_api_key(auth[len("Bearer ") :]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_("API keys cannot be managed with API-key authentication."),
        )


def _session():
    """Open a session on the MAIN engine, where users + api keys live.

    User identities are server-global (they live with the registry, not in a
    per-tenant database), and ``api_key`` rows FK ``user.id``, so both always
    resolve on ``db.get_engine()`` regardless of the active tenant — mirroring
    ``profile`` and ``require_authenticated_user``.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )
    return session_local()


def _resolve_user(session, current_user: str) -> models.User:
    """Load the authenticated user by login id, or raise 401."""
    user = session.query(models.User).filter(models.User.userid == current_user).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_("User not found.")
        )
    return user


@router.post(
    "",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(JWTBearer()), Depends(forbid_api_key_auth)],
    summary="Create an API key",
)
async def create_api_key(
    payload: ApiKeyCreate,
    current_user: str = Depends(get_current_user),
    tenant_id: Optional[str] = Depends(get_current_tenant),
):
    """Mint a new API key for the authenticated user.

    The plaintext key is returned **once** in the ``key`` field — only its hash
    is stored, so it can never be retrieved again.  In multi-tenant mode the key
    is pinned to the caller's active tenant.
    """
    full_key, key_hash, key_prefix = generate_api_key()
    with _session() as session:
        user = _resolve_user(session, current_user)
        api_key = models.ApiKey(
            user_id=user.id,
            name=payload.name.strip(),
            key_prefix=key_prefix,
            key_hash=key_hash,
            scopes=payload.scopes,
            tenant_id=tenant_id,
            expires_at=payload.expires_at,
        )
        session.add(api_key)
        session.commit()
        session.refresh(api_key)
        return {**api_key.to_dict(), "key": full_key}


@router.get(
    "",
    response_model=List[ApiKeyOut],
    dependencies=[Depends(JWTBearer())],
    summary="List your API keys",
)
async def list_api_keys(current_user: str = Depends(get_current_user)):
    """List the authenticated user's API keys (secrets are never returned)."""
    with _session() as session:
        user = _resolve_user(session, current_user)
        keys = (
            session.query(models.ApiKey)
            .filter(models.ApiKey.user_id == user.id)
            .order_by(models.ApiKey.created_at.desc())
            .all()
        )
        return [k.to_dict() for k in keys]


@router.get(
    "/{key_id}",
    response_model=ApiKeyOut,
    dependencies=[Depends(JWTBearer())],
    summary="Get one of your API keys",
)
async def get_api_key(key_id: str, current_user: str = Depends(get_current_user)):
    """Fetch a single API key owned by the authenticated user."""
    with _session() as session:
        user = _resolve_user(session, current_user)
        key = (
            session.query(models.ApiKey)
            .filter(
                models.ApiKey.id == key_id,
                models.ApiKey.user_id == user.id,
            )
            .first()
        )
        if key is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_("API key not found.")
            )
        return key.to_dict()


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(JWTBearer()), Depends(forbid_api_key_auth)],
    summary="Revoke an API key",
)
async def revoke_api_key(key_id: str, current_user: str = Depends(get_current_user)):
    """Revoke (deactivate) an API key owned by the authenticated user.

    Idempotent in effect: the key is marked inactive and stamped with a
    revocation time; subsequent authentication with it fails immediately.
    """
    with _session() as session:
        user = _resolve_user(session, current_user)
        key = (
            session.query(models.ApiKey)
            .filter(
                models.ApiKey.id == key_id,
                models.ApiKey.user_id == user.id,
            )
            .first()
        )
        if key is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_("API key not found.")
            )
        key.is_active = False
        key.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Re-exported for callers/tests that want the canonical key prefix.
__all__ = ["router", "API_KEY_PREFIX"]
