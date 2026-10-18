# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
A host's compliance evidence report (ROADMAP 24.4).

The agent sends ``compliance_evidence_update`` when what the compliance checks
read changes (the effective sshd settings, sysctls, file modes, PAM, auditd,
AIDE...), else daily.  ``services/compliance_evidence.py`` stores it; the
scheduled compliance scan (``services/compliance_scan_tick.py``) re-scans the
host because its evidence is now newer than its latest scan.
"""

import logging
from typing import Any, Dict

from sqlalchemy.orm import Session

from backend.persistence.models import Host
from backend.services import compliance_evidence

logger = logging.getLogger(__name__)


def _error() -> Dict[str, Any]:
    return {"message_type": "error", "error_type": "host_not_registered", "data": {}}


async def handle_compliance_evidence_update(  # NOSONAR
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Store the host's compliance evidence.  Never raises."""
    host_id = getattr(connection, "host_id", None)
    if not host_id:
        logger.warning(
            "compliance_evidence_update with no host_id on the connection; ignored"
        )
        return _error()
    payload = (
        message_data.get("data") if "sections" not in message_data else message_data
    )
    payload = payload if isinstance(payload, dict) else {}
    host = db.query(Host).filter(Host.id == host_id).first()
    if host is None:
        logger.warning(
            "compliance_evidence_update for unknown host %s; ignored", host_id
        )
        return _error()
    row = compliance_evidence.apply_report(db, host, payload)
    db.commit()
    return {"message_type": "success", "data": {"stored": row is not None}}
