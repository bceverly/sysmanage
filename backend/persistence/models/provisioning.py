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
        ForeignKey("compute_resource.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    template_id = Column(
        GUID(),
        ForeignKey("provisioning_template.id", ondelete="SET NULL"),
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
