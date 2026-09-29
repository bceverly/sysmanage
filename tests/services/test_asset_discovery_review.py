# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The review side of asset discovery (Phase 21.6 S3).

What fails silently if got wrong:

  * an exclusion must never hide a MANAGED host (managed always wins);
  * an exclusion must survive DHCP renumbering (keyed by MAC, not by IP);
  * "known and fine" needs a reason and an actor, and withdrawing it keeps the
    history;
  * the summary must carry the blind spots, or the list reads as complete.
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


def _device(db, mac, ip, managed_by=None, network="10.0.0.0/24", observer=None):
    asset = models.DiscoveredAsset(
        identity=mac,
        identity_kind="mac",
        mac=mac,
        mac_locally_administered=False,
        last_ip=ip,
        ips=[ip],
        managed_host_id=managed_by,
        managed_reason="mac" if managed_by else None,
    )
    db.add(asset)
    db.flush()
    if observer is not None:
        db.add(
            models.DiscoveredAssetSighting(
                asset_id=asset.id,
                observer_host_id=observer.id,
                network=network,
                methods=["arp_listen"],
                sightings=1,
            )
        )
        db.flush()
    return asset


@pytest.fixture
def lan(db):
    agent = _host(db, "agent.example.com")
    managed = _host(db, "web.example.com")
    printer = _device(db, "00:1a:2b:00:00:01", "10.0.0.21", observer=agent)
    phone = _device(db, "da:a1:19:00:00:02", "10.0.0.22", observer=agent)
    tv = _device(
        db, "00:1a:2b:00:00:03", "10.0.1.9", network="10.0.1.0/24", observer=agent
    )
    web = _device(
        db, "00:1a:2b:00:00:04", "10.0.0.5", managed_by=managed.id, observer=agent
    )
    return SimpleNamespace(agent=agent, printer=printer, phone=phone, tv=tv, web=web)


class TestListing:
    def test_statuses(self, db, lan):
        unmanaged = review.list_devices(db, "unmanaged")
        assert unmanaged["total"] == 3
        assert {
            d["identity"] for d in review.list_devices(db, "managed")["devices"]
        } == {lan.web.identity}
        device = next(
            d for d in unmanaged["devices"] if d["identity"] == lan.printer.identity
        )
        assert device["observers"] == ["agent.example.com"]
        assert device["networks"] == ["10.0.0.0/24"]

    def test_filters(self, db, lan):
        assert review.list_devices(db, "unmanaged", network="10.0.1.0/24")["total"] == 1
        assert review.list_devices(db, "all", search="10.0.0.2")["total"] == 2
        assert review.list_devices(db, "all", search="DA:A1")["total"] == 1

    def test_an_unknown_status_is_refused(self, db):
        with pytest.raises(review.ReviewError):
            review.list_devices(db, "everything")


class TestExclusions:
    def test_exclude_counts_every_outcome(self, db, lan):
        result = review.exclude(
            db,
            [lan.printer.id, lan.web.id, uuid.uuid4()],
            "printer",
            "Front office printer",
            "op@example.com",
        )
        assert (result["excluded"], result["skipped_managed"], result["not_found"]) == (
            1,
            1,
            1,
        )
        again = review.exclude(
            db, [lan.printer.id], "printer", "again", "op@example.com"
        )
        assert again["already_excluded"] == 1 and again["excluded"] == 0
        assert review.list_devices(db, "excluded")["total"] == 1
        assert review.list_devices(db, "unmanaged")["total"] == 2

    def test_managed_always_wins_over_an_exclusion(self, db, lan):
        # Even an exclusion row for a managed host's MAC cannot hide it.
        db.add(
            models.DiscoveredAssetExclusion(
                identity=lan.web.identity, category="other", reason="legacy row",
                created_by="x",
            )  # fmt: skip
        )
        db.flush()
        assert review.list_devices(db, "managed")["total"] == 1
        assert review.list_devices(db, "excluded")["total"] == 0

    def test_an_exclusion_survives_dhcp(self, db, lan):
        review.exclude(db, [lan.printer.id], "printer", "Front office printer", "op@x")
        lan.printer.last_ip, lan.printer.ips = "10.0.0.99", ["10.0.0.99", "10.0.0.21"]
        db.flush()
        (device,) = review.list_devices(db, "excluded")["devices"]
        assert device["last_ip"] == "10.0.0.99" and device["exclusion"]["reason"]

    @pytest.mark.parametrize(
        "category,reason", [("printer", "  "), ("toaster", "fine")]
    )
    def test_a_reason_and_a_known_category_are_required(
        self, db, lan, category, reason
    ):
        with pytest.raises(review.ReviewError):
            review.exclude(db, [lan.printer.id], category, reason, "op@x")

    def test_revoking_keeps_the_history(self, db, lan):
        made = review.exclude(db, [lan.printer.id], "printer", "Front office", "op@x")
        exclusion_id = uuid.UUID(made["exclusions"][0]["id"])
        row = review.revoke(db, exclusion_id, "Printer was replaced", "boss@x")
        assert (
            row["revoked_by"] == "boss@x"
            and row["revoke_reason"] == "Printer was replaced"
        )
        assert review.list_devices(db, "unmanaged")["total"] == 3
        assert review.list_exclusions(db) == []
        (history,) = review.list_exclusions(db, include_revoked=True)
        assert history["last_ip"] == "10.0.0.21"
        with pytest.raises(review.ReviewError):
            review.revoke(db, exclusion_id, "twice", "boss@x")


