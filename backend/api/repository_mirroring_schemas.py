# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Pydantic request models for the Repository Mirroring API.

Extracted from ``backend.api.repository_mirroring`` to keep that module under
the line-count cap.  Re-imported back there so the public API is unchanged.
"""

from typing import Optional

from pydantic import BaseModel, Field


class MirrorCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    package_manager: str = Field(..., min_length=1, max_length=20)
    upstream_url: str = Field(..., min_length=1, max_length=500)
    host_id: str
    suite: Optional[str] = None
    components: Optional[str] = None
    architectures: Optional[str] = None
    repoid: Optional[str] = None
    gpgkey_url: Optional[str] = None
    repo_alias: Optional[str] = None
    release: Optional[str] = None
    signing_key_url: Optional[str] = None
    bandwidth_cap_kbps: int = Field(default=0, ge=0)
    sync_cron: str = Field(default="0 4 * * *")
    network_tier: Optional[str] = None
    enabled: bool = True
    known_version_id: Optional[str] = None  # Phase 10.4.4 — set by the dropdown


class MirrorUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    upstream_url: Optional[str] = Field(None, min_length=1, max_length=500)
    suite: Optional[str] = None
    components: Optional[str] = None
    architectures: Optional[str] = None
    repoid: Optional[str] = None
    gpgkey_url: Optional[str] = None
    repo_alias: Optional[str] = None
    release: Optional[str] = None
    signing_key_url: Optional[str] = None
    bandwidth_cap_kbps: Optional[int] = Field(None, ge=0)
    sync_cron: Optional[str] = None
    network_tier: Optional[str] = None
    enabled: Optional[bool] = None
    known_version_id: Optional[str] = None  # Phase 10.4.4 — set by the dropdown


class MirrorSettingsRequest(BaseModel):
    mirror_root_path: Optional[str] = Field(None, min_length=1, max_length=500)
    integrity_check_cadence_hours: Optional[int] = Field(None, ge=1, le=168)
    retention_window_days: Optional[int] = Field(None, ge=0, le=365)
    default_bandwidth_cap_kbps: Optional[int] = Field(None, ge=0)
    snapshot_count_to_keep: Optional[int] = Field(None, ge=0, le=100)


class MirrorSetupInstallRequest(BaseModel):
    """Body for POST /setup-install/{host_id}."""

    package_manager: str = Field(
        ...,
        description="apt | dnf | zypper | pkg — drives which install plan is emitted",
    )
