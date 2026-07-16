# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Server-wide configuration singleton.

Holds settings that describe *this* SysManage server instance rather
than any managed host.  Currently just the air-gap ``server_role``
(Phase 12 — moved out of ``sysmanage.yaml`` so operators set it via
Settings → Server Role instead of hand-editing a config file and
restarting).

Single-row table: a fixed sentinel UUID guarantees there's exactly one
row.  Future server-wide knobs add columns here rather than new tables.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSON

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

import uuid

# Fixed sentinel id so the row is a true singleton (same pattern as
# ``SINGLETON_MIRROR_SETTINGS_ID``).  Distinct value so the two
# singletons never collide.
SINGLETON_SERVER_CONFIG_ID = uuid.UUID("00000000-0000-0000-0000-000000000004")

# The air-gap topology roles.  ``standard`` = no air gap (the default
# for every ordinary deployment).  ``collector`` = public/online half
# that mirrors upstream and builds ISOs.  ``repository`` = private/
# disconnected half that ingests ISOs and serves a local mirror.
VALID_SERVER_ROLES = ("standard", "collector", "repository")
DEFAULT_SERVER_ROLE = "standard"

# Phase 12: multi-site federation role.  INDEPENDENT of the air-gap
# ``server_role`` axis above — a server can be, say, an air-gap
# ``collector`` AND a federation ``site`` at the same time.  ``none`` =
# not part of any federation (the default).  ``coordinator`` = aggregates
# subordinate site servers.  ``site`` = a subordinate that reports up to a
# coordinator.
VALID_FEDERATION_ROLES = ("none", "coordinator", "site")
DEFAULT_FEDERATION_ROLE = "none"


class ServerConfiguration(Base):
    """Singleton row of server-instance-wide settings."""

    __tablename__ = "server_configuration"

    id = Column(GUID(), primary_key=True, default=lambda: SINGLETON_SERVER_CONFIG_ID)
    # The air-gap topology role (renamed from ``server_role`` once
    # ``federation_role`` was added — see migration n8agrole).
    air_gap_role = Column(String(40), nullable=False, default=DEFAULT_SERVER_ROLE)
    # Block-device node (e.g. /dev/sr0) the operator picked as the
    # air-gap import drive on an Air-Gap Repository server.  NULL until
    # chosen; only meaningful when air_gap_role == 'repository'.
    airgap_import_device = Column(String(200), nullable=True)
    # Phase 12: federation role — separate axis from air_gap_role.
    federation_role = Column(
        String(40), nullable=False, default=DEFAULT_FEDERATION_ROLE
    )
    # Phase 13.1.H (config classification): a key/value bag of server-scoped
    # runtime settings that migrated out of sysmanage.yaml (jwt timeouts,
    # message-queue tunables, monitoring, etc.).  Edited via Settings → the
    # config layer reads here first, then falls back to YAML.  See
    # docs/planning/config-classification.md and backend/config/settings_service.py.
    settings = Column(JSON, nullable=True)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self) -> dict:
        return {
            "air_gap_role": self.air_gap_role,
            "airgap_import_device": self.airgap_import_device,
            "federation_role": self.federation_role,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
