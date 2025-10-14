"""Pydantic models for package update management."""

from typing import List, Optional

from pydantic import BaseModel, validator


class PackageUpdateInfo(BaseModel):
    """Represents package update information from agent."""

    package_name: str
    current_version: Optional[str] = None
    available_version: str
    package_manager: str
    source: Optional[str] = None
    is_security_update: bool = False
    is_system_update: bool = False
    requires_reboot: bool = False
    update_size_bytes: Optional[int] = None
    bundle_id: Optional[str] = None
    repository: Optional[str] = None
    channel: Optional[str] = None


class UpdatesReport(BaseModel):
    """Complete update report from agent."""

    available_updates: List[PackageUpdateInfo]
    total_updates: int
    security_updates: int
    system_updates: int
    application_updates: int
    platform: str
    requires_reboot: bool = False


class UpdateExecutionRequest(BaseModel):
    """Request to execute package updates."""

    host_ids: List[str]
    package_names: List[str]
    package_managers: Optional[List[str]] = None

    @validator("host_ids")
    def validate_host_ids(cls, host_ids):  # pylint: disable=no-self-argument
        if not host_ids:
            raise ValueError("host_ids cannot be empty")
        return host_ids

    @validator("package_names")
    def validate_package_names(cls, package_names):  # pylint: disable=no-self-argument
        if not package_names:
            raise ValueError("package_names cannot be empty")
        return package_names

    @validator("package_managers", pre=True)
    def validate_package_managers(
        cls, package_managers
    ):  # pylint: disable=no-self-argument
        if package_managers == []:
            return None
        return package_managers


class UpdateStatsSummary(BaseModel):
    """Summary statistics for updates across hosts."""

    total_hosts: int
    hosts_with_updates: int
    total_updates: int
    security_updates: int
    system_updates: int
    application_updates: int
