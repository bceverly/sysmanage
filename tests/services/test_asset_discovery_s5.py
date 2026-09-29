# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Vendor, classification, retention and static addresses (Phase 21.6 S5).

What fails silently if got wrong:

  * a vendor must come from the table the server SHIPS -- never a network
    lookup -- and a locally administered MAC has no vendor at all;
  * a device must not stay "unmanaged" forever once its network is gone, but
    forgetting it must not forget the operator's exclusion of it;
  * a static address (VIP, load balancer) registered by IP covers whatever
    holds that address -- and still never hides a MANAGED host.
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api import asset_discovery as api
from backend.persistence import models
from backend.persistence.db import Base
from backend.services import asset_discovery_review as review
from backend.services import asset_discovery_service as svc
from backend.services import network_discovery_policy as policy
from backend.services import oui
from tests.services.test_asset_discovery_service import FakeEngine


class ClassifyingEngine(FakeEngine):
    @staticmethod
    def classify(device):
        if "_ipp._tcp" in (device.get("evidence") or {}).get("mdns_services", []):
            return {
                "device_type": "printer",
                "confidence": "high",
                "reasons": ["mdns:_ipp"],
            }
        return {"device_type": "unknown", "confidence": "none", "reasons": []}


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


def _host(db, name):
    host = models.Host(
        id=uuid.uuid4(), fqdn=name, active=True, status="up", approval_status="approved"
    )
    db.add(host)
    db.flush()
    return host


def _device(db, mac, ip, managed_by=None, seen=None):
    asset = models.DiscoveredAsset(
        identity=mac, identity_kind="mac", mac=mac, mac_locally_administered=False,
        last_ip=ip, ips=[ip], managed_host_id=managed_by,
        managed_reason="mac" if managed_by else None,
        last_seen_at=seen or datetime.utcnow(),
    )  # fmt: skip
    db.add(asset)
    db.flush()
    return asset


class TestVendor:
    def test_the_shipped_table_names_makers_longest_prefix_first(self):
        assert oui.vendor_of("00:00:00:12:34:56") == "XEROX CORPORATION"  # MA-L
        assert (
            oui.vendor_of("00-55-DA-01-02-03") == "Shinko Technos co.,ltd."
        )  # MA-M carve-out
        assert len(oui.table()) > 30000

    def test_a_locally_administered_mac_has_no_vendor(self):
        assert oui.vendor_of("52:54:00:12:34:56") is None  # QEMU
        assert oui.vendor_of("d6:e4:8f:03:23:e9") is None  # a randomized phone MAC
        assert oui.vendor_of("garbage") is None

    def test_a_missing_table_is_loud_not_fatal(self, tmp_path):
        assert oui._load(str(tmp_path / "missing.tsv.gz")) == {}


class TestClassificationOnIngest:
    def test_vendor_and_a_labeled_guess_are_stored(self, db):
        observer = _host(db, "a1")
        report = {
            "interfaces": [
                {"name": "eth0", "mac": "aa:bb:cc:00:00:01", "network": "10.0.0.0/24"}
            ],
            "observations": [
                {
                    "mac": "00:00:00:12:34:56",
                    "ip": "10.0.0.21",
                    "interface": "eth0",
                    "methods": ["mdns"],
                }
            ],
        }

        class WithEvidence(ClassifyingEngine):
            def sanitize_report(self, payload):
                clean = super().sanitize_report(payload)
                clean["observations"][0]["evidence"] = {
                    "mdns_services": ["_ipp._tcp"],
                    "ssdp": [],
                }
                return clean

        with patch.object(svc.shim, "engine", return_value=WithEvidence()):
            svc.record_report(db, observer.id, report)
        asset = db.query(models.DiscoveredAsset).one()
        assert asset.vendor == "XEROX CORPORATION"
        assert asset.device_type == "printer"
        assert asset.classification == {"confidence": "high", "reasons": ["mdns:_ipp"]}

    def test_an_engine_without_classify_still_stores(self, db):
        observer = _host(db, "a1")
        report = {
            "interfaces": [],
            "observations": [
                {"mac": "00:00:00:12:34:56", "ip": "10.0.0.21", "methods": ["cache"]}
            ],
        }
        with patch.object(svc.shim, "engine", return_value=FakeEngine()):
            assert svc.record_report(db, observer.id, report)["stored"]
        asset = db.query(models.DiscoveredAsset).one()
        assert asset.vendor == "XEROX CORPORATION" and asset.device_type is None


