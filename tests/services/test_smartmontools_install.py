# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""smartmontools where drives cannot be read (Phase 23.1 S6): recommended
only for hosts that need it, installed by an operator or -- licensed AND
consented -- automatically, retried with backoff, done when the agent says."""

import itertools
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest

from backend.persistence import models
from backend.services import hardware_health, smartmontools_install as si

ABSENT = [{"code": "smartctl_absent"}]


def _host(session, fqdn, reasons=None, kind="drive", **fields):
    host = models.Host(
        id=uuid.uuid4(),
        fqdn=fqdn,
        active=fields.pop("active", True),
        approval_status=fields.pop("approval_status", "approved"),
    )
    session.add(host)
    session.commit()
    hardware_health.apply_report(
        session,
        host,
        {
            "components": [
                {
                    "kind": kind,
                    "id": "ada0",
                    "name": "Samsung SSD 860 EVO",
                    "state": "unknown" if reasons else "ok",
                    "reasons": reasons or [],
                    "metrics": {},
                    "source": None if reasons else "smartctl",
                }
            ],
            "sources": [{"name": "smartctl", "status": "absent"}],
        },
    )
    session.commit()
    return host


@pytest.fixture
def queued():
    ids = (f"cmd-{n}" for n in itertools.count())
    sent = []

    def fake(_db, host_id, command_type, parameters):
        sent.append((str(host_id), command_type, parameters))
        return next(ids)

    with patch.object(si.config_mgmt_dispatch, "queue_command", side_effect=fake):
        yield sent


@pytest.fixture
def consented():
    with patch.object(si, "licensed", return_value=True), patch.object(
        si, "auto_enabled", return_value=True
    ):
        yield


def test_recommended_only_where_a_drive_needs_smartctl(session):
    needs = _host(session, "freebsd.lab", ABSENT)
    _host(session, "beast.lab")  # readable
    _host(session, "pending.lab", ABSENT, approval_status="pending")
    _host(session, "gone.lab", ABSENT, active=False)
    _host(session, "sensor.lab", ABSENT, kind="sensor")
    _host(session, "other.lab", [{"code": "smartctl_failed", "rc": 2}])
    assert [h.id for h in si.recommended_hosts(session)] == [needs.id]


def test_an_install_is_the_generic_plan_and_done_when_the_agent_says(session, queued):
    host = _host(session, "freebsd.lab", ABSENT)
    command_id = si.queue_install(session, host, "admin@example.com")
    session.commit()
    assert queued == [
        (
            str(host.id),
            "apply_deployment_plan",
            {"plan": {"packages": ["smartmontools"]}},
        )
    ]
    view = si.installs_by_host(session, [host.id])[str(host.id)]
    assert (view["status"], view["requested_by"], view["attempts"]) == (
        "queued",
        "admin@example.com",
        0,
    )
    assert not si.record_result(session, {"command_id": "someone-else"})
    assert si.record_result(
        session,
        {
            "command_id": command_id,
            "success": True,
            "result": {"success": False, "errors": ["pkg: No packages available"]},
        },
    )
    view = si.installs_by_host(session, [host.id])[str(host.id)]
    assert view["status"] == "failed" and "No packages" in view["last_error"]


def test_debian_family_installs_without_a_mail_server():
    ubuntu = models.Host(platform="Linux", platform_release="Ubuntu 22.04")
    plan = si.build_plan(ubuntu)
    install = plan["commands"][1]["argv"]
    assert "--no-install-recommends" in install and install[-1] == "smartmontools"
    assert "DEBIAN_FRONTEND=noninteractive" in install
    assert plan["commands"][0]["ignore_errors"] and "packages" not in plan
    for host in (
        models.Host(platform="Linux", platform_release="Fedora Linux 42"),
        models.Host(platform="FreeBSD", platform_release="14.4-RELEASE"),
        models.Host(platform=None, platform_release=None),
    ):
        assert si.build_plan(host) == {"packages": ["smartmontools"]}


def test_nothing_automatic_without_license_and_consent(session, queued):
    _host(session, "freebsd.lab", ABSENT)
    with patch.object(si, "licensed", return_value=False), patch.object(
        si, "auto_enabled", return_value=True
    ):
        assert si.reconcile(session, None) == 0
    with patch.object(si, "licensed", return_value=True), patch.object(
        si, "auto_enabled", return_value=False
    ):
        assert si.reconcile(session, None) == 0
    assert not queued


def test_automatic_install_backs_off_and_retries(session, queued, consented):
    host = _host(session, "freebsd.lab", ABSENT)
    with patch.object(si, "_audit"):
        assert si.reconcile(session, None) == 1
        assert si.reconcile(session, None) == 0  # waiting for the answer
        record = session.query(models.HardwareToolInstall).one()
        assert (record.attempts, record.requested_by) == (1, si.SYSTEM_ACTOR)
        si.record_result(session, {"command_id": record.command_id, "success": False})
        assert si.reconcile(session, None) == 0  # backing off
        record.finished_at -= si.retry_delay(1, host.id) + timedelta(minutes=1)
        session.commit()
        assert si.reconcile(session, None) == 1
        assert record.attempts == 2
    assert len(queued) == 2


def test_a_success_ends_it_once_the_drives_are_readable(session, queued, consented):
    host = _host(session, "freebsd.lab", ABSENT)
    with patch.object(si, "_audit"):
        si.reconcile(session, None)
        record = session.query(models.HardwareToolInstall).one()
        si.record_result(session, {"command_id": record.command_id, "success": True})
        record.finished_at -= timedelta(hours=2)
        session.commit()
        # still unreadable an hour after a success: tried again
        assert si.reconcile(session, None) == 1
        hardware_health.apply_report(
            session,
            host,
            {
                "components": [
                    {
                        "kind": "drive",
                        "id": "ada0",
                        "state": "ok",
                        "reasons": [],
                        "metrics": {},
                        "source": "smartctl",
                    }
                ],
                "sources": [{"name": "smartctl", "status": "ran"}],
            },
        )
        session.commit()
        record.status, record.finished_at = "failed", record.requested_at
        record.requested_at -= timedelta(days=3)
        record.finished_at = record.requested_at
        session.commit()
        assert si.reconcile(session, None) == 0  # readable: nothing to do


def test_undelivered_is_a_failed_attempt(session, queued, consented):
    host = _host(session, "freebsd.lab", ABSENT)
    with patch.object(si, "_audit"):
        si.reconcile(session, None)
    record = session.query(models.HardwareToolInstall).one()
    session.add(
        models.MessageQueue(
            host_id=host.id,
            message_id=record.command_id,
            direction="outbound",
            message_type="command",
            message_data="{}",
            status="failed",
            priority="normal",
            created_at=record.requested_at,
            error_message="no acknowledgment",
        )
    )
    session.commit()
    si._mark_undelivered(session)  # pylint: disable=protected-access
    assert record.status == "failed" and "not delivered" in record.last_error


def test_consent_is_per_tenant():
    with patch.object(si.settings_service, "get_tenant_setting", return_value=True):
        assert si.auto_enabled("t1")
    with patch.object(si.settings_service, "get_setting", return_value=None):
        assert not si.auto_enabled(None)
    with patch.object(
        si.settings_service, "set_tenant_setting", return_value=True
    ) as tenant, patch.object(si.settings_service, "set_setting", return_value=True):
        assert si.set_auto("t1", True)
    tenant.assert_called_once_with("t1", si.SETTING_AUTO, True)
