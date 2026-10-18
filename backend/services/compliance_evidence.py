# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Store a host's compliance evidence (ROADMAP 24.4).

The agent's ``compliance_evidence_update`` carries what the compliance
checks read, in the engine's ``host_data`` shapes.  This keeps the latest
per host (``HostComplianceEvidence``) and hands it to the engine's scan.

Only the sections the engine knows are kept, each with the type its checks
expect; anything else -- a wrong type, an unknown section -- is stored as
not collected (``None``), so a malformed report can lower what the scan can
judge but never invent a pass.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.persistence import models

logger = logging.getLogger(__name__)

# section -> the type the engine's checks read
SECTION_TYPES = {
    "ssh_config": dict,
    "sysctl": dict,
    "kernel_modules": dict,
    "file_permissions": dict,
    "services": dict,
    "login_defs": dict,
    "faillock_config": dict,
    "auditd_config": dict,
    "chrony_config": dict,
    "aide_rules": dict,
    "pam_modules": list,
    "audit_rules": list,
    "umask": str,
    "fips_enabled": bool,
}
MAX_SECTIONS_BYTES = 512 * 1024
_MAX_STATUS = 32


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _when(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def clean_sections(raw: Any) -> Dict[str, Any]:
    """Every known section, its value or None (not collected)."""
    raw = raw if isinstance(raw, dict) else {}
    cleaned = {}
    for name, kind in SECTION_TYPES.items():
        value = raw.get(name)
        cleaned[name] = value if isinstance(value, kind) else None
    return cleaned


def clean_sources(raw: Any) -> Dict[str, str]:
    raw = raw if isinstance(raw, dict) else {}
    return {
        name: raw[name][:_MAX_STATUS]
        for name in SECTION_TYPES
        if isinstance(raw.get(name), str)
    }


def apply_report(
    db: Session,
    host: models.Host,
    payload: Dict[str, Any],
    now: Optional[datetime] = None,
) -> Optional[models.HostComplianceEvidence]:
    """Store ``host``'s evidence; the row, or None when the report was
    refused (too large).  The caller commits."""
    sections = clean_sections(payload.get("sections"))
    encoded = json.dumps(sections, sort_keys=True, default=str)
    if len(encoded) > MAX_SECTIONS_BYTES:
        logger.warning(
            "compliance evidence from host %s (%s) is %d bytes, over the %d cap; "
            "ignored -- its rules stay as last reported",
            host.id, host.fqdn, len(encoded), MAX_SECTIONS_BYTES,
        )  # fmt: skip
        return None
    row = (
        db.query(models.HostComplianceEvidence)
        .filter(models.HostComplianceEvidence.host_id == host.id)
        .first()
    )
    if row is None:
        row = models.HostComplianceEvidence(host_id=host.id)
        db.add(row)
    row.platform = str(payload.get("platform") or "")[:32] or None
    row.sections = encoded
    row.sources = json.dumps(clean_sources(payload.get("sources")), sort_keys=True)
    row.collected_at = _when(payload.get("collected_at"))
    row.received_at = now or _now()
    return row


def host_sections(db: Session, host_id) -> Optional[Dict[str, Any]]:
    """The stored sections for ``host_id``, or None when it never reported."""
    row = (
        db.query(models.HostComplianceEvidence)
        .filter(models.HostComplianceEvidence.host_id == host_id)
        .first()
    )
    if row is None:
        return None
    try:
        return clean_sections(json.loads(row.sections))
    except (TypeError, ValueError):
        logger.warning("unreadable compliance evidence for host %s; ignored", host_id)
        return None