class TestRetention:
    def test_only_the_unseen_are_forgotten_and_exclusions_survive(self, db):
        agent = _host(db, "a1")
        old = _device(
            db,
            "00:1a:2b:00:00:01",
            "10.121.1.9",
            seen=datetime.utcnow() - timedelta(days=45),
        )
        _device(db, "00:1a:2b:00:00:02", "10.0.0.22")
        db.add(
            models.DiscoveredAssetSighting(
                asset_id=old.id, observer_host_id=agent.id, sightings=1
            )
        )
        review.exclude(
            db, [old.id], "virtual_machine", "S0 test bed, torn down", "op@x"
        )
        assert policy.prune_devices(db) == 1  # default 30 days
        assert [a.identity for a in db.query(models.DiscoveredAsset)] == [
            "00:1a:2b:00:00:02"
        ]
        assert db.query(models.DiscoveredAssetSighting).count() == 0  # no orphans
        assert len(review.list_exclusions(db)) == 1  # the decision outlives the row

    def test_the_window_is_the_tenants_choice_from_a_fixed_set(self, db):
        policy.set_policy(db, True, 300, "op@x", retention_days=365)
        assert policy.get_policy(db)["retention_days"] == 365
        with pytest.raises(ValueError):
            policy.set_policy(db, True, 300, "op@x", retention_days=12)


class TestStaticAddresses:
    def test_a_registered_address_covers_whatever_holds_it(self, db):
        vip = _device(db, "00:00:5e:00:01:0a", "10.0.0.1")
        row = review.exclude_address(
            db, "10.0.0.1", "virtual_address", "Core VRRP VIP", "op@x"
        )
        assert row["identity"] == "ip:10.0.0.1"
        (listed,) = review.list_devices(db, "excluded")["devices"]
        assert (
            listed["identity"] == vip.identity
            and listed["exclusion"]["category"] == "virtual_address"
        )
        assert review.list_devices(db, "unmanaged")["total"] == 0

    def test_it_never_hides_a_managed_host(self, db):
        web = _host(db, "web")
        _device(db, "00:1a:2b:00:00:04", "10.0.0.5", managed_by=web.id)
        review.exclude_address(db, "10.0.0.5", "virtual_address", "legacy VIP", "op@x")
        assert review.list_devices(db, "managed")["total"] == 1
        assert review.list_devices(db, "excluded")["total"] == 0

    @pytest.mark.parametrize("address", ["not-an-ip", "10.0.0.300"])
    def test_bad_addresses_are_refused(self, db, address):
        with pytest.raises(review.ReviewError):
            review.exclude_address(db, address, "virtual_address", "VIP", "op@x")

    def test_one_active_registration_per_address(self, db):
        review.exclude_address(db, "10.0.0.1", "virtual_address", "VIP", "op@x")
        with pytest.raises(review.ReviewError):
            review.exclude_address(db, "10.0.0.1", "virtual_address", "again", "op@x")

    def test_the_summary_counts_what_the_unmanaged_look_like(self, db):
        printer = _device(db, "00:1a:2b:00:00:01", "10.0.0.21")
        printer.device_type = "printer"
        _device(db, "00:1a:2b:00:00:02", "10.0.0.22")
        db.flush()
        assert review.summary(db)["types"] == {"printer": 1, "unknown": 1}


class TestApi:
    def _user(self, *roles):
        return SimpleNamespace(
            id=uuid.uuid4(), userid="op@example.com", has_role=lambda r: r in roles
        )

    def test_a_static_address_needs_the_role_and_is_audited(self, db):
        request = api.AddressExclusionRequest(
            address="10.0.0.1", category="virtual_address", reason="Core VIP"
        )
        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(
                api.post_address_exclusion(
                    request, db, self._user(api.SecurityRoles.VIEW_HOST_DETAILS)
                )
            )
        assert excinfo.value.status_code == 403
        manager = self._user(api.SecurityRoles.MANAGE_NETWORK_DISCOVERY)
        with patch.object(api.AuditService, "log_create") as audit:
            row = asyncio.run(api.post_address_exclusion(request, db, manager))
        assert (
            row["identity"] == "ip:10.0.0.1"
            and audit.call_args.kwargs["details"]["static"] is True
        )

    def test_an_unsupported_retention_is_a_400(self, db):
        manager = self._user(api.SecurityRoles.MANAGE_NETWORK_DISCOVERY)
        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(
                api.put_policy(
                    api.PolicyRequest(enabled=True, retention_days=12), db, manager
                )
            )
        assert excinfo.value.status_code == 400
