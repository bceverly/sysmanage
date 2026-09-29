# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Active sweeps (Phase 21.6 S4).

The one discovery method that puts traffic on a network. What must hold:

  * nothing is sent unless BOTH opt-ins are on (listening, then sweeping);
  * only an on-link network, swept by an agent that is ON it and says it can;
  * every run is recorded -- including refused and timed-out ones;
  * only the agent that was asked can close a run;
  * a fresh sweep clears the "silent devices unseen" blind spot for THAT
    network only.
"""

import asyncio
import ipaddress
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
from backend.services import asset_discovery_review as review
from backend.services import network_discovery_policy as policy
from backend.services import network_sweep as sweep

LAN = "192.168.4.0/24"


class FakeEngine:
    """The engine's sweep contract, minimally."""

    @staticmethod
    def validate_sweep(cidr, rate, known):
        try:
            net = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            return {
                "cidr": None,
                "rate": None,
                "addresses": 0,
                "errors": ["invalid_network"],
            }
        errors = []
        if net.num_addresses > 4096:
            errors.append("too_large")
        if str(net) not in known:
            errors.append("not_on_link")
        return {
            "cidr": str(net),
            "rate": rate or 50,
            "addresses": net.num_addresses - 2,
            "errors": errors,
        }

    @staticmethod
    def choose_sweeper(cidr, candidates):
        fit = [c for c in candidates if cidr in c["networks"] and not c["busy"]]
        return fit[0]["host_id"] if fit else None


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
    captured = []

    def _capture(_self, **kwargs):
        captured.append(kwargs)
        return kwargs["message_id"]

    with patch(
        "backend.websocket.queue_operations.QueueOperations.enqueue_message", _capture
    ), patch.object(sweep.shim, "engine", return_value=FakeEngine()):
        yield captured


def _agent(db, name, commands=("run_network_sweep",), network=LAN, active=True):
    host = models.Host(
        id=uuid.uuid4(), fqdn=name, active=active, status="up", approval_status="approved",
        agent_capabilities=json.dumps({"schema_version": 1, "commands": list(commands)}),
    )  # fmt: skip
    db.add(host)
    db.flush()
    db.add(
        models.NetworkDiscoveryObserver(
            host_id=host.id, networks=[{"interface": "eth0", "network": network}],
            methods={"arp_listen": "ok"}, reports=1, last_report_at=datetime.utcnow(),
        )  # fmt: skip
    )
    db.flush()
    return host


def _allow(db, sweeps=True):
    policy.set_policy(db, True, 300, "op@x", sweep_enabled=sweeps)


class TestRequest:
    def test_both_opt_ins_are_required(self, db, sent):
        _agent(db, "a1")
        with pytest.raises(sweep.SweepError) as excinfo:
            sweep.request_sweep(db, LAN, 50, "op@x")  # nothing enabled
        assert excinfo.value.code == "sweeps_disabled"
        _allow(db, sweeps=False)  # listening on, sweeping off
        with pytest.raises(sweep.SweepError):
            sweep.request_sweep(db, LAN, 50, "op@x")
        assert sent == [] and db.query(models.NetworkSweepRun).count() == 0

    def test_a_sweep_goes_to_an_agent_on_the_network(self, db, sent):
        _agent(db, "elsewhere", network="10.9.9.0/24")
        _agent(db, "no-command", commands=("install_package",))
        onlan = _agent(db, "on-lan")
        _allow(db)
        run = sweep.request_sweep(db, "192.168.4.9/24", 25, "op@x")
        assert run["cidr"] == LAN and run["rate"] == 25 and run["status"] == "queued"
        assert run["agent_host_id"] == str(onlan.id) and run["requested_by"] == "op@x"
        (command,) = sent
        assert command["host_id"] == str(onlan.id)
        assert command["message_data"]["data"]["parameters"] == {
            "run_id": run["id"],
            "cidr": LAN,
            "rate": 25,
        }
        assert (
            db.query(models.NetworkSweepRun).one().command_id == command["message_id"]
        )

    @pytest.mark.parametrize(
        "cidr,code", [("172.16.0.0/24", "not_on_link"), ("10.0.0.0/16", "too_large")]
    )
    def test_the_engine_refuses_with_a_reason(self, db, sent, cidr, code):
        _agent(db, "a1")
        _allow(db)
        with pytest.raises(sweep.SweepError) as excinfo:
            sweep.request_sweep(db, cidr, 50, "op@x")
        assert excinfo.value.code == code and str(excinfo.value)
        assert sent == []

    def test_one_sweep_at_a_time_per_agent(self, db, sent):
        _agent(db, "a1")
        _allow(db)
        sweep.request_sweep(db, LAN, 50, "op@x")
        with pytest.raises(sweep.SweepError) as excinfo:
            sweep.request_sweep(db, LAN, 50, "op@x")
        assert excinfo.value.code == "busy"


