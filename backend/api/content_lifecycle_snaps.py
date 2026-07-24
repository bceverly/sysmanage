# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Snap-materialize helper for content-view publish (Phase 17.1, Slice 3).

Extracted from ``backend.api.content_lifecycle`` to keep that module under the
line-count cap.  When a content view is published, any snaps CAPTURED into its
member mirrors are materialized into the same version store so they ride the
air-gap ISO unchanged — gated on the Pro+ ``snap_proxy_engine`` being licensed.
"""

from typing import List

from sqlalchemy.orm import Session

from backend.licensing.module_loader import module_loader
from backend.persistence import models


def _cv_captured_snap_mirrors(cv, tenant_db: Session) -> List[str]:
    """Names of the CV's member mirrors that have CAPTURED snap content."""
    mirror_ids = [m.mirror_id for m in cv.repos if m.mirror_id]
    if not mirror_ids:
        return []
    rows = (
        tenant_db.query(models.MirrorRepository.name)
        .join(
            models.MirrorSnapContent,
            models.MirrorSnapContent.repository_id == models.MirrorRepository.id,
        )
        .filter(
            models.MirrorRepository.id.in_(mirror_ids),
            models.MirrorSnapContent.capture_status == "CAPTURED",
        )
        .distinct()
        .all()
    )
    return [r[0] for r in rows]


def append_snap_materialize(commands, cv, tenant_db, mirror_root, store_parent):
    """Append snap-materialize commands to a publish plan, in place.

    No-op unless the CV has CAPTURED snaps AND the snap_proxy_engine is loaded;
    appended AFTER the repo-materialize commands (it freezes its own snap
    subtree under ``store_parent``)."""
    if not store_parent:
        return
    names = _cv_captured_snap_mirrors(cv, tenant_db)
    if not names:
        return
    snap_engine = module_loader.get_module("snap_proxy_engine")
    if snap_engine is None:
        return
    plan = snap_engine.build_snap_materialize_plan(mirror_root, names, store_parent)
    commands.extend(plan.get("commands", []))
