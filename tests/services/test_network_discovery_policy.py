# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Network discovery policy, dispatch and re-correlation (Phase 21.6 S2).

What fails silently if got wrong:

  * listening must be OFF until an operator turns it on, and only agents that
    POSITIVELY advertise the command may be sent it (an older agent answers
    "Unknown command type");
  * a host that enrolls or reconnects after the change must still be told --
    reconciliation, not a one-shot broadcast;
  * a device first seen BEFORE its host enrolled must become managed when the
    host reports its interfaces, and stop being managed when the MAC moves.
"""

import asyncio
import json
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
from backend.services import asset_discovery_service as assets
from backend.services import background_ticks
from backend.services import network_discovery_policy as policy
from tests.services.test_asset_discovery_service import FakeEngine

CMD = "configure_network_discovery"


class RealishEngine(FakeEngine):
    """The FakeEngine plus the two helpers re-correlation needs."""

    @staticmethod
    def normalize_mac(value):
        return value.lower().replace("-", ":") if value else None

    @staticmethod
    def identity_ip(value):
        return value or None


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def sent():
    """Capture enqueued commands instead of writing a queue."""
    captured = []

    def _capture(_self, **kwargs):
        captured.append(kwargs)
        return kwargs["message_id"]

    with patch(
        "backend.websocket.queue_operations.QueueOperations.enqueue_message", _capture
    ):
        yield captured


def _host(db, name, commands=(CMD,), mac=None, ip=None, readvertised=None):
    host = models.Host(
        id=uuid.uuid4(),
        fqdn=name,
        ipv4=ip,
        active=True,
        status="up",
        approval_status="approved",
        agent_capabilities=(
            json.dumps({"schema_version": 1, "commands": list(commands)})
            if commands is not None
            else None
        ),
        agent_capabilities_updated_at=readvertised,
    )
    db.add(host)
    db.flush()
    if mac:
        _iface(db, host, mac, ip)
    return host


def _iface(db, host, mac, ip=None):
    db.add(
        models.NetworkInterface(
            host_id=host.id,
            interface_name="eth0",
            mac_address=mac,
            ipv4_address=ip,
            last_updated=datetime.utcnow(),
        )
    )
    db.flush()


class TestPolicy:
    def test_off_until_someone_turns_it_on(self, db):
        assert policy.get_policy(db)["enabled"] is False

    def test_the_interval_is_clamped_like_the_agent_does(self, db):
        policy.set_policy(db, True, 5, "a@b")
        assert policy.get_policy(db)["report_interval_seconds"] == 60
        policy.set_policy(db, True, 999999, "a@b")
        assert policy.get_policy(db)["report_interval_seconds"] == 3600
        assert policy.get_policy(db)["updated_by"] == "a@b"

    def test_set_returns_before_and_after_for_the_audit(self, db):
        change = policy.set_policy(db, True, 300, "a@b")
        assert (
            change["before"]["enabled"] is False and change["after"]["enabled"] is True
        )


class TestReconcile:
    def test_only_hosts_that_advertise_the_command_are_told(self, db, sent):
        capable = _host(db, "new-agent")
        _host(db, "old-agent", commands=("install_package",))
        _host(db, "never-reported", commands=None)
        policy.set_policy(db, True, 300, "a@b")
        summary = policy.reconcile(db)
        assert summary == {"queued": 1, "not_equipped": 2, "deferred": 0}
        assert sent[0]["host_id"] == str(capable.id)
        envelope = sent[0]["message_data"]
        assert envelope["data"]["command_type"] == CMD
        assert envelope["data"]["parameters"] == {
            "enabled": True,
            "report_interval_seconds": 300,
        }
        # ONE id for the envelope and the queue row -- the agent echoes it back.
        assert envelope["message_id"] == sent[0]["message_id"]
        row = db.query(models.NetworkDiscoveryDispatch).one()
        assert row.command_id == sent[0]["message_id"] and row.enabled is True

    def test_nothing_is_sent_while_off_to_a_host_never_told(self, db, sent):
        _host(db, "a1")
        assert policy.reconcile(db)["queued"] == 0 and sent == []

    def test_turning_it_off_tells_the_hosts_that_were_on(self, db, sent):
        _host(db, "a1")
        policy.set_policy(db, True, 300, "a@b")
        policy.reconcile(db)
        policy.set_policy(db, False, 300, "a@b")
        policy.reconcile(db)
        assert [c["message_data"]["data"]["parameters"]["enabled"] for c in sent] == [
            True,
            False,
        ]

    def test_no_resend_when_nothing_changed(self, db, sent):
        _host(db, "a1")
        policy.set_policy(db, True, 300, "a@b")
        policy.reconcile(db)
        policy.reconcile(db)
        assert len(sent) == 1

    def test_a_reinstalled_agent_is_told_again(self, db, sent):
        host = _host(db, "a1")
        policy.set_policy(db, True, 300, "a@b")
        policy.reconcile(db)
        # It re-advertised AFTER we told it: a restart may have lost the setting.
        host.agent_capabilities_updated_at = datetime.utcnow() + timedelta(minutes=5)
        db.flush()
        policy.reconcile(db)
        assert len(sent) == 2

    def test_a_tick_is_bounded(self, db, sent):
        for i in range(3):
            _host(db, f"h{i}")
        policy.set_policy(db, True, 300, "a@b")
        with patch.object(policy, "MAX_DISPATCHES_PER_TICK", 2):
            summary = policy.reconcile(db)
        assert summary["queued"] == 2 and summary["deferred"] == 1

    def test_the_tick_does_nothing_without_the_engine(self):
        with patch.object(policy.module_loader, "get_module", return_value=None):
            assert policy.run_one_tick() == {
                "queued": 0,
                "not_equipped": 0,
                "deferred": 0,
            }
            # advisor (21.2), network discovery (21.6), malware (21.3): none licensed.
            assert background_ticks.start_licensed_ticks() == [None, None, None]


class TestRecorrelate:
    @pytest.fixture(autouse=True)
    def _engine(self):
        with patch.object(assets.shim, "engine", return_value=RealishEngine()):
            yield

    def _device(self, db, mac, managed_by=None):
        asset = models.DiscoveredAsset(
            identity=mac,
            identity_kind="mac",
            mac=mac,
            mac_locally_administered=False,
            managed_host_id=managed_by,
            managed_reason="mac" if managed_by else None,
        )
        db.add(asset)
        db.flush()
        return asset

    def test_a_device_becomes_managed_when_its_host_enrolls(self, db):
        printer = self._device(db, "00:1a:2b:3c:4d:5e")
        host = _host(db, "late", mac="00-1A-2B-3C-4D-5E")  # Windows spelling
        assert assets.recorrelate_host(db, host.id) == 1
        assert printer.managed_host_id == host.id and printer.managed_reason == "mac"

    def test_a_device_is_released_when_its_mac_moves_away(self, db):
        host = _host(db, "h1", mac="00:1a:2b:3c:4d:5e")
        device = self._device(db, "00:1a:2b:3c:4d:5e", managed_by=host.id)
        db.query(models.NetworkInterface).delete()
        _iface(db, host, "00:1a:2b:3c:4d:99")
        assert assets.recorrelate_host(db, host.id) == 1
        assert device.managed_host_id is None and device.managed_reason is None

    def test_a_tap_port_is_attributed_when_its_guest_enrolls(self, db):
        tap = self._device(db, "fe:54:00:21:01:0b")
        guest = _host(db, "guest", mac="52:54:00:21:01:0b")
        assets.recorrelate_host(db, guest.id)
        assert (
            tap.managed_host_id == guest.id and tap.managed_reason == "hypervisor_port"
        )

    def test_nothing_happens_without_the_engine(self, db):
        with patch.object(assets.shim, "engine", return_value=None):
            assert assets.recorrelate_host(db, uuid.uuid4()) == 0


class TestApi:
    def _user(self, *roles):
        return SimpleNamespace(
            id=uuid.uuid4(), userid="op@example.com", has_role=lambda r: r in roles
        )

    def test_changing_it_needs_its_own_role(self, db):
        user = self._user(api.SecurityRoles.VIEW_HOST_DETAILS)
        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(api.put_policy(api.PolicyRequest(enabled=True), db, user))
        assert excinfo.value.status_code == 403

    def test_a_change_is_audited_and_applied_at_once(self, db, sent):
        _host(db, "a1")
        user = self._user(api.SecurityRoles.MANAGE_NETWORK_DISCOVERY)
        with patch.object(api.AuditService, "log_update") as audit:
            reply = asyncio.run(
                api.put_policy(
                    api.PolicyRequest(enabled=True, report_interval_seconds=120),
                    db,
                    user,
                )
            )
        assert reply["enabled"] is True and reply["report_interval_seconds"] == 120
        assert reply["dispatch"]["queued"] == 1 and len(sent) == 1
        details = audit.call_args.kwargs["details"]
        assert (
            details["before"]["enabled"] is False
            and details["after"]["enabled"] is True
        )

    def test_reading_it_needs_view_host_details(self, db):
        with pytest.raises(HTTPException):
            asyncio.run(api.get_policy(db, self._user()))
        reply = asyncio.run(
            api.get_policy(db, self._user(api.SecurityRoles.VIEW_HOST_DETAILS))
        )
        assert reply["enabled"] is False
