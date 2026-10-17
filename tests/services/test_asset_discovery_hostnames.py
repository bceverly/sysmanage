# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Device hostnames in Network Discovery (ROADMAP, 2026-10-17).

The engine judges (trust order, merge, matching by name); what is ours and
fails silently:

  * the names the agent sent reach the row, and the API shows the display
    name and every name WITH its source -- including rows stored before,
    which hold plain strings;
  * a device matched to a host by NAME (no MAC seen) stays matched when that
    host re-reports its hardware;
  * the search box finds a device by its name;
  * reverse DNS is ACTIVE: agents are told they may do it only while the
    sweep opt-in is on, and are told again when it changes.
"""

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence import models
from backend.persistence.db import Base
from backend.services import asset_discovery_review as review
from backend.services import asset_discovery_service as svc
from backend.services import network_discovery_policy as policy
from tests.services.test_asset_discovery_service import FakeEngine
from tests.services.test_network_discovery_policy import _host, sent  # noqa: F401

NAMES = [
    {"name": "brother-hl", "source": "dhcp", "seen_at": "2026-10-17T10:00:00Z"},
    {"name": "brother-hl.local", "source": "mdns", "seen_at": "2026-10-17T10:01:00Z"},
]


class NamingEngine(FakeEngine):
    """FakeEngine that keeps names, and matches a MAC-less device by name."""

    @staticmethod
    def normalize_mac(value):
        return value.lower().replace("-", ":") if value else None

    @staticmethod
    def identity_ip(value):
        return value or None

    def sanitize_report(self, payload):
        clean = super().sanitize_report(payload)
        for obs, raw in zip(clean["observations"], payload["observations"]):
            obs["hostnames"] = list(raw.get("hostnames") or [])
        return clean

    def lookup_keys(self, observations):
        keys = super().lookup_keys(observations)
        keys["names"] = sorted(
            {
                (h["name"] if isinstance(h, dict) else h).split(".")[0].lower()
                for o in observations
                if not o["mac"]
                for h in o.get("hostnames") or []
            }
        )
        return keys

    def build_fleet_index(self, rows):
        fleet = super().build_fleet_index([r for r in rows if "fqdn" not in r])
        fleet["names"] = {
            r["fqdn"].split(".")[0].lower(): r["host_id"] for r in rows if "fqdn" in r
        }
        return fleet

    def correlate(self, obs, fleet):
        verdict = super().correlate(obs, fleet)
        if verdict["managed_host_id"] or obs["mac"]:
            return verdict
        for item in obs.get("hostnames") or []:
            text = item["name"] if isinstance(item, dict) else item
            host_id = fleet.get("names", {}).get(text.split(".")[0].lower())
            if host_id:
                return {"managed_host_id": host_id, "reason": "hostname"}
        return verdict

    def merge_asset(self, existing, obs):
        merged = super().merge_asset(existing, obs)
        merged["hostnames"] = obs["hostnames"] or existing.get("hostnames") or []
        return merged


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def naming():
    with patch.object(svc.shim, "engine", return_value=NamingEngine()):
        yield


def _report(*observations):
    return {
        "interfaces": [{"name": "eth0", "mac": "52:54:00:21:01:0b"}],
        "methods": {"arp_listen": "ok", "dhcp": "ok"},
        "observations": list(observations),
    }


def test_names_pass_through_to_the_api_with_their_source(db, naming):
    observer = _host(db, "a1", mac="52:54:00:21:01:0b", ip="10.121.1.11")
    svc.record_report(db, observer.id, _report(
        {"mac": "00:1a:2b:3c:4d:5e", "ip": "10.121.1.21", "interface": "eth0",
         "methods": ["dhcp"], "hostnames": NAMES},
    ))  # fmt: skip
    device = review.list_devices(db, status="unmanaged")["devices"][0]
    assert device["display_name"] == "brother-hl"
    assert device["hostnames"] == NAMES


def test_rows_stored_before_hold_plain_strings(db):
    asset = models.DiscoveredAsset(
        identity="00:1a:2b:3c:4d:5e", identity_kind="mac", hostnames=["old.local", 7]
    )
    db.add(asset)
    db.flush()
    out = asset.to_dict()
    assert out["display_name"] == "old.local"
    assert out["hostnames"] == [
        {"name": "old.local", "source": "unknown", "seen_at": None}
    ]
    asset.hostnames = None
    assert (
        asset.to_dict()["display_name"] is None and asset.to_dict()["hostnames"] == []
    )


def test_search_finds_a_device_by_name(db, naming):
    observer = _host(db, "a1", mac="52:54:00:21:01:0b", ip="10.121.1.11")
    svc.record_report(db, observer.id, _report(
        {"mac": "00:1a:2b:3c:4d:5e", "ip": "10.121.1.21", "interface": "eth0",
         "methods": ["dhcp"], "hostnames": NAMES},
        {"mac": "00:1a:2b:3c:4d:5f", "ip": "10.121.1.22", "interface": "eth0"},
    ))  # fmt: skip
    found = review.list_devices(db, status="unmanaged", search="Brother")
    assert [d["identity"] for d in found["devices"]] == ["00:1a:2b:3c:4d:5e"]


def test_a_mac_less_device_matches_its_host_by_name_and_stays_matched(db, naming):
    observer = _host(db, "a1", mac="52:54:00:21:01:0b", ip="10.121.1.11")
    t14 = _host(db, "gdr-t14.example.com")
    svc.record_report(db, observer.id, _report(
        {"ip": "192.168.4.132", "interface": "eth0", "methods": ["mdns"],
         "hostnames": [{"name": "gdr-t14.local", "source": "mdns", "seen_at": None}]},
    ))  # fmt: skip
    asset = db.query(models.DiscoveredAsset).one()
    assert (asset.managed_host_id, asset.managed_reason) == (t14.id, "hostname")
    # The host re-reports its hardware: the name match must survive.
    svc.recorrelate_host(db, t14.id)
    assert (asset.managed_host_id, asset.managed_reason) == (t14.id, "hostname")


def test_the_host_name_lookup_is_by_short_name(db):
    t14 = _host(db, "GDR-T14.example.com")
    _host(db, "gdr-t140.example.com")
    rows = svc._hosts_named(db, ["gdr-t14"])
    assert rows == [{"host_id": str(t14.id), "fqdn": "GDR-T14.example.com"}]


class TestNameLookupsFollowTheSweepOptIn:
    def _told(self, sent):  # noqa: F811
        return [c["message_data"]["data"]["parameters"]["name_lookups"] for c in sent]

    def test_off_unless_sweeps_are_allowed_and_resent_when_that_changes(
        self, db, sent  # noqa: F811
    ):
        _host(db, "a1")
        policy.set_policy(db, True, 300, "a@b")
        policy.reconcile(db)
        policy.set_policy(db, True, 300, "a@b", sweep_enabled=True)
        policy.reconcile(db)
        policy.reconcile(db)  # nothing changed: nothing sent
        policy.set_policy(db, True, 300, "a@b", sweep_enabled=False)
        policy.reconcile(db)
        assert self._told(sent) == [False, True, False]
