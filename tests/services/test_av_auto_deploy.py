# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Antivirus auto-deploy (Phase 21.3): hosts get ClamAV without a click.

What must hold:
  * an approved, active host with an OS default gets the deploy plan once per
    plan version, and not again while it waits for the answer;
  * DONE means the agent said the plan succeeded -- a host that reports
    ClamAV installed is NOT done if the plan failed (2026-09-30: an agent
    without BSD service control installed it and started nothing);
  * a failed plan is retried with growing backoff and never given up on;
  * a Deploy-button plan's result matches no record and is left alone;
  * pending/inactive hosts and OSes with no default are never touched.
"""

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence import models
from backend.persistence.db import Base
from backend.services import av_auto_deploy, av_plan_builder


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    now = datetime.utcnow()
    for os_name, package in (("Ubuntu", "clamav"), ("FreeBSD", "clamav")):
        session.add(
            models.AntivirusDefault(
                os_name=os_name,
                antivirus_package=package,
                created_at=now,
                updated_at=now,
            )
        )
    session.commit()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def queued():
    sent = []
    with patch.object(
        av_auto_deploy._queue_ops,
        "enqueue_message",
        side_effect=lambda **kw: sent.append(kw),
    ), patch.object(av_auto_deploy, "_audit"):
        yield sent


def _host(db, release="Ubuntu 24.04", platform="Linux", **kw):
    host = models.Host(
        id=uuid.uuid4(),
        fqdn=f"h-{uuid.uuid4().hex[:6]}.example",
        platform=platform,
        platform_release=release,
        active=kw.pop("active", True),
        approval_status=kw.pop("approval_status", "approved"),
        **kw,
    )
    db.add(host)
    db.commit()
    return host


def _age(db, host, hours, field="requested_at"):
    record = db.get(models.AntivirusAutoDeploy, host.id)
    setattr(record, field, datetime.utcnow() - timedelta(hours=hours))
    db.commit()


def _answer(db, message, success, errors=None):
    handled = av_auto_deploy.record_result(
        db,
        {
            "command_id": message["message_id"],
            "success": success,
            "result": {"success": success, "errors": errors or []},
        },
    )
    db.commit()
    return handled


def _plan(message):
    return message["message_data"]["data"]["parameters"]["plan"]


def test_a_host_gets_the_plan_once_and_waits_for_the_answer(db, queued):
    host = _host(db)
    assert av_auto_deploy.reconcile(db)["queued"] == 1
    db.commit()
    assert queued[0]["host_id"] == str(host.id)
    assert _plan(queued[0])["av_product"] == "clamav"
    # One id for the envelope and the queue row: the agent echoes it back.
    assert queued[0]["message_id"] == queued[0]["message_data"]["message_id"]
    record = db.get(models.AntivirusAutoDeploy, host.id)
    assert record.plan_version == av_plan_builder.PLAN_VERSION
    assert record.status == "queued" and record.attempts == 1
    summary = av_auto_deploy.reconcile(db)
    assert summary["queued"] == 0 and summary["waiting_result"] == 1


def test_only_a_succeeded_plan_is_done(db, queued):
    host = _host(db)
    av_auto_deploy.reconcile(db)
    db.commit()
    assert _answer(db, queued[0], True)
    assert db.get(models.AntivirusAutoDeploy, host.id).status == "succeeded"
    _age(db, host, 100)
    summary = av_auto_deploy.reconcile(db)
    assert summary["queued"] == 0 and summary["current"] == 1
    # A new plan version reaches it again.
    with patch.object(
        av_plan_builder, "PLAN_VERSION", av_plan_builder.PLAN_VERSION + 1
    ):
        assert av_auto_deploy.reconcile(db)["queued"] == 1


def test_a_failed_plan_is_retried_with_backoff_and_never_given_up(db, queued):
    host = _host(db)
    av_auto_deploy.reconcile(db)
    db.commit()
    assert _answer(db, queued[-1], False, ["Service control requires privileged mode"])
    record = db.get(models.AntivirusAutoDeploy, host.id)
    assert record.status == "failed" and "privileged" in record.last_error
    assert av_auto_deploy.reconcile(db)["waiting_retry"] == 1  # too soon
    for attempt in range(1, 8):
        _age(db, host, av_auto_deploy.retry_delay(attempt).total_seconds() / 3600 + 0.1,
             "finished_at")  # fmt: skip
        assert av_auto_deploy.reconcile(db)["queued"] == 1, attempt
        db.commit()
        _answer(db, queued[-1], False)
    assert db.get(models.AntivirusAutoDeploy, host.id).attempts == 8
    assert av_auto_deploy.retry_delay(1).total_seconds() == 3600
    assert av_auto_deploy.retry_delay(20).total_seconds() == 24 * 3600


def test_an_unanswered_plan_is_resent_after_a_day(db, queued):
    host = _host(db)
    av_auto_deploy.reconcile(db)
    db.commit()
    _age(db, host, av_auto_deploy.RETRY_MAX_HOURS + 1)
    assert av_auto_deploy.reconcile(db)["queued"] == 1


def test_a_result_for_some_other_plan_is_left_alone(db, queued):
    _host(db)
    assert not av_auto_deploy.record_result(
        db, {"command_id": "not-ours", "success": True}
    )
    assert not av_auto_deploy.record_result(db, {"success": True})


def test_hosts_that_are_not_eligible_are_left_alone(db, queued):
    _host(db, approval_status="pending")
    _host(db, active=False)
    _host(db, release="Plan9 4", platform="Plan9")
    summary = av_auto_deploy.reconcile(db)
    assert summary["queued"] == 0 and queued == []
    # Every skip is counted with its reason, so the log says why.
    assert summary["not_approved"] == 1 and summary["inactive"] == 1
    assert summary["no_default"] == 1 and summary["no_default_for"] == ["Plan"]


def test_os_names_match_the_defaults_table():
    name = av_auto_deploy.os_name_for_defaults
    assert (
        name(SimpleNamespace(platform="Linux", platform_release="Ubuntu 25.04"))
        == "Ubuntu"
    )
    assert (
        name(SimpleNamespace(platform="OpenBSD", platform_release="7.7")) == "OpenBSD"
    )
    assert (
        name(SimpleNamespace(platform="macOS", platform_release="Sequoia")) == "macOS"
    )
    assert name(SimpleNamespace(platform=None, platform_release=None)) is None


async def test_a_real_agent_result_reaches_the_record_through_the_queue(db):
    # Agents do not echo command_type; the handler recovers it from the queue
    # row, which only works because the envelope and the row share one id.
    from backend.api import message_handlers  # pylint: disable=import-outside-toplevel

    host = _host(db)
    with patch.object(av_auto_deploy, "_audit"):
        av_auto_deploy.reconcile(db)
    db.commit()
    command_id = db.get(models.AntivirusAutoDeploy, host.id).command_id
    await message_handlers.handle_command_result(
        db,
        SimpleNamespace(hostname=host.fqdn, host_id=str(host.id)),
        {"command_id": command_id, "success": False, "error": "boom", "result": None},
    )
    record = db.get(models.AntivirusAutoDeploy, host.id)
    assert record.status == "failed" and record.last_error == "boom"


def test_a_plan_the_queue_gave_up_delivering_is_retried_soon(db):
    # x13s, 2026-09-30: sent into a connection that never handed it over; the
    # queue failed it after three unacknowledged tries.  That is a failed
    # attempt (retry in an hour), not "waiting for an answer" (a day).
    host = _host(db)
    with patch.object(av_auto_deploy, "_audit"):
        av_auto_deploy.reconcile(db)
    db.commit()
    record = db.get(models.AntivirusAutoDeploy, host.id)
    row = (
        db.query(models.MessageQueue)
        .filter(models.MessageQueue.message_id == record.command_id)
        .one()
    )
    row.status = "failed"
    row.error_message = "No acknowledgment received within 60 seconds"
    db.commit()
    with patch.object(av_auto_deploy, "_audit"):
        summary = av_auto_deploy.reconcile(db)
    db.commit()
    record = db.get(models.AntivirusAutoDeploy, host.id)
    assert record.status == "failed" and "not delivered" in record.last_error
    assert summary["waiting_retry"] == 1
    _age(db, host, 1.1, "finished_at")
    with patch.object(av_auto_deploy, "_audit"):
        assert av_auto_deploy.reconcile(db)["queued"] == 1


def test_an_operator_opt_out_survives_a_new_plan_version(db, queued):
    host = _host(db)
    av_auto_deploy.operator_opt_out(db, host.id, "removed", "admin@example.com")
    db.commit()
    with patch.object(
        av_plan_builder, "PLAN_VERSION", av_plan_builder.PLAN_VERSION + 5
    ):
        summary = av_auto_deploy.reconcile(db)
    assert summary["queued"] == 0 and summary["opted_out"] == 1 and queued == []
    av_auto_deploy.operator_opt_in(db, host.id)
    db.commit()
    assert av_auto_deploy.reconcile(db)["queued"] == 1
