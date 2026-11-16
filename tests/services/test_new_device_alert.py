# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The ``new_network_device`` alert (ROADMAP 26.9), on the real compiled
alerting engine and a real database: a device is new once, the baseline is
never alerted on, the type filter holds, a burst is one alert, and a DHCP
renumber of a known device says nothing unless asked."""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.persistence import models


@pytest.fixture(name="alerting")
def _engine():
    from tests._engine_loader import (  # pylint: disable=import-outside-toplevel
        require_engine,
    )

    return require_engine("alerting_engine")


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class _World:
    """An observer host with an alert rule, and devices it sees."""

    def __init__(self, session, engine, params=None, rule_age_hours=48):
        self.session = session
        self.engine = engine
        self.host = models.Host(
            fqdn="beast", ipv4="192.168.4.2", active=True, status="up",
            approval_status="approved",
        )  # fmt: skip
        session.add(self.host)
        self.rule = models.AlertRule(
            name="New device", condition_type="new_network_device",
            condition_params=params or {}, severity="medium", enabled=True,
            cooldown_minutes=0, host_filter={},
            created_at=_now() - timedelta(hours=rule_age_hours),
        )  # fmt: skip
        session.add(self.rule)
        session.commit()
        self.sent = []
        self.service = engine.AlertingServiceImpl()
        self.service.configure(models, None, logging.getLogger("test"))
        self.service._dispatch_notification = (  # pylint: disable=protected-access
            lambda *a, **k: self.sent.append(a) or True
        )

    def device(self, mac, ip, device_type="iot", age_minutes=30, observer_age_hours=24):
        first = _now() - timedelta(minutes=age_minutes)
        asset = models.DiscoveredAsset(
            identity=mac, identity_kind="mac", mac=mac, last_ip=ip, ips=[ip],
            device_type=device_type, vendor="Espressif",
            classification={"confidence": "high", "reasons": ["mdns"]},
            first_seen_at=first, last_seen_at=_now(),
        )  # fmt: skip
        self.session.add(asset)
        self.session.flush()
        self.session.add(
            models.DiscoveredAssetSighting(
                asset_id=asset.id, observer_host_id=self.host.id,
                network="192.168.4.0/24", ip=ip, sightings=3,
                first_seen_at=first, last_seen_at=_now(),
            )
        )  # fmt: skip
        self._observer_started(observer_age_hours)
        self.session.commit()
        return asset

    def _observer_started(self, hours):
        """An older sighting so the agent is past its first hour."""
        old = _now() - timedelta(hours=hours)
        marker = "02:00:00:00:00:01"
        if (
            self.session.query(models.DiscoveredAsset)
            .filter_by(identity=marker)
            .first()
        ):
            return
        asset = models.DiscoveredAsset(
            identity=marker, identity_kind="mac", mac=marker, last_ip="192.168.4.1",
            ips=["192.168.4.1"], device_type="network_equipment",
            first_seen_at=old, last_seen_at=_now(),
        )  # fmt: skip
        self.session.add(asset)
        self.session.flush()
        self.session.add(
            models.DiscoveredAssetSighting(
                asset_id=asset.id, observer_host_id=self.host.id,
                network="192.168.4.0/24", ip="192.168.4.1", sightings=1,
                first_seen_at=old, last_seen_at=_now(),
            )
        )  # fmt: skip

    def evaluate(self):
        return self.service.evaluate_all_rules(self.session)

    def alerts(self):
        return self.session.query(models.Alert).all()


def _baselined(world):
    """The rule's first pass: everything present becomes the baseline."""
    world.device("aa:00:00:00:00:01", "192.168.4.10", device_type="computer")
    assert world.evaluate() == 0
    assert world.alerts() == []


def test_the_first_pass_is_the_baseline_and_never_alerts(session, alerting):
    world = _World(session, alerting)
    _baselined(world)
    outcomes = {m.outcome for m in session.query(models.NewDeviceAlertMark)}
    assert outcomes == {"baseline"}


