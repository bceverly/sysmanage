# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Unenrolled asset discovery (ROADMAP 21.6 S1).

Agents report the devices they can see on their own network segments; the
server keeps one row per DEVICE and matches it against the managed fleet, so
the review page (21.6 S3) can show what is on the network that SysManage does
not manage.

NOT THE SAME AS ``DiscoveredHost``
----------------------------------
``provisioning.DiscoveredHost`` (Phase 18.2) is a machine that network-BOOTED
into the provisioning subnet and is waiting to be installed. A
``DiscoveredAsset`` is anything answering on a segment an agent sits on --
printers, phones, switches, other people's servers -- and nothing is ever
installed on it. Different lifecycle, different table.

IDENTITY IS THE MAC (21.6 S0, measured)
---------------------------------------
Renumbering a device through DHCP kept its MAC; an IP-keyed exclusion lost it
while a MAC-keyed one held. So ``identity`` is the normalized MAC whenever
one was observed, and ``ip:<address>`` only when none was -- a deliberate,
labeled fallback. ``mac_locally_administered`` marks a locally administered MAC (19% of
the devices on a real home LAN): those can ROTATE, so their "new device"
semantics must be stated, not assumed stable.

All three tables are tenant data (tenant alembic chain), like ``host``.
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
    UniqueConstraint,
    false,
)

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

IDENTITY_MAC = "mac"
IDENTITY_IP = "ip"
HOST_ID = "host.id"  # the column every observation points at


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DiscoveredAsset(Base):
    """One device seen on a segment, managed or not."""

    __tablename__ = "discovered_asset"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    # "aa:bb:cc:dd:ee:ff", or "ip:<address>" when no MAC was ever observed.
    identity = Column(String(64), nullable=False, unique=True, index=True)
    identity_kind = Column(String(8), nullable=False)
    mac = Column(String(17), nullable=True, index=True)
    mac_locally_administered = Column(Boolean, nullable=False, default=False)
    last_ip = Column(String(45), nullable=True)
    ips = Column(JSON, nullable=True)  # most recent first, bounded
    hostnames = Column(JSON, nullable=True)  # mDNS names, bounded
    # {"mdns_services": [...], "ssdp": [...]} -- what the device says it is.
    evidence = Column(JSON, nullable=True)
    methods = Column(JSON, nullable=True)  # every method that has seen it
    # S5: the IEEE-registered maker of the MAC (never for a locally
    # administered one), and the engine's LABELED guess at what the device is:
    # {"confidence": high|low|none, "reasons": [...]}.
    vendor = Column(String(128), nullable=True)
    device_type = Column(String(32), nullable=True)
    classification = Column(JSON, nullable=True)
    # Set when the device IS a managed host (or its hypervisor port). The
    # FK nulls itself when that host is deleted, which is exactly right: a
    # decommissioned host still on the network is an unmanaged device again.
    managed_host_id = Column(
        GUID(), ForeignKey(HOST_ID, ondelete="SET NULL"), nullable=True, index=True
    )
    managed_reason = Column(String(32), nullable=True)
    correlated_at = Column(DateTime, nullable=True)
    first_seen_at = Column(DateTime, nullable=False, default=_utcnow)
    last_seen_at = Column(DateTime, nullable=False, default=_utcnow, index=True)

    def to_dict(self):
        return {
            "id": str(self.id),
            "identity": self.identity,
            "identity_kind": self.identity_kind,
            "mac": self.mac,
            "mac_locally_administered": bool(self.mac_locally_administered),
            "last_ip": self.last_ip,
            "ips": self.ips or [],
            "hostnames": self.hostnames or [],
            "evidence": self.evidence or {},
            "methods": self.methods or [],
            "vendor": self.vendor,
            "device_type": self.device_type,
            "classification": self.classification or {},
            "managed_host_id": (
                str(self.managed_host_id) if self.managed_host_id else None
            ),
            "managed_reason": self.managed_reason,
            "first_seen_at": _iso(self.first_seen_at),
            "last_seen_at": _iso(self.last_seen_at),
        }


