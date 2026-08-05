# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Provisioning models (Phase 18.1).

Three tables backing the Pro+ ``provisioning_engine`` module (net-new host
provisioning):

  compute_resource
      A configured compute backend (a provider endpoint) — remote libvirt,
      Proxmox, and later cloud/VMware.  Holds the connection URI and a
      ``credential_ref`` (an OpenBAO path); the secret itself is never stored
      in the row.

  provisioning_template
      An operator-authored, versioned provisioning artifact template
      (cloud-init / kickstart / preseed / autoinstall / partition / finish).
      Authoring is the Pro+ surface; the engine renders the final artifact.

  provisioning_job
      A record of a provision request against a compute resource — its state,
      the provider's handle once created, and free-form detail.

These are per-tenant operational data (tenant partition under multi-tenancy;
the single shared DB when MT is off).  The OSS server owns the schema +
migrations + REST wiring so non-Pro+ deployments don't crash on unknown
tables; the Pro+ Cython ``provisioning_engine`` reads/writes them at request
time via the injected ``models`` namespace.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

# Extracted so the FK target string is written once (Sonar S1192), matching
# the convention in repository_mirroring.py.
_HOST_ID_FK = "host.id"
_TEMPLATE_ID_FK = "provisioning_template.id"

# ON DELETE behaviours, named for the same reason.  The distinction is
# deliberate and worth keeping legible: a template going away must NOT delete
# the job or assignment that referenced it (SET NULL — the record stays, it just
# loses its optional template), whereas a child row whose owner is deleted has
# no meaning on its own (CASCADE).
_ON_DELETE_SET_NULL = "SET NULL"
_ON_DELETE_CASCADE = "CASCADE"

# Compute-provider kinds the engine can drive (kept in sync with the engine's
# PROVIDER_REGISTRY).  Stored as a plain string so adding a provider is a
# code-only change, no migration.
COMPUTE_PROVIDER_KINDS = ("libvirt", "proxmox")

# Provisioning template kinds (kept in sync with the engine's TEMPLATE_KINDS).
PROVISIONING_TEMPLATE_KINDS = (
    "cloud_init",
    "kickstart",
    "preseed",
    "autoinstall",
    "partition",
    "finish",
)

# Answer-file dialects a bare-metal install source can be driven by (Phase
# 18.2).  Which one an OS needs is a property of the OS, not of the operator's
# choice — Ubuntu server takes autoinstall, Debian preseed, RHEL kickstart,
# SUSE AutoYaST, and FreeBSD a bsdinstall script.
INSTALL_TEMPLATE_TYPES = (
    "autoinstall",
    "preseed",
    "kickstart",
    "autoyast",
    "bsdinstall",
)

# What a catalog entry is for.  A discovery image is netbooted by an UNKNOWN
# machine to inventory it in RAM; an install source installs an OS to disk.
INSTALL_SOURCE_PURPOSES = ("install", "discovery")

# Lifecycle of a discovered (as-yet unassigned) machine.
#   discovered -- inventoried, sitting in the parking lot awaiting an operator
#   assigned   -- an install assignment exists for its MAC
#   ignored    -- deliberately parked; keeps re-registering without nagging
DISCOVERED_HOST_STATES = ("discovered", "assigned", "ignored")

# Lifecycle of a per-MAC install assignment.
#   assigned   -- pinned, waiting for the machine to netboot
#   building   -- the installer has fetched its answer file
#   installed  -- finished; MUST fall through to local boot from here on
#   failed     -- install reported failure; netboot stays armed for a retry
INSTALL_ASSIGNMENT_STATES = ("assigned", "building", "installed", "failed")