class TestSummary:
    def test_counts_networks_and_blind_spots(self, db, lan):
        db.add(
            models.NetworkDiscoveryObserver(
                host_id=lan.agent.id,
                methods={
                    "arp_listen": "unavailable:not_root",
                    "cache": "ok",
                    "sweep": "unavailable:disabled",  # policy's call, not a blind spot
                },
                reports=4,
                last_report_at=datetime.utcnow() - timedelta(hours=2),
            )
        )
        db.flush()
        result = review.summary(db)
        assert result["counts"] == {"unmanaged": 3, "managed": 1, "excluded": 0}
        assert result["networks"][0] == {
            "network": "10.0.0.0/24",
            "unmanaged": 2,
            "observers": 1,
            "swept_at": None,
        }
        (observer,) = result["observers"]
        assert observer["unavailable"] == {"arp_listen": "not_root"}
        assert observer["stale"] is True  # 2 h > 3 x 5 min
        spots = result["blind_spots"]
        assert spots["silent_devices_unseen"] is True
        assert (spots["stale_observers"], spots["observers_without_arp"]) == (1, 1)
        assert result["policy"]["enabled"] is False


class TestApi:
    def _user(self, *roles):
        return SimpleNamespace(
            id=uuid.uuid4(), userid="op@example.com", has_role=lambda r: r in roles
        )

    def test_viewing_needs_view_host_details(self, db):
        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(api.get_summary(db, self._user()))
        assert excinfo.value.status_code == 403

    def test_excluding_needs_the_discovery_role_and_is_audited(self, db, lan):
        request = api.ExcludeRequest(
            asset_ids=[str(lan.printer.id)], category="printer", reason="Front office"
        )
        viewer = self._user(api.SecurityRoles.VIEW_HOST_DETAILS)
        with pytest.raises(HTTPException):
            asyncio.run(api.post_exclusions(request, db, viewer))
        manager = self._user(api.SecurityRoles.MANAGE_NETWORK_DISCOVERY)
        with patch.object(api.AuditService, "log_create") as audit:
            result = asyncio.run(api.post_exclusions(request, db, manager))
        assert result["excluded"] == 1
        assert audit.call_args.kwargs["entity_name"] == lan.printer.identity

    def test_bad_input_is_a_400(self, db):
        manager = self._user(api.SecurityRoles.MANAGE_NETWORK_DISCOVERY)
        bad = api.ExcludeRequest(
            asset_ids=["not-a-uuid"], category="printer", reason="x"
        )
        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(api.post_exclusions(bad, db, manager))
        assert excinfo.value.status_code == 400
        viewer = self._user(api.SecurityRoles.VIEW_HOST_DETAILS)
        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(api.get_devices("nope", None, None, 100, 0, db, viewer))
        assert excinfo.value.status_code == 400

    def test_revoke_is_audited(self, db, lan):
        made = review.exclude(db, [lan.printer.id], "printer", "Front office", "op@x")
        manager = self._user(api.SecurityRoles.MANAGE_NETWORK_DISCOVERY)
        with patch.object(api.AuditService, "log_update") as audit:
            row = asyncio.run(
                api.post_revoke(
                    made["exclusions"][0]["id"],
                    api.RevokeRequest(reason="replaced"),
                    db,
                    manager,
                )
            )
        assert row["revoked_by"] == "op@example.com"
        assert audit.call_args.kwargs["details"]["revoked"] is True
