# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Pydantic models for child host API endpoints.
"""

from typing import List, Optional

from pydantic import BaseModel


class CreateChildHostRequest(BaseModel):
    """Request model for creating a child host."""

    child_type: str  # 'wsl', 'lxd', 'virtualbox', etc.
    distribution_id: str  # UUID of the distribution to install
    hostname: str  # Hostname for the new child host
    username: str  # Non-root user to create
    password: str  # Password for the user
    install_path: Optional[str] = None  # Optional custom install location
    auto_approve: bool = False  # Automatically approve the child host when it registers


class CreateWslChildHostRequest(BaseModel):
    """Request body for creating a WSL, LXD, VMM, or KVM child host."""

    child_type: str = "wsl"
    distribution: str
    hostname: str
    username: str
    password: str
    root_password: Optional[str] = None  # For VMM: separate root password
    container_name: Optional[str] = None  # For LXD containers
    vm_name: Optional[str] = None  # For VMM/KVM virtual machines
    iso_url: Optional[str] = None  # For VMM: URL to download install ISO
    auto_approve: bool = False  # Automatically approve the child host when it registers
    # KVM-specific fields
    memory: Optional[str] = "2G"  # Memory allocation (e.g., "2G", "4096M")
    disk_size: Optional[str] = "20G"  # Disk size (e.g., "20G", "50G")
    cpus: Optional[int] = 2  # Number of vCPUs
    # Windows Server child hosts (Phase 12.5).  Only read when the selected
    # distribution is a Windows one; ignored entirely for Linux/BSD guests.
    #
    # NOTE these carry PLAINTEXT secrets, unlike ``password`` which is hashed
    # before it leaves here.  That is forced by the platform, not a shortcut:
    # Autounattend consumes Microsoft's base64 obfuscation of the plaintext (or
    # the plaintext itself), and a product key must be the literal key.  They
    # are never persisted in the child_host row — the key goes to OpenBAO and
    # the passwords are transient (see child_host_virtualization).
    windows_edition: Optional[str] = "standard-core"
    windows_admin_password: Optional[str] = None
    windows_product_key: Optional[str] = None
    windows_timezone: Optional[str] = "UTC"
    windows_locale: Optional[str] = "en-US"
    windows_iso_path: Optional[str] = None
    # Static networking is opt-in; empty means DHCP.
    windows_static_ip: Optional[str] = None
    windows_gateway: Optional[str] = None
    windows_dns_servers: Optional[str] = None
    # Domain join is opt-in; empty domain means a workgroup machine.
    windows_join_domain: Optional[str] = None
    windows_domain_ou: Optional[str] = None
    windows_domain_user: Optional[str] = None
    windows_domain_password: Optional[str] = None


class EnableWslRequest(BaseModel):
    """Request body for enabling WSL."""

    # No parameters needed for now - placeholder for future options


class ChildHostResponse(BaseModel):
    """Response model for child host data."""

    id: str
    parent_host_id: str
    child_host_id: Optional[str] = None
    child_name: str
    child_type: str
    distribution: Optional[str] = None
    distribution_version: Optional[str] = None
    hostname: Optional[str] = None
    status: str
    installation_step: Optional[str] = None
    # Progress telemetry (Phase 12.5).  step_at is what lets the UI say
    # "nothing for 12 minutes" instead of spinning indefinitely.
    installation_step_number: Optional[int] = None
    installation_total_steps: Optional[int] = None
    installation_step_at: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str
    installed_at: Optional[str] = None
    reboot_required: bool = False
    agent_version: Optional[str] = None

    class Config:
        from_attributes = True


class DistributionResponse(BaseModel):
    """Response model for distribution data."""

    id: str
    child_type: str
    distribution_name: str
    distribution_version: str
    display_name: str
    is_active: bool

    class Config:
        from_attributes = True


class DistributionDetailResponse(BaseModel):
    """Detailed response model for distribution data (admin view)."""

    id: str
    child_type: str
    distribution_name: str
    distribution_version: str
    display_name: str
    install_identifier: Optional[str] = None
    executable_name: Optional[str] = None
    agent_install_method: Optional[str] = None
    agent_install_commands: Optional[str] = None
    is_active: bool
    min_agent_version: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class CreateDistributionRequest(BaseModel):
    """Request model for creating a distribution."""

    child_type: str
    distribution_name: str
    distribution_version: str
    display_name: str
    install_identifier: Optional[str] = None
    executable_name: Optional[str] = None
    agent_install_method: Optional[str] = None
    agent_install_commands: Optional[str] = None
    is_active: bool = True
    min_agent_version: Optional[str] = None
    notes: Optional[str] = None


class UpdateDistributionRequest(BaseModel):
    """Request model for updating a distribution."""

    child_type: Optional[str] = None
    distribution_name: Optional[str] = None
    distribution_version: Optional[str] = None
    display_name: Optional[str] = None
    install_identifier: Optional[str] = None
    executable_name: Optional[str] = None
    agent_install_method: Optional[str] = None
    agent_install_commands: Optional[str] = None
    is_active: Optional[bool] = None
    min_agent_version: Optional[str] = None
    notes: Optional[str] = None


class VirtualizationSupportResponse(BaseModel):
    """Response model for virtualization support info."""

    supported_types: List[str]  # ['wsl', 'lxd', etc.]
    wsl_enabled: Optional[bool] = None
    wsl_version: Optional[int] = None
    requires_reboot: bool = False


class ConfigureKvmNetworkingRequest(BaseModel):
    """Request model for configuring KVM networking."""

    mode: str = "nat"  # 'nat' (default) or 'bridged'
    network_name: Optional[str] = (
        None  # Name for the network (default: 'default' for NAT)
    )
    bridge: Optional[str] = (
        None  # Linux bridge interface name (required for bridged mode)
    )