class TestResults:
    def _queued(self, db, sent):
        agent = _agent(db, "a1")
        _allow(db)
        return agent, sweep.request_sweep(db, LAN, 50, "op@x")

    def test_the_asked_agent_closes_the_run(self, db, sent):
        agent, run = self._queued(db, sent)
        result = {
            "run_id": run["id"],
            "status": "completed",
            "probed": 254,
            "reason": None,
            "cidr": LAN,
        }
        assert sweep.record_result(db, agent.id, result, 7)
        row = db.query(models.NetworkSweepRun).one()
        assert (row.status, row.probed, row.devices_found) == ("completed", 254, 7)
        assert row.finished_at is not None

    def test_another_agent_cannot_close_it(self, db, sent):
        _agent_, run = self._queued(db, sent)
        stranger = _agent(db, "stranger")
        result = {
            "run_id": run["id"],
            "status": "completed",
            "probed": 254,
            "reason": None,
            "cidr": LAN,
        }
        assert not sweep.record_result(db, stranger.id, result, 7)
        assert db.query(models.NetworkSweepRun).one().status == "queued"

    def test_a_refusal_is_recorded_with_its_reason(self, db, sent):
        agent, run = self._queued(db, sent)
        refused = {
            "run_id": run["id"],
            "status": "refused",
            "probed": 0,
            "reason": "not_on_link",
            "cidr": LAN,
        }
        sweep.record_result(db, agent.id, refused, 3)
        row = db.query(models.NetworkSweepRun).one()
        assert (row.status, row.reason, row.devices_found) == (
            "refused",
            "not_on_link",
            0,
        )

    def test_an_unanswered_run_times_out(self, db, sent):
        self._queued(db, sent)
        later = datetime.utcnow() + timedelta(hours=2)
        assert sweep.expire_stale(db, later) == 1
        assert db.query(models.NetworkSweepRun).one().status == "timed_out"

    def test_a_fresh_sweep_clears_that_networks_blind_spot_only(self, db, sent):
        agent, run = self._queued(db, sent)
        _agent(db, "other", network="10.121.2.0/24")
        before = review.summary(db)["blind_spots"]
        assert sorted(before["unswept_networks"]) == ["10.121.2.0/24", LAN]
        sweep.record_result(
            db, agent.id,
            {"run_id": run["id"], "status": "completed", "probed": 254, "reason": None, "cidr": LAN}, 2,
        )  # fmt: skip
        after = review.summary(db)["blind_spots"]
        assert after["unswept_networks"] == ["10.121.2.0/24"]
        assert after["silent_devices_unseen"] is True  # one network is still unswept
        assert sweep.list_runs(db)[0]["agent_fqdn"] == "a1"


class TestApi:
    def _user(self, *roles):
        return SimpleNamespace(
            id=uuid.uuid4(), userid="op@example.com", has_role=lambda r: r in roles
        )

    def test_sweeping_needs_the_discovery_role_and_is_audited(self, db, sent):
        _agent(db, "a1")
        _allow(db)
        request = api.SweepRequest(cidr=LAN, rate=50)
        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(
                api.post_sweep(
                    request, db, self._user(api.SecurityRoles.VIEW_HOST_DETAILS)
                )
            )
        assert excinfo.value.status_code == 403
        manager = self._user(api.SecurityRoles.MANAGE_NETWORK_DISCOVERY)
        with patch.object(api.AuditService, "log_create") as audit:
            run = asyncio.run(api.post_sweep(request, db, manager))
        assert run["status"] == "queued"
        assert audit.call_args.kwargs["entity_type"] == api.EntityType.NETWORK_SWEEP
        assert audit.call_args.kwargs["details"]["cidr"] == LAN
        with pytest.raises(HTTPException) as excinfo:  # the only agent is now busy
            asyncio.run(api.post_sweep(request, db, manager))
        assert excinfo.value.status_code == 409

    def test_the_policy_carries_the_sweep_opt_in(self, db, sent):
        manager = self._user(api.SecurityRoles.MANAGE_NETWORK_DISCOVERY)
        with patch.object(api.AuditService, "log_update"):
            reply = asyncio.run(
                api.put_policy(
                    api.PolicyRequest(enabled=True, sweep_enabled=True), db, manager
                )
            )
        assert reply["sweep_enabled"] is True
        with patch.object(api.AuditService, "log_update"):
            kept = asyncio.run(
                api.put_policy(api.PolicyRequest(enabled=True), db, manager)
            )
        assert kept["sweep_enabled"] is True  # omitted keeps it
