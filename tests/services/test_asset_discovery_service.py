# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Persisting network-discovery reports (Phase 21.6 S1).

The licensed engine decides what each sighting IS and is tested in its own
repo. What is tested here is the part that is ours and fails silently:

  * without the engine NOTHING is stored (an uncorrelated table would show
    every managed host as unmanaged);
  * the fleet lookup finds a managed Windows host whose MAC is stored as
    ``AA-BB-..`` -- a separator must not make a managed host look unmanaged;
  * a hypervisor tap port's guest is fetched, so the engine can attribute it;
  * a second report UPDATES the device and its sighting instead of
    duplicating them, and two agents racing to insert one new device end
    with one row.
"""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.handlers import network_discovery_handlers as handler
from backend.persistence import models
from backend.persistence.db import Base
from backend.services import asset_discovery_service as svc


def _mac(value):
    return value.lower().replace("-", ":") if value else None


class FakeEngine:
    """The engine's contract, minimally: identity = MAC, correlate by MAC or
    by the tap-port suffix, IP only without a MAC."""

    def sanitize_report(self, payload):
        interfaces = [
            {"name": i["name"], "mac": _mac(i.get("mac")), "network": i.get("network")}
            for i in payload.get("interfaces", [])
        ]
        own = {i["mac"] for i in interfaces}
        observations = []
        for raw in payload.get("observations", []):
            mac = _mac(raw.get("mac"))
            if mac in own:
                continue
            ips = [raw["ip"]] if raw.get("ip") else []
            observations.append(
                {
                    "identity": mac or "ip:" + ips[0],
                    "identity_kind": "mac" if mac else "ip",
                    "mac": mac,
                    "mac_locally_administered": False,
                    "ips": ips,
                    "interface": raw.get("interface"),
                    "network": "10.121.1.0/24",
                    "methods": raw.get("methods", ["arp_listen"]),
                    "count": 1,
                    "hostnames": [],
                    "evidence": {"mdns_services": [], "ssdp": []},
                }
            )
        return {
            "interfaces": interfaces,
            "methods": payload.get("methods", {}),
            "window_seconds": 300,
            "observations": observations,
            "dropped": 0,
            "truncated": False,
        }

    def lookup_keys(self, observations):
        macs = sorted({o["mac"] for o in observations if o["mac"]})
        suffixes = sorted({m[2:] for m in macs if m.startswith("fe:")})
        ips = sorted({ip for o in observations if not o["mac"] for ip in o["ips"]})
        return {"macs": macs, "mac_suffixes": suffixes, "ips": ips}

    def build_fleet_index(self, rows):
        macs = {_mac(r["mac_address"]): r["host_id"] for r in rows if r["mac_address"]}
        return {
            "macs": macs,
            "suffixes": {m[2:]: h for m, h in macs.items()},
            "ips": {r["ipv4_address"]: r["host_id"] for r in rows if r["ipv4_address"]},
        }

    def correlate(self, obs, fleet):
        mac = obs["mac"]
        if mac and mac in fleet["macs"]:
            return {"managed_host_id": fleet["macs"][mac], "reason": "mac"}
        if mac and mac.startswith("fe:") and mac[2:] in fleet["suffixes"]:
            return {
                "managed_host_id": fleet["suffixes"][mac[2:]],
                "reason": "hypervisor_port",
            }
        if not mac:
            for ip in obs["ips"]:
                if ip in fleet["ips"]:
                    return {"managed_host_id": fleet["ips"][ip], "reason": "ip"}
        return {"managed_host_id": None, "reason": None}

    def merge_asset(self, existing, obs):
        ips = obs["ips"] + [
            i for i in (existing.get("ips") or []) if i not in obs["ips"]
        ]
        return {
            "mac": obs["mac"],
            "mac_locally_administered": False,
            "last_ip": ips[0] if ips else None,
            "ips": ips,
            "hostnames": [],
            "evidence": obs["evidence"],
            "methods": sorted(set(existing.get("methods") or []) | set(obs["methods"])),
        }


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def licensed():
    with patch.object(svc.shim, "engine", return_value=FakeEngine()), patch.object(
        handler.shim, "engine_available", return_value=True
    ):
        yield


def _host(db, name, mac=None, ip=None):
    host = models.Host(
        id=uuid.uuid4(),
        fqdn=name,
        ipv4=ip,
        active=True,
        status="up",
        approval_status="approved",
    )
    db.add(host)
    db.flush()
    if mac:
        db.add(
            models.NetworkInterface(
                host_id=host.id,
                interface_name="eth0",
                mac_address=mac,
                ipv4_address=ip,
                last_updated=svc._utcnow(),
            )
        )
        db.flush()
    return host


def _report(*observations, own="52:54:00:21:01:0b"):
    return {
        "interfaces": [{"name": "eth0", "mac": own, "network": "10.121.1.0/24"}],
        "methods": {"arp_listen": "ok", "cache": "ok", "sweep": "unavailable:disabled"},
        "observations": list(observations),
    }


def _obs(mac, ip, methods=("arp_listen",)):
    return {"mac": mac, "ip": ip, "interface": "eth0", "methods": list(methods)}


def test_nothing_is_stored_without_the_engine(db):
    observer = _host(db, "a1", "52:54:00:21:01:0b", "10.121.1.11")
    with patch.object(svc.shim, "engine", return_value=None):
        result = svc.record_report(
            db, observer.id, _report(_obs("00:1a:2b:3c:4d:5e", "10.121.1.21"))
        )
    assert result == {"stored": False, "reason": "engine_unavailable"}
    assert db.query(models.DiscoveredAsset).count() == 0
    assert db.query(models.NetworkDiscoveryObserver).count() == 0


def test_devices_sightings_and_blind_spots_are_stored(db, licensed):
    observer = _host(db, "a1", "52:54:00:21:01:0b", "10.121.1.11")
    windows = _host(db, "win", "52-54-00-21-01-0C", "10.121.1.12")
    result = svc.record_report(
        db,
        observer.id,
        _report(
            _obs("52:54:00:21:01:0b", "10.121.1.11"),  # itself: never a discovery
            _obs("52:54:00:21:01:0c", "10.121.1.12"),  # managed WINDOWS host
            _obs("fe:54:00:21:01:0b", None, ["nd_listen"]),  # its own tap port
            _obs("00:1a:2b:3c:4d:5e", "10.121.1.21"),  # the printer
        ),
    )
    assert result["stored"] and result["devices"] == 3 and result["managed"] == 2
    by_id = {a.identity: a for a in db.query(models.DiscoveredAsset)}
    assert by_id["52:54:00:21:01:0c"].managed_host_id == windows.id
    assert by_id["52:54:00:21:01:0c"].managed_reason == "mac"
    assert by_id["fe:54:00:21:01:0b"].managed_host_id == observer.id
    assert by_id["fe:54:00:21:01:0b"].managed_reason == "hypervisor_port"
    printer = by_id["00:1a:2b:3c:4d:5e"]
    assert printer.managed_host_id is None and printer.last_ip == "10.121.1.21"
    sighting = (
        db.query(models.DiscoveredAssetSighting).filter_by(asset_id=printer.id).one()
    )
    assert sighting.observer_host_id == observer.id
    assert sighting.network == "10.121.1.0/24" and sighting.sightings == 1
    watcher = db.query(models.NetworkDiscoveryObserver).one()
    assert watcher.methods["sweep"] == "unavailable:disabled"
    assert watcher.networks == [{"interface": "eth0", "network": "10.121.1.0/24"}]


def test_a_second_report_updates_instead_of_duplicating(db, licensed):
    observer = _host(db, "a1", "52:54:00:21:01:0b", "10.121.1.11")
    svc.record_report(
        db, observer.id, _report(_obs("00:1a:2b:3c:4d:5e", "10.121.1.22"))
    )
    first_seen = db.query(models.DiscoveredAsset).one().first_seen_at
    # Renumbered by DHCP; seen this time from the neighbor cache.
    svc.record_report(
        db, observer.id, _report(_obs("00:1a:2b:3c:4d:5e", "10.121.1.23", ["cache"]))
    )
    asset = db.query(models.DiscoveredAsset).one()
    assert asset.last_ip == "10.121.1.23" and asset.ips == [
        "10.121.1.23",
        "10.121.1.22",
    ]
    assert asset.first_seen_at == first_seen
    assert asset.methods == ["arp_listen", "cache"]
    sighting = db.query(models.DiscoveredAssetSighting).one()
    assert sighting.sightings == 2 and sighting.methods == ["arp_listen", "cache"]
    assert db.query(models.NetworkDiscoveryObserver).one().reports == 2


def test_a_device_stops_being_managed_when_its_host_is_gone(db, licensed):
    observer = _host(db, "a1", "52:54:00:21:01:0b", "10.121.1.11")
    retired = _host(db, "old", "00:1a:2b:3c:4d:5e", "10.121.1.30")
    svc.record_report(
        db, observer.id, _report(_obs("00:1a:2b:3c:4d:5e", "10.121.1.30"))
    )
    assert db.query(models.DiscoveredAsset).one().managed_host_id == retired.id
    db.query(models.NetworkInterface).filter_by(host_id=retired.id).delete()
    svc.record_report(
        db, observer.id, _report(_obs("00:1a:2b:3c:4d:5e", "10.121.1.30"))
    )
    asset = db.query(models.DiscoveredAsset).one()
    assert asset.managed_host_id is None and asset.managed_reason is None


def test_two_agents_racing_on_one_new_device_end_with_one_row(db, licensed):
    observer = _host(db, "a1", "52:54:00:21:01:0b", "10.121.1.11")
    # Another agent's report inserted the device after we looked for it.
    db.add(
        models.DiscoveredAsset(
            identity="00:1a:2b:3c:4d:5e",
            identity_kind="mac",
            mac_locally_administered=False,
        )
    )
    db.flush()
    with patch.object(svc, "_existing_assets", return_value={}):
        result = svc.record_report(
            db, observer.id, _report(_obs("00:1a:2b:3c:4d:5e", "10.121.1.21"))
        )
    assert result["stored"]
    assert db.query(models.DiscoveredAsset).count() == 1
    assert db.query(models.DiscoveredAssetSighting).count() == 1


class TestHandler:
    def _run(self, db, connection, message):
        return asyncio.run(
            handler.handle_network_discovery_report(db, connection, message)
        )

    def test_an_unregistered_connection_is_refused(self, db):
        reply = self._run(db, SimpleNamespace(host_id=None), {"data": {}})
        assert reply["error_type"] == "host_not_registered"

    def test_unlicensed_is_acknowledged_and_ignored(self, db):
        observer = _host(db, "a1", "52:54:00:21:01:0b", "10.121.1.11")
        with patch.object(handler.shim, "engine_available", return_value=False):
            reply = self._run(
                db, SimpleNamespace(host_id=str(observer.id)), {"data": _report()}
            )
        assert reply == handler.ACK
        assert db.query(models.NetworkDiscoveryObserver).count() == 0

    def test_a_report_is_stored_and_committed(self, db, licensed):
        observer = _host(db, "a1", "52:54:00:21:01:0b", "10.121.1.11")
        db.commit()
        message = {"data": _report(_obs("00:1a:2b:3c:4d:5e", "10.121.1.21"))}
        assert (
            self._run(db, SimpleNamespace(host_id=str(observer.id)), message)
            == handler.ACK
        )
        db.rollback()  # proves the handler committed
        assert db.query(models.DiscoveredAsset).count() == 1

    def test_a_failure_is_rolled_back_and_still_acknowledged(self, db, licensed):
        observer = _host(db, "a1", "52:54:00:21:01:0b", "10.121.1.11")
        with patch.object(svc, "record_report", side_effect=RuntimeError("boom")):
            reply = self._run(
                db, SimpleNamespace(host_id=str(observer.id)), {"data": _report()}
            )
        assert reply == handler.ACK
