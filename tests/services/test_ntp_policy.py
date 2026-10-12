# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The fleet NTP policy (Phase 23.3 S5b): resolution, compliance, apply in
waves with backoff, results, and auto-resync on breach."""

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from backend.persistence import models
from backend.services import ntp_policy as np
from tests.services import _fake_ntp_engine

LAB = ["ntp1.lab", "ntp2.lab"]


@pytest.fixture(autouse=True)
def fake_engine():
    with patch.object(
        np.config_mgmt_spec_shim, "engine_module", return_value=_fake_ntp_engine
    ):
        yield


@pytest.fixture
def queued():
    calls = []

    def fake(_db, host_id, command_type, parameters):
        calls.append((str(host_id), command_type, parameters))
        return str(uuid.uuid4())

    with patch("backend.services.config_mgmt_dispatch.queue_command", side_effect=fake):
        yield calls


def _host(session, servers=None, service="chrony", enabled=True, **fields):
    fields.setdefault("is_agent_privileged", True)
    host = models.Host(
        id=uuid.uuid4(),
        fqdn=f"{uuid.uuid4().hex[:6]}.lab",
        active=True,
        approval_status="approved",
        platform="Linux",
        time_service=service,
        time_service_enabled=enabled,
        time_configured_servers=None if servers is None else json.dumps(servers),
        **fields,
    )
    session.add(host)
    session.commit()
    return host


def _tag(session, host=None):
    now = datetime.utcnow()
    tag = models.Tag(
        id=uuid.uuid4(), name=uuid.uuid4().hex[:8], created_at=now, updated_at=now
    )
    session.add(tag)
    if host is not None:
        session.add(
            models.HostTag(
                id=uuid.uuid4(), host_id=host.id, tag_id=tag.id, created_at=now
            )
        )
    session.commit()
    return tag


def test_no_engine_judges_nothing(session):
    host = _host(session, ["pool.ntp.org"])
    np.set_policy(session, "fleet", "", LAB, True, False, "admin")
    with patch.object(np.config_mgmt_spec_shim, "engine_module", return_value=None):
        assert np.evaluate(session, [host]) == {}
        assert np.reconcile(session) == {"pushed": 0, "resynced": 0}


def test_compliance_against_the_most_specific_policy(session):
    site = uuid.uuid4()
    fleet_ok = _host(session, LAB)
    drifted = _host(session, ["pool.ntp.org"], enabled=False)
    sited = _host(session, ["10.0.0.1"], site_id=site)
    np.set_policy(session, "fleet", "", LAB, False, False, "admin")
    np.set_policy(session, "site", str(site), ["10.0.0.1"], False, False, "admin")
    judged = np.evaluate(session, [fleet_ok, drifted, sited])
    assert judged[str(fleet_ok.id)]["compliant"] is True
    assert [f["code"] for f in judged[str(drifted.id)]["findings"]] == [
        "servers_differ",
        "not_enabled",
    ]
    assert judged[str(sited.id)]["compliant"] is True  # the site's own pair


def test_no_policy_is_unjudged_and_a_tag_conflict_is_reported(session):
    host = _host(session, LAB)
    assert np.evaluate(session, [host])[str(host.id)]["compliant"] is None
    a, b = _tag(session, host), _tag(session, host)
    np.set_policy(session, "tag", str(a.id), LAB, True, False, "admin")
    np.set_policy(session, "tag", str(b.id), ["other.lab"], True, False, "admin")
    verdict = np.evaluate(session, [host])[str(host.id)]
    assert verdict["conflict"] and verdict["policy"] is None
    assert verdict["findings"] == [{"code": "policy_conflict"}]
    # Two tags with the SAME servers are no conflict.
    np.set_policy(session, "tag", str(b.id), list(reversed(LAB)), True, False, "admin")
    assert np.evaluate(session, [host])[str(host.id)]["conflict"] is False


def test_an_enforced_policy_is_applied_once(session, queued):
    host = _host(session, ["pool.ntp.org"])
    np.set_policy(session, "fleet", "", LAB, True, False, "admin")
    assert np.reconcile(session)["pushed"] == 1
    ((host_id, command, params),) = queued
    assert (host_id, command) == (str(host.id), "apply_deployment_plan")
    assert params["plan"]["files"][0]["servers"] == LAB
    assert np.reconcile(session)["pushed"] == 0  # queued: not sent twice
    state = session.get(models.NtpPolicyState, host.id)
    assert (state.status, state.attempts) == ("queued", 1)


def test_report_only_never_applies(session, queued):
    _host(session, ["pool.ntp.org"])
    np.set_policy(session, "fleet", "", LAB, False, False, "admin")
    assert np.reconcile(session)["pushed"] == 0 and queued == []


def test_hosts_that_cannot_be_fixed_or_are_unprivileged_are_left(session, queued):
    _host(session, None, service="none")
    _host(session, ["pool.ntp.org"], is_agent_privileged=False)
    np.set_policy(session, "fleet", "", LAB, True, False, "admin")
    assert np.reconcile(session)["pushed"] == 0


def test_results_close_and_failures_back_off(session, queued):
    host = _host(session, ["pool.ntp.org"])
    np.set_policy(session, "fleet", "", LAB, True, False, "admin")
    np.reconcile(session)
    state = session.get(models.NtpPolicyState, host.id)
    assert np.record_result(
        session,
        {
            "command_id": state.command_id,
            "success": False,
            "result": {"success": False, "errors": ["chronyd: unit not found"]},
        },
    )
    session.commit()
    assert (state.status, state.last_error) == ("failed", "chronyd: unit not found")
    assert np.reconcile(session)["pushed"] == 0  # backing off
    later = datetime.utcnow() + timedelta(hours=2)
    assert np.reconcile(session, now=later)["pushed"] == 1
    assert state.attempts == 2
    assert np.record_result(session, {"command_id": state.command_id, "success": True})
    assert state.status == "succeeded" and state.last_error is None
    assert np.record_result(session, {"command_id": "unknown"}) is False


def test_a_changed_policy_is_sent_again(session, queued):
    host = _host(session, ["pool.ntp.org"])
    np.set_policy(session, "fleet", "", LAB, True, False, "admin")
    np.reconcile(session)
    state = session.get(models.NtpPolicyState, host.id)
    np.record_result(session, {"command_id": state.command_id, "success": True})
    session.commit()
    np.set_policy(session, "fleet", "", ["ntp3.lab"], True, False, "admin")
    assert np.reconcile(session)["pushed"] == 1


def test_waves_cap_a_pass(session, queued):
    for _ in range(3):
        _host(session, ["pool.ntp.org"])
    np.set_policy(session, "fleet", "", LAB, True, False, "admin")
    with patch.object(np, "MAX_PUSHES_PER_PASS", 2):
        assert np.reconcile(session)["pushed"] == 2
        assert np.reconcile(session)["pushed"] == 1


def test_auto_resync_on_breach_is_rate_limited(session):
    now = datetime.utcnow()
    host = _host(session, LAB, clock_offset_ms=9000.0, clock_measured_at=now)
    np.set_policy(session, "fleet", "", LAB, False, True, "admin")
    with patch.object(np.clock_resync, "release"):
        assert np.reconcile(session)["resynced"] == 1
        assert np.reconcile(session)["resynced"] == 0  # cooling down
    row = session.query(models.ClockResync).one()
    assert (row.host_id, row.requested_by) == (host.id, "system:ntp-policy")


def test_policy_crud(session):
    np.set_policy(session, "fleet", "", LAB, True, True, "admin")
    np.set_policy(session, "fleet", "", ["x.lab"], False, False, "admin")
    (row,) = session.query(models.NtpPolicy).all()
    assert (
        np.as_dict(row)["servers"] == ["x.lab"] and np.as_dict(row)["enforce"] is False
    )
    assert np.clear_policy(session, "fleet", "")
    assert not np.clear_policy(session, "fleet", "")
