# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Asset tag CSV import / export and held tags (Phase 23.2 S5).

The import is two calls with the same file: ``preview`` shows what every row
would do, ``apply`` re-plans against the database as it is at that moment and
writes.  Refusals travel as codes the UI translates.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.asset_tags import _require_role, load_scheme
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.services import asset_tag_csv as tag_csv
from backend.services.audit_service import ActionType, AuditService, EntityType
from backend.utils.verbosity_logger import sanitize_log

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(JWTBearer())])


class CsvBody(BaseModel):
    csv: str


def _rows_or_422(db: Session, body: CsvBody, run) -> Dict[str, Any]:
    try:
        rows = run(db, body.csv)
    except tag_csv.CsvError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code}) from exc
    return {
        "rows": [row.public() for row in rows],
        "summary": tag_csv.summary(rows),
    }


@router.post("/asset-tags/import/preview")
async def preview_import(
    body: CsvBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """What every row of the file would do.  Writes nothing."""
    _require_role(current_user)
    return _rows_or_422(
        db,
        body,
        lambda session, text: tag_csv.plan(session, text, load_scheme(session)),
    )


@router.post("/asset-tags/import/apply")
async def apply_import(
    body: CsvBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Re-plan the file and write its ``assign`` and ``hold`` rows."""
    _require_role(current_user)
    result = _rows_or_422(
        db,
        body,
        lambda session, text: tag_csv.apply(
            session, text, load_scheme(session), current_user.id, current_user.userid
        ),
    )
    db.commit()
    logger.info(
        "Asset tag CSV import by %s: %s",
        sanitize_log(current_user.userid),
        sanitize_log(result["summary"]),
    )
    return result


@router.get("/asset-tags/export")
async def export_tags(db: Session = Depends(get_tenant_db)) -> Response:
    """Every machine and held tag as CSV -- re-importable as it stands."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Response(
        content=tag_csv.export(db),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="asset_tags_{stamp}.csv"'
        },
    )


@router.get("/asset-tags/held")
async def list_held(db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    """Tags waiting for a machine to report in."""
    holds = db.query(models.HeldAssetTag).order_by(models.HeldAssetTag.asset_tag).all()
    return {
        "held": [
            {
                "id": str(h.id),
                "kind": h.kind,
                "identifier": h.identifier,
                "asset_tag": h.asset_tag,
                "created_at": h.created_at.isoformat() if h.created_at else None,
                "created_by": h.created_by,
            }
            for h in holds
        ]
    }


@router.delete("/asset-tags/held/{held_id}")
async def release_held(
    held_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Drop a held tag; the machine will not receive it."""
    _require_role(current_user)
    try:
        key = uuid.UUID(held_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": "held_not_found"}) from exc
    hold = db.get(models.HeldAssetTag, key)
    if hold is None:
        raise HTTPException(status_code=404, detail={"code": "held_not_found"})
    AuditService.log(
        db=db,
        action_type=ActionType.DELETE,
        entity_type=EntityType.HOST,
        entity_name=hold.asset_tag,
        description=_("Held asset tag %s released") % hold.asset_tag,
        user_id=current_user.id,
        username=current_user.userid,
        details={"kind": hold.kind, "identifier": hold.identifier},
        commit=False,
    )
    db.delete(hold)
    db.commit()
    return {"released": str(key)}
