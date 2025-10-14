"""
Pydantic models for package management API.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class PackageInfo(BaseModel):
    """Package information model for API responses."""

    name: str
    version: str
    description: Optional[str] = None
    package_manager: str


class PackageManagerSummary(BaseModel):
    """Summary of packages per package manager."""

    package_manager: str
    package_count: int


class OSPackageSummary(BaseModel):
    """Summary of packages per OS/version combination."""

    os_name: str
    os_version: str
    package_managers: List[PackageManagerSummary]
    total_packages: int


class PackageInstallRequest(BaseModel):
    """Request model for package installation."""

    package_names: List[str]
    requested_by: str


class PackageInstallResponse(BaseModel):
    """Response model for package installation."""

    success: bool
    message: str
    request_id: str  # The UUID that groups all packages in this request


class PackageUninstallRequest(BaseModel):
    """Request model for package uninstallation."""

    package_names: List[str]
    requested_by: str


class PackageUninstallResponse(BaseModel):
    """Response model for package uninstallation."""

    success: bool
    message: str
    request_id: str  # The UUID that groups all packages in this request


class PackageItem(BaseModel):
    """Individual package within an installation request."""

    package_name: str
    package_manager: str


class InstallationHistoryItem(BaseModel):
    """Response model for installation history item - now UUID-based."""

    request_id: str  # The UUID that groups packages
    requested_by: str
    status: str
    operation_type: str  # install or uninstall
    requested_at: datetime
    completed_at: Optional[datetime] = None
    installation_log: Optional[str] = None
    package_names: str  # Comma-separated list of package names


class InstallationHistoryResponse(BaseModel):
    """Response model for installation history."""

    installations: List[InstallationHistoryItem]
    total_count: int


class InstallationCompletionRequest(BaseModel):
    """Request from agent when installation completes."""

    request_id: str
    success: bool
    result_log: str