def test_a_new_device_alerts_once_naming_it(session, alerting):
    world = _World(session, alerting)
    _baselined(world)
    world.device("24:0a:c4:11:22:33", "192.168.4.77")

    assert world.evaluate() == 1
    alert = world.alerts()[0]
    assert alert.host_id == world.host.id
    assert "192.168.4.77" in alert.message and "24:0a:c4:11:22:33" in alert.message
    assert "/asset-discovery?search=24%3A0a%3Ac4%3A11%3A22%3A33" in alert.message
    assert alert.details["devices"][0]["device_type"] == "iot"

    assert world.evaluate() == 0  # a device is new once
    assert len(world.alerts()) == 1


def test_a_burst_is_one_alert(session, alerting):
    world = _World(session, alerting)
    _baselined(world)
    for n in range(3):
        world.device(f"24:0a:c4:00:00:0{n}", f"192.168.4.8{n}")
    assert world.evaluate() == 1
    assert world.alerts()[0].details["count"] == 3


def test_the_type_filter_holds(session, alerting):
    world = _World(session, alerting, params={"device_types": ["iot"]})
    _baselined(world)
    world.device("aa:00:00:00:00:99", "192.168.4.99", device_type="computer")
    assert world.evaluate() == 0
    mark = (
        session.query(models.NewDeviceAlertMark)
        .filter_by(identity="aa:00:00:00:00:99")
        .one()
    )
    assert mark.outcome == "filtered"


def test_a_device_not_settled_yet_waits(session, alerting):
    world = _World(session, alerting)
    _baselined(world)
    world.device("24:0a:c4:aa:bb:cc", "192.168.4.50", age_minutes=1)
    assert world.evaluate() == 0
    assert (
        not session.query(models.NewDeviceAlertMark)
        .filter_by(identity="24:0a:c4:aa:bb:cc")
        .first()
    )


def test_an_agents_first_hour_is_its_baseline(session, alerting):
    world = _World(session, alerting)
    _baselined(world)
    session.query(models.DiscoveredAssetSighting).delete()
    session.commit()
    # A new segment's agent: its oldest sighting is 30 minutes old.
    world.device("24:0a:c4:de:ad:01", "10.0.0.5", observer_age_hours=0.5)
    assert world.evaluate() == 0


def test_a_dhcp_renumber_is_silent_unless_asked(session, alerting):
    for asked, expected in ((False, 0), (True, 1)):
        world = _World(session, alerting, params={"new_address": asked})
        _baselined(world)
        known = (
            session.query(models.DiscoveredAsset)
            .filter_by(identity="aa:00:00:00:00:01")
            .one()
        )
        known.last_ip, known.ips = "192.168.4.11", ["192.168.4.11", "192.168.4.10"]
        session.commit()
        assert world.evaluate() == expected
        session.query(models.Alert).delete()
        session.query(models.NewDeviceAlertMark).delete()
        session.query(models.DiscoveredAssetSighting).delete()
        session.query(models.DiscoveredAsset).delete()
        session.query(models.AlertRule).delete()
        session.commit()


def test_an_excluded_device_is_not_new(session, alerting):
    world = _World(session, alerting)
    _baselined(world)
    session.add(
        models.DiscoveredAssetExclusion(
            id=uuid.uuid4(), identity="24:0a:c4:ee:ee:ee", category="iot",
            reason="the thermostat", created_by="bryan@theeverlys.com",
        )
    )  # fmt: skip
    world.device("24:0a:c4:ee:ee:ee", "192.168.4.60")
    assert world.evaluate() == 0


def test_html_email_text_is_escaped(alerting):
    text = alerting._html_text(
        '<script>x</script>\n"name"'
    )  # pylint: disable=protected-access
    assert "<script>" not in text and "&lt;script&gt;" in text and "<br>" in text


def test_names_from_the_network_cannot_inject_markup(alerting):
    host = SimpleNamespace(fqdn="beast")
    entry = {
        "kind": "new_device", "identity": "x", "mac": "aa:bb:cc:dd:ee:ff",
        "addresses": ["192.168.4.5"], "vendor": None, "device_type": "unknown",
        "confidence": "none", "reasons": [], "names": ["<img src=x>"],
        "randomized": True, "network": "192.168.4.0/24",
        "first_seen_at": "2026-11-16T12:00:00",
    }  # fmt: skip
    message = alerting.new_device_message(host, [entry])
    assert "<img src=x>" in message  # plain text keeps it
    assert "<img" not in alerting._html_text(
        message
    )  # pylint: disable=protected-access
