# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
The PHYSICAL (or virtual) machine a host runs on -- Phase 23.2.

A host is one operating system; a machine is the hardware under it.  A laptop
that multi-boots Windows, Ubuntu and OpenBSD is three hosts on one machine, and
an OS reinstall is a new host on the same machine.  The asset tag belongs here,
so it survives both.

Hosts are grouped by ``match_key``, the agent's byte-order-insensitive form of
the SMBIOS system UUID (an OS that prints the UUID swapped still lands on the
same machine).  The key is NOT unique: a cloned VM that kept its UUID is a
second machine with the same key once an admin says so.  The identity groups
hosts; it never authenticates one (Phase 22.0) -- a VM can be given any UUID.
"""

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    false,
)

from backend.persistence.db import Base
from backend.persistence.models.core import GUID


class Machine(Base):
    """One machine; ``host.machine_id`` points here (a soft reference)."""

    __tablename__ = "machine"
    __table_args__ = (UniqueConstraint("asset_tag", name="uq_machine_asset_tag"),)

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    # The byte-order-insensitive identity key, as the agent computes it.
    match_key = Column(String(36), nullable=False, index=True)
    # The identity in SMBIOS 2.6 order, and the corroborating serials.
    system_uuid = Column(String(36), nullable=True)
    system_serial = Column(String(255), nullable=True)
    board_serial = Column(String(255), nullable=True)
    vendor = Column(String(255), nullable=True)
    model = Column(String(255), nullable=True)
    # A hypervisor's virtual hardware (QEMU, VMware, Hyper-V, ...): a second
    # host on it is usually a clone, so it is confirmed by an admin rather than
    # linked automatically.
    is_virtual = Column(Boolean, nullable=False, default=False, server_default=false())
    # The asset tag lives on the machine, not the host.  Unique when set
    # (several NULLs are allowed on both SQLite and PostgreSQL).
    asset_tag = Column(String(128), nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


# The one row of ``asset_tag_scheme`` (per tenant database).
ASSET_TAG_SCHEME_ID = uuid.UUID("00000000-0000-0000-0000-000000000023")


class AssetTagScheme(Base):
    """The tenant's asset-tag naming scheme (Phase 23.2 S3): a single row,
    edited in Settings.  See ``services/asset_tag_scheme.py``."""

    __tablename__ = "asset_tag_scheme"

    id = Column(GUID(), primary_key=True, default=lambda: ASSET_TAG_SCHEME_ID)
    # "builder" (prefix / separator / digits / suffix) or "regex".
    mode = Column(String(16), nullable=False, default="builder")
    prefix = Column(String(32), nullable=False, default="")
    separator = Column(String(1), nullable=False, default="-")
    digits = Column(Integer, nullable=False, default=6)
    suffix = Column(String(32), nullable=False, default="")
    pattern = Column(String(256), nullable=False, default="")
    # Reject non-conforming tags at entry (False: accept, and report them).
    enforce = Column(Boolean, nullable=False, default=False, server_default=false())
    updated_at = Column(DateTime, nullable=True)
    updated_by = Column(String(255), nullable=True)


# How a held tag finds its machine.
HELD_BY_UUID = "system_uuid"
HELD_BY_SERIAL = "system_serial"


class HeldAssetTag(Base):
    """A tag waiting for a machine that has not reported in yet (Phase 23.2
    S5): a CSV row whose UUID or serial matched no machine, or a tag given to
    a box 18.2's bare-metal discovery saw before it had an OS.  Applied -- and
    deleted -- when a machine with that identity first appears untagged."""

    __tablename__ = "held_asset_tag"
    __table_args__ = (
        UniqueConstraint("kind", "identifier", name="uq_held_asset_tag_identity"),
        UniqueConstraint("asset_tag", name="uq_held_asset_tag_tag"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    # HELD_BY_UUID (identifier = the byte-order-insensitive match key) or
    # HELD_BY_SERIAL (identifier = the system serial as printed).
    kind = Column(String(16), nullable=False)
    identifier = Column(String(255), nullable=False, index=True)
    asset_tag = Column(String(128), nullable=False)
    created_at = Column(DateTime, nullable=False)
    created_by = Column(String(255), nullable=True)