class ComputeResource(Base):
    """A configured compute backend a provider driver connects to."""

    __tablename__ = "compute_resource"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    # Provider kind — one of COMPUTE_PROVIDER_KINDS (validated in the engine).
    kind = Column(String(50), nullable=False, index=True)
    connection_uri = Column(String(500), nullable=False)
    # OpenBAO path to the credential (e.g. an SSH key for qemu+ssh://).  The
    # secret is brokered from OpenBAO at connect time; only the path lives here.
    credential_ref = Column(String(500), nullable=True)
    # Non-secret provider settings (e.g. node_ssh_user, snippet_storage,
    # node_ssh_host for cluster targeting).  NEVER holds credentials — secrets
    # live only in OpenBAO, referenced by credential_ref.
    config = Column(JSON, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return (
            f"<ComputeResource(id={self.id}, name='{self.name}', kind='{self.kind}')>"
        )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "kind": self.kind,
            "connection_uri": self.connection_uri,
            "credential_ref": self.credential_ref,
            "config": self.config or {},
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ProvisioningTemplate(Base):
    """An operator-authored, versioned provisioning artifact template."""

    __tablename__ = "provisioning_template"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    # Template kind — one of PROVISIONING_TEMPLATE_KINDS (validated in engine).
    kind = Column(String(50), nullable=False, index=True)
    body = Column(Text, nullable=False)
    # Free-form parameter defaults/metadata the renderer interpolates.
    params = Column(JSON, nullable=False, default=dict)
    # Bumped on every update so callers can detect drift / pin a version.
    version = Column(Integer, nullable=False, default=1)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return (
            f"<ProvisioningTemplate(id={self.id}, name='{self.name}', "
            f"kind='{self.kind}', v={self.version})>"
        )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "kind": self.kind,
            "body": self.body,
            "params": self.params or {},
            "version": self.version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ProvisioningJob(Base):
    """A provision request against a compute resource + its lifecycle state."""

    __tablename__ = "provisioning_job"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    compute_resource_id = Column(
        GUID(),
        ForeignKey("compute_resource.id", ondelete=_ON_DELETE_CASCADE),
        nullable=False,
        index=True,
    )
    template_id = Column(
        GUID(),
        ForeignKey(_TEMPLATE_ID_FK, ondelete=_ON_DELETE_SET_NULL),
        nullable=True,
    )
    target_name = Column(String(255), nullable=False)
    # pending | creating | running | stopped | error | absent
    state = Column(String(30), nullable=False, default="pending", index=True)
    # The provider's own handle for the created guest (libvirt domain UUID,
    # Proxmox vmid, cloud instance id) — NULL until the provider creates it.
    provider_id = Column(String(255), nullable=True)
    detail = Column(Text, nullable=True, default="")

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return (
            f"<ProvisioningJob(id={self.id}, target='{self.target_name}', "
            f"state='{self.state}')>"
        )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "compute_resource_id": str(self.compute_resource_id),
            "template_id": str(self.template_id) if self.template_id else None,
            "target_name": self.target_name,
            "state": self.state,
            "provider_id": self.provider_id,
            "detail": self.detail,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ProvisioningReadiness(Base):
    """Cached result of the most recent PXE-readiness probe per host (Phase 18.2).

    Same asynchronous shape as ``MirrorSetupStatus``: the UI's "Refresh"
    dispatches a probe plan via ``apply_deployment_plan``; when the agent's
    command_result lands, ``provisioning_result_handlers`` parses the probe
    stdout and upserts this row.  The card polls the GET while
    ``last_check_message_id`` is non-NULL.

    Bare-metal provisioning needs three services on the designated
    provisioning-server host — DHCP, TFTP, and HTTP — and a boot loader to
    hand out.  Readiness gates PXE until they are present.
    """

    __tablename__ = "provisioning_readiness"

    host_id = Column(
        GUID(), ForeignKey(_HOST_ID_FK, ondelete=_ON_DELETE_CASCADE), primary_key=True
    )
    # {tool_name: "present" | "missing"} — commands AND boot-loader files.
    tools = Column(JSON, nullable=False, default=dict)
    # Observed runtime facts the advisor needs, e.g.
    # {"dhcp_port_67": "in_use" | "free", "tftp_port_69": ...}.  A DHCP server
    # already answering on the segment is what makes proxyDHCP the right mode.
    services = Column(JSON, nullable=False, default=dict)
    platform = Column(String(40), nullable=True)
    distro = Column(String(40), nullable=True)
    # Stamped from ``detect_firewall_flavor`` at probe time so the advisor can
    # emit the right port-opening commands without re-deriving it.
    firewall_flavor = Column(String(20), nullable=True)
    # Operator's chosen DHCP mode: "own" (we run DHCP) or "proxy" (we answer
    # PXE only, alongside a corporate DHCP we cannot change).  NULL until set.
    dhcp_mode = Column(String(10), nullable=True)

    last_check_at = Column(DateTime, nullable=True)
    last_check_message_id = Column(String(36), nullable=True)
    last_check_error = Column(Text, nullable=True)

    install_status = Column(String(20), nullable=False, default="idle")
    last_install_at = Column(DateTime, nullable=True)
    last_install_message_id = Column(String(36), nullable=True)
    last_install_error = Column(Text, nullable=True)

    # Config-advisor apply is tracked separately from tool install: installing
    # dnsmasq is harmless, writing a DHCP config and starting it is not.
    apply_status = Column(String(20), nullable=False, default="idle")
    last_apply_at = Column(DateTime, nullable=True)
    last_apply_message_id = Column(String(36), nullable=True)
    last_apply_error = Column(Text, nullable=True)

    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # role -> alternative tool groups; the role is satisfied when EVERY tool in
    # ANY ONE group is present.  dnsmasq deliberately appears under both dhcp
    # and tftp: it serves both, which is why it is the recommended stack and
    # the one the 18.2 S0 spike proved (libvirt's own dnsmasq did DHCP+TFTP).
    REQUIRED_TOOLS_BY_ROLE = {
        "dhcp": (("dnsmasq",), ("dhcpd",), ("kea-dhcp4",)),
        "tftp": (("dnsmasq",), ("in.tftpd",), ("atftpd",)),
        "http": (("nginx",), ("httpd",), ("apache2",)),
        "boot": (("pxelinux.0",), ("undionly.kpxe",), ("ipxe.efi",)),
    }

    PROVISIONING_ROLES = ("dhcp", "tftp", "http", "boot")

    def is_ready_for(self, role: str) -> bool:
        groups = self.REQUIRED_TOOLS_BY_ROLE.get((role or "").lower())
        if not groups:
            return False
        if not isinstance(self.tools, dict):
            return False
        return any(
            all(self.tools.get(tool) == "present" for tool in group) for group in groups
        )

    def is_ready(self) -> bool:
        """Every provisioning role satisfied — the gate PXE gets held behind."""
        return all(self.is_ready_for(r) for r in self.PROVISIONING_ROLES)

    def missing_for(self, role: str) -> list:
        """Tools from the CHEAPEST unsatisfied group — what to offer to install.

        Returns the group needing the fewest additional tools, so a host that
        already has dnsmasq isn't told to install isc-dhcp-server.
        """
        groups = self.REQUIRED_TOOLS_BY_ROLE.get((role or "").lower())
        if not groups or self.is_ready_for(role):
            return []
        tools = self.tools if isinstance(self.tools, dict) else {}
        best = min(
            groups,
            key=lambda g: sum(1 for t in g if tools.get(t) != "present"),
        )
        return [t for t in best if tools.get(t) != "present"]

    def recommended_dhcp_mode(self) -> str:
        """proxyDHCP when something already serves DHCP here, else own-DHCP.

        Running a second authoritative DHCP server on a segment that already
        has one hands out conflicting leases to the whole network, so the
        presence of an existing listener flips the recommendation.
        """
        services = self.services if isinstance(self.services, dict) else {}
        return "proxy" if services.get("dhcp_port_67") == "in_use" else "own"

    def __repr__(self):
        return (
            f"<ProvisioningReadiness(host_id={self.host_id}, "
            f"ready={self.is_ready()})>"
        )

    def to_dict(self) -> dict:
        return {
            "host_id": str(self.host_id),
            "tools": self.tools or {},
            "services": self.services or {},
            "platform": self.platform,
            "distro": self.distro,
            "firewall_flavor": self.firewall_flavor,
            "dhcp_mode": self.dhcp_mode,
            "last_check_at": (
                self.last_check_at.isoformat() if self.last_check_at else None
            ),
            "last_check_message_id": self.last_check_message_id,
            "last_check_error": self.last_check_error,
            "install_status": self.install_status,
            "last_install_at": (
                self.last_install_at.isoformat() if self.last_install_at else None
            ),
            "last_install_message_id": self.last_install_message_id,
            "last_install_error": self.last_install_error,
            "apply_status": self.apply_status,
            "last_apply_at": (
                self.last_apply_at.isoformat() if self.last_apply_at else None
            ),
            "last_apply_message_id": self.last_apply_message_id,
            "last_apply_error": self.last_apply_error,
            "ready": self.is_ready(),
            "roles": {
                role: {
                    "ready": self.is_ready_for(role),
                    "missing": self.missing_for(role),
                }
                for role in self.PROVISIONING_ROLES
            },
            "recommended_dhcp_mode": self.recommended_dhcp_mode(),
        }


class InstallSource(Base):
    """A bootable OS install source in the catalog (Phase 18.2 S3).

    This is what makes "Ubuntu 22.04 on this box, 24.04 on that one, FreeBSD on
    a third" a first-class choice rather than an emergent side effect: you can
    only offer an OS whose install tree you have staged or mirrored, and each
    entry records both what to netboot (kernel/initrd) and which answer-file
    dialect that OS speaks.

    ``mirror_repository_id`` is a SOFT reference (no FK) to the mirror the tree
    came from — provenance only, and deliberately not a constraint so a mirror
    can be retired without invalidating a working catalog entry.
    """

    __tablename__ = "install_source"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    os_family = Column(String(40), nullable=False, index=True)
    version = Column(String(40), nullable=False)
    arch = Column(String(20), nullable=False, default="x86_64", index=True)

    # Netboot artifacts, as paths under the provisioning server's TFTP/HTTP
    # root.  FreeBSD is the shape-breaker — it netboots pxeboot + an mfsroot
    # rather than a Linux kernel+initrd — so initrd_path is nullable.
    kernel_path = Column(String(500), nullable=False)
    initrd_path = Column(String(500), nullable=True)
    # Where the installer pulls packages from (a mirrored repo or air-gap tree).
    install_tree_url = Column(String(1000), nullable=False)
    # Answer-file dialect — one of INSTALL_TEMPLATE_TYPES.
    template_type = Column(String(30), nullable=False)
    # "install" (default) or "discovery" — see INSTALL_SOURCE_PURPOSES.  A
    # discovery image runs entirely in RAM and never touches the disk, so it
    # has no answer file; template_type is ignored for it.
    #
    # Not indexed on purpose: two distinct values over a handful of rows buys
    # nothing, and an index here breaks the SQLite downgrade path (batch table
    # recreation replays reflected indexes over the dropped column).
    purpose = Column(String(20), nullable=False, default="install")
    # Extra kernel command-line appended verbatim at boot.
    boot_args = Column(Text, nullable=True)
    # Provenance only; soft reference, intentionally without a FK.
    mirror_repository_id = Column(GUID(), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return (
            f"<InstallSource(id={self.id}, name='{self.name}', "
            f"os='{self.os_family} {self.version}', arch='{self.arch}')>"
        )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "os_family": self.os_family,
            "version": self.version,
            "arch": self.arch,
            "kernel_path": self.kernel_path,
            "initrd_path": self.initrd_path,
            "install_tree_url": self.install_tree_url,
            "template_type": self.template_type,
            "purpose": self.purpose,
            "boot_args": self.boot_args,
            "mirror_repository_id": (
                str(self.mirror_repository_id) if self.mirror_repository_id else None
            ),
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class HostInstallAssignment(Base):
    """A per-MAC pin: this machine gets this OS (Phase 18.2 S3).

    The per-MAC iPXE endpoint resolves against this table at boot.  MAC is the
    key because a blank machine has no other stable identity — it has no agent,
    no hostname, and no host row until it enrolls.

    ``state`` is load-bearing, not decorative: once a machine reaches
    ``installed`` it must fall through to LOCAL boot.  A netboot-first machine
    that keeps matching an install assignment would reinstall itself on every
    single reboot, wiping the OS it just installed.
    """

    __tablename__ = "host_install_assignment"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    # Normalised lowercase colon-separated form (aa:bb:cc:dd:ee:ff).  Callers
    # go through the engine's normaliser — iPXE, pxelinux and operators each
    # spell MACs differently.
    mac_address = Column(String(17), nullable=False, unique=True, index=True)
    install_source_id = Column(
        GUID(),
        ForeignKey("install_source.id", ondelete=_ON_DELETE_CASCADE),
        nullable=False,
        index=True,
    )
    partition_template_id = Column(
        GUID(),
        ForeignKey(_TEMPLATE_ID_FK, ondelete=_ON_DELETE_SET_NULL),
        nullable=True,
    )
    finish_template_id = Column(
        GUID(),
        ForeignKey(_TEMPLATE_ID_FK, ondelete=_ON_DELETE_SET_NULL),
        nullable=True,
    )
    # What the installed machine should call itself.
    hostname = Column(String(255), nullable=True)
    # Placement for the enrollment token minted at install time — same pair the
    # 18.1 S4 token carries.  Soft references (no FK): site/access-group live in
    # the registry partition under multi-tenancy.
    site_id = Column(GUID(), nullable=True)
    access_group_id = Column(GUID(), nullable=True)
    # One of INSTALL_ASSIGNMENT_STATES.
    state = Column(String(20), nullable=False, default="assigned", index=True)
    # Per-host template parameters the renderer interpolates.
    params = Column(JSON, nullable=False, default=dict)
    # Secret in the answer-file URL.  A netbooting machine cannot authenticate,
    # so the answer file (which carries an enrollment token) is protected by an
    # unguessable per-assignment token with an expiry instead.
    boot_token = Column(String(64), nullable=True, index=True)
    boot_token_expires_at = Column(DateTime, nullable=True)
    last_boot_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def netboot_armed(self) -> bool:
        """Should this machine be served an installer on its next netboot?

        False once installed — see the class docstring; this is the property
        that stops a finished machine from reinstalling itself forever.
        """
        return self.state in ("assigned", "building", "failed")

    def __repr__(self):
        return (
            f"<HostInstallAssignment(mac='{self.mac_address}', "
            f"state='{self.state}')>"
        )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "mac_address": self.mac_address,
            "install_source_id": str(self.install_source_id),
            "partition_template_id": (
                str(self.partition_template_id) if self.partition_template_id else None
            ),
            "finish_template_id": (
                str(self.finish_template_id) if self.finish_template_id else None
            ),
            "hostname": self.hostname,
            "site_id": str(self.site_id) if self.site_id else None,
            "access_group_id": (
                str(self.access_group_id) if self.access_group_id else None
            ),
            "state": self.state,
            "params": self.params or {},
            # The token itself is never serialised — it is a bearer secret for
            # the answer-file URL.  Callers get told whether one exists.
            "has_boot_token": bool(self.boot_token),
            "boot_token_expires_at": (
                self.boot_token_expires_at.isoformat()
                if self.boot_token_expires_at
                else None
            ),
            "netboot_armed": self.netboot_armed(),
            "last_boot_at": (
                self.last_boot_at.isoformat() if self.last_boot_at else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class DiscoveredHost(Base):
    """An unmanaged machine that netbooted the discovery image (Phase 18.2 S5).

    The "discovered hosts" parking lot: a blank machine PXE-boots an ephemeral
    RAM probe that inventories the hardware and registers here WITHOUT touching
    the disk.  An operator (or a policy) then assigns it an OS, which creates
    the per-MAC ``HostInstallAssignment`` the boot service resolves.

    Keyed by MAC for the same reason the assignment is: a machine with no OS,
    no agent and no host row has no other stable identity.  ``facts`` is a free
    -form bag rather than columns because what a probe can see varies by
    hardware, and none of it is queried structurally — it exists for a human
    deciding what to install on this box.
    """

    __tablename__ = "discovered_host"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    # Normalised lowercase colon form, via the engine's normaliser.
    mac_address = Column(String(17), nullable=False, unique=True, index=True)
    # One of DISCOVERED_HOST_STATES.
    state = Column(String(20), nullable=False, default="discovered", index=True)
    # Address the probe reported from — useful for locating the machine, and
    # not authoritative for anything.
    ip_address = Column(String(45), nullable=True)
    hostname = Column(String(255), nullable=True)
    # Summary fields lifted out of ``facts`` purely so the parking-lot list is
    # readable without expanding every row.
    cpu_model = Column(String(255), nullable=True)
    cpu_count = Column(Integer, nullable=True)
    memory_mb = Column(Integer, nullable=True)
    disk_count = Column(Integer, nullable=True)
    primary_disk = Column(String(120), nullable=True)
    manufacturer = Column(String(120), nullable=True)
    product_name = Column(String(255), nullable=True)
    serial_number = Column(String(120), nullable=True)
    # Everything the probe reported, verbatim.
    facts = Column(JSON, nullable=False, default=dict)

    first_seen_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return (
            f"<DiscoveredHost(mac='{self.mac_address}', state='{self.state}', "
            f"product='{self.product_name}')>"
        )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "mac_address": self.mac_address,
            "state": self.state,
            "ip_address": self.ip_address,
            "hostname": self.hostname,
            "cpu_model": self.cpu_model,
            "cpu_count": self.cpu_count,
            "memory_mb": self.memory_mb,
            "disk_count": self.disk_count,
            "primary_disk": self.primary_disk,
            "manufacturer": self.manufacturer,
            "product_name": self.product_name,
            "serial_number": self.serial_number,
            "facts": self.facts or {},
            "first_seen_at": (
                self.first_seen_at.isoformat() if self.first_seen_at else None
            ),
            "last_seen_at": (
                self.last_seen_at.isoformat() if self.last_seen_at else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
