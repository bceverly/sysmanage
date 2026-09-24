# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Which pending OpenBSD syspatches are SECURITY fixes.

The agent reports what ``syspatch -c`` lists: patch ids like ``001_xserver``
and nothing else. Whether an erratum is a security fix or a reliability fix is
published only on openbsd.org's errata pages -- which the advisory catalog
already ingests (source ``openbsd``). The agent used to label every syspatch
"security"; on OpenBSD 7.8 that was wrong for 27 of 57 errata (2026-09-23).

So the server classifies: a patch id the catalog lists as a SECURITY erratum
for the host's release is ``security``; anything else is ``system`` -- which
every syspatch certainly is -- rather than a guess in either direction.
"""

import logging
import re
from typing import Dict, Iterable

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.persistence.partitions import PARTITION_SHARED, partition_session

logger = logging.getLogger(__name__)

SYSPATCH = "syspatch"


def _release(db: Session, host_id) -> str:
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    match = re.match(
        r"(\d+\.\d+)", (getattr(host, "platform_release", None) or "").strip()
    )
    return match.group(1) if match else ""


def syspatch_update_types(
    db: Session, host_id, updates: Iterable[dict]
) -> Dict[str, str]:
    """``{patch_id: "security" | "system"}`` for the syspatch rows in ``updates``."""
    patch_ids = {
        u.get("package_name") for u in updates if u.get("package_manager") == SYSPATCH
    }
    patch_ids.discard(None)
    if not patch_ids:
        return {}
    types = {patch_id: "system" for patch_id in patch_ids}
    release = _release(db, host_id)
    if not release:
        return types
    try:
        with partition_session(PARTITION_SHARED) as shared:
            rows = (
                shared.query(models.SharedAdvisoryPackage.package_name)
                .join(
                    models.SharedAdvisory,
                    models.SharedAdvisory.id
                    == models.SharedAdvisoryPackage.advisory_row_id,
                )
                .filter(
                    models.SharedAdvisory.source == "openbsd",
                    models.SharedAdvisory.advisory_type == "security",
                    models.SharedAdvisoryPackage.package_manager == SYSPATCH,
                    models.SharedAdvisoryPackage.release == f"openbsd:{release}",
                    models.SharedAdvisoryPackage.package_name.in_(patch_ids),
                )
                .all()
            )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # No catalog (advisories never refreshed, or the table is absent on
        # this install): every syspatch is still a base-system patch.
        logger.warning(
            "syspatch classification unavailable for OpenBSD %s: %s", release, exc
        )
        return types
    for (patch_id,) in rows:
        types[patch_id] = "security"
    return types


def classify_syspatch_updates(db: Session, host_id, updates) -> None:
    """Set each syspatch row's ``is_security_update`` from the errata catalog
    (in place), so the update handler's usual mapping yields security/system."""
    types = syspatch_update_types(db, host_id, updates)
    for update in updates:
        if update.get("package_manager") == SYSPATCH:
            update["is_security_update"] = (
                types.get(update.get("package_name")) == "security"
            )
            update["is_system_update"] = True