class DiscoveredAssetSighting(Base):
    """Which agent saw a device, on which network, by which methods."""

    __tablename__ = "discovered_asset_sighting"
    __table_args__ = (
        UniqueConstraint(
            "asset_id", "observer_host_id", name="uq_discovered_asset_sighting"
        ),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    asset_id = Column(
        GUID(),
        ForeignKey("discovered_asset.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    observer_host_id = Column(
        GUID(), ForeignKey(HOST_ID, ondelete="CASCADE"), nullable=False, index=True
    )
    interface = Column(String(64), nullable=True)
    network = Column(String(64), nullable=True)  # the observer's on-link CIDR
    ip = Column(String(45), nullable=True)
    methods = Column(JSON, nullable=True)
    sightings = Column(Integer, nullable=False, default=0)
    first_seen_at = Column(DateTime, nullable=False, default=_utcnow)
    last_seen_at = Column(DateTime, nullable=False, default=_utcnow)


class NetworkDiscoveryObserver(Base):
    """What one agent can and cannot see -- the blind spots, per host.

    A passive-only agent cannot find a silent device, and a Windows agent
    cannot listen for ARP at all (21.6 S0). The review page states those
    limits from here instead of implying its list is complete.
    """

    __tablename__ = "network_discovery_observer"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(
        GUID(),
        ForeignKey(HOST_ID, ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    networks = Column(JSON, nullable=True)  # [{"interface", "network"}]
    # {"arp_listen": "ok" | "unavailable:<reason>", "cache": ..., ...}
    methods = Column(JSON, nullable=True)
    window_seconds = Column(Integer, nullable=True)
    reports = Column(Integer, nullable=False, default=0)
    last_report_at = Column(DateTime, nullable=False, default=_utcnow)


def _iso(value):
    return value.isoformat() if value else None


DEFAULT_REPORT_INTERVAL_SECONDS = 300
DEFAULT_RETENTION_DAYS = 30
RETENTION_CHOICES = (7, 30, 90, 365)
MIN_REPORT_INTERVAL_SECONDS = 60
MAX_REPORT_INTERVAL_SECONDS = 3600


class NetworkDiscoveryPolicy(Base):
    """Whether this tenant's agents listen, and how often they report (S2).

    One row per tenant database; absent means OFF. Listening to a network is
    an operator decision, so it defaults to off and every change is audited.
    """

    __tablename__ = "network_discovery_policy"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    enabled = Column(Boolean, nullable=False, default=False)
    report_interval_seconds = Column(
        Integer, nullable=False, default=DEFAULT_REPORT_INTERVAL_SECONDS
    )
    # S4: may operators run ACTIVE sweeps at all? A second, separate opt-in:
    # listening is quiet, a sweep puts traffic on the network.
    sweep_enabled = Column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    # S5: a device unseen this long is forgotten (its exclusion, keyed by
    # identity, is kept). Without it a device from a network that no longer
    # exists stays "unmanaged" forever -- found live 2026-09-29.
    retention_days = Column(
        Integer,
        nullable=False,
        default=DEFAULT_RETENTION_DAYS,
        server_default=str(DEFAULT_RETENTION_DAYS),
    )
    updated_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime, nullable=False, default=_utcnow)


class NetworkDiscoveryDispatch(Base):
    """What each host was last TOLD, so the reconciler only sends a change.

    Re-sent when the agent re-advertises its capabilities after this was sent
    (a restart or reinstall may have lost its saved setting) -- the command is
    idempotent on the agent, so a spare resend costs nothing.
    """

    __tablename__ = "network_discovery_dispatch"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(
        GUID(),
        ForeignKey(HOST_ID, ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    enabled = Column(Boolean, nullable=False)
    report_interval_seconds = Column(Integer, nullable=False)
    command_id = Column(String(36), nullable=True)
    sent_at = Column(DateTime, nullable=False, default=_utcnow)


# Why an operator says a device is fine. A closed set so the review page can
# group and filter by it; the free-text ``reason`` carries the specifics.
EXCLUSION_CATEGORIES = (
    "printer",
    "iot",
    "network_equipment",
    "appliance",
    "personal_device",
    "virtual_machine",
    "virtual_address",  # S5: a VIP / load-balancer / virtual-router address
    "other",
)


class DiscoveredAssetExclusion(Base):
    """ "This device is known and fine -- never show it as unmanaged again" (S3).

    An AUDIT ROW, not UI state: who decided, when, why, and -- if it was
    withdrawn -- who withdrew it. Keyed by the device's ``identity`` (its MAC),
    not by an asset row or an IP, so it survives DHCP renumbering (21.6 S0
    proved an IP-keyed exclusion rots) and even the asset row being purged and
    re-discovered. Revoked rows are kept; at most one is active per identity.
    """

    __tablename__ = "discovered_asset_exclusion"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    identity = Column(String(64), nullable=False, index=True)
    category = Column(String(32), nullable=False)
    reason = Column(String(1000), nullable=False)
    created_by = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    revoked_by = Column(String(255), nullable=True)
    revoked_at = Column(DateTime, nullable=True, index=True)
    revoke_reason = Column(String(1000), nullable=True)

    def to_dict(self):
        return {
            "id": str(self.id),
            "identity": self.identity,
            "category": self.category,
            "reason": self.reason,
            "created_by": self.created_by,
            "created_at": _iso(self.created_at),
            "revoked_by": self.revoked_by,
            "revoked_at": _iso(self.revoked_at),
            "revoke_reason": self.revoke_reason,
        }


SWEEP_QUEUED = "queued"
SWEEP_COMPLETED = "completed"
SWEEP_REFUSED = "refused"
SWEEP_FAILED = "failed"
SWEEP_TIMED_OUT = "timed_out"


class NetworkSweepRun(Base):
    """One operator-requested active sweep (S4) -- the audit of what was probed.

    The range, the rate, who asked, which agent ran it and what came back.
    Kept for every run, refused and failed ones included: "who put traffic on
    this network, and when" must stay answerable.
    """

    __tablename__ = "network_sweep_run"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    cidr = Column(String(64), nullable=False, index=True)
    rate = Column(Integer, nullable=False)
    addresses = Column(Integer, nullable=False)
    status = Column(String(16), nullable=False, default=SWEEP_QUEUED, index=True)
    reason = Column(String(32), nullable=True)
    requested_by = Column(String(255), nullable=False)
    requested_at = Column(DateTime, nullable=False, default=_utcnow)
    agent_host_id = Column(
        GUID(), ForeignKey(HOST_ID, ondelete="SET NULL"), nullable=True, index=True
    )
    command_id = Column(String(36), nullable=True)
    finished_at = Column(DateTime, nullable=True)
    probed = Column(Integer, nullable=True)
    devices_found = Column(Integer, nullable=True)

    def to_dict(self):
        return {
            "id": str(self.id),
            "cidr": self.cidr,
            "rate": self.rate,
            "addresses": self.addresses,
            "status": self.status,
            "reason": self.reason,
            "requested_by": self.requested_by,
            "requested_at": _iso(self.requested_at),
            "agent_host_id": str(self.agent_host_id) if self.agent_host_id else None,
            "finished_at": _iso(self.finished_at),
            "probed": self.probed,
            "devices_found": self.devices_found,
        }
