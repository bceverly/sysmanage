# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Per-channel private mirrors for the agent's OWN install channels (Phase 12).

Phase 11.1 mirrors OS packages and repoints hosts that are already managed.
This is the bootstrap end of the same loop: it tells provisioning where to
install the *agent* from, so a host coming up in an air-gapped site — with no
route to the Launchpad PPA, COPR, OBS, winget or the Homebrew tap — still gets
an agent and enrolls.

Configuration is per CHANNEL, not per distro: one ``copr`` row covers
Fedora/RHEL/Rocky/Alma, and a new RHEL-family distro inherits it for free.

The list of configurable channels and the URL validation both come from the
provisioning engine, which is the same code that renders the install commands.
Duplicating either here would let the UI accept a channel or a URL that the
renderer then refuses — a mismatch whose only symptom is a provisioned host
that silently never enrolls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.db import get_db

router = APIRouter(
    prefix="/api/v1/airgap/agent-mirrors",
    tags=["airgap-agent-mirrors"],
    dependencies=[Depends(JWTBearer())],
)


class AgentMirrorPayload(BaseModel):
    channel: str
    mirror_url: str
    enabled: bool = True
    notes: Optional[str] = None


def _engine():
    """The provisioning engine, or None when it isn't licensed/loaded."""
    return module_loader.get_module("provisioning_engine")


@router.get("")
def list_agent_mirrors(db: Session = Depends(get_db)):
    """Configured mirrors plus the channels that MAY be configured.

    ``available_channels`` is empty when the engine isn't loaded rather than a
    hardcoded fallback list — the UI then shows nothing to configure, which is
    honest, instead of offering channels nothing will ever read.
    """
    engine = _engine()
    channels = engine.agent_mirror_channels() if engine else []
    rows = (
        db.query(models.AirgapAgentChannelMirror)
        .order_by(models.AirgapAgentChannelMirror.channel)
        .all()
    )
    return {
        "mirrors": [row.to_dict() for row in rows],
        "available_channels": channels,
    }


@router.put("/{channel}")
def upsert_agent_mirror(
    channel: str,
    payload: AgentMirrorPayload,
    db: Session = Depends(get_db),
):
    """Create or update one channel's mirror.

    Validation happens HERE, when the operator types the URL — not hours later
    when a provisioning job renders a bootstrap script and refuses it.
    """
    engine = _engine()
    if engine is None:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=_("Provisioning engine is not licensed on this server."),
        )
    if channel not in engine.agent_mirror_channels():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_("Channel '{channel}' cannot be mirrored.").format(channel=channel),
        )
    if not engine.is_valid_mirror_url(payload.mirror_url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_(
                "Mirror URL must be an http/https/ftp/file URL with no spaces, "
                "quotes or shell metacharacters."
            ),
        )

    row = (
        db.query(models.AirgapAgentChannelMirror)
        .filter(models.AirgapAgentChannelMirror.channel == channel)
        .first()
    )
    if row is None:
        row = models.AirgapAgentChannelMirror(channel=channel)
        db.add(row)
    row.mirror_url = payload.mirror_url
    row.enabled = payload.enabled
    row.notes = payload.notes
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row.to_dict()


@router.delete("/{channel}")
def delete_agent_mirror(channel: str, db: Session = Depends(get_db)):
    """Remove a channel's mirror; that channel reverts to installing upstream."""
    row = (
        db.query(models.AirgapAgentChannelMirror)
        .filter(models.AirgapAgentChannelMirror.channel == channel)
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_("No mirror configured for channel '{channel}'.").format(
                channel=channel
            ),
        )
    db.delete(row)
    db.commit()
    return {"deleted": channel}
