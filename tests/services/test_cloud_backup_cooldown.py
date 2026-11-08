# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Apple's refusal (HTTP 503) is waited out and the download tried again by
itself, schedule on or off, after a cooldown that doubles (24.12).  Written
after 2026-11-04: a first full pass stopped after 6,523 photos with "Apple
iCloud is temporary refusing to serve icloudpd" and nothing tried again."""

from datetime import timedelta

from backend.services import cloud_backup_jobs as cloud
from backend.services import cloud_backup_results as results
from backend.services import cloud_backup_tick as tick
from backend.services import cloud_backup_views as views
from tests.services.test_backup_results import (  # noqa: F401  # pylint: disable=unused-import
    _setup,
    sent,
)
from tests.services.test_cloud_backup import _enabled, _signed_in

REFUSED = (
    "2026-11-04 17:08:11 INFO     Downloaded /srv/x/2020/05/29/IMG_1858.HEIC\n"
    "2026-11-04 17:08:31 INFO     Apple iCloud is temporary refusing to serve icloudpd"
)


def _finish(session, s, account, when, **result):
    run = cloud.queue_account_run(session, account, cloud.RECONCILE, "ops")
    results.record_result(session, s.nas.id, {"run_id": str(run.id), **result})
    run.queued_at = when - timedelta(minutes=30)
    run.finished_at = when
    session.commit()  # as the result handler does
    return run


def _refused(session, s, account, when, reason="tool_failed"):
    """How an agent older than the "apple_busy" reason reports it."""
    return _finish(session, s, account, when, status="failed", exit_code=1,
                   reason=reason, detail=REFUSED,
                   message="icloudpd exited with status 1")  # fmt: skip


def _account(session, enabled):
    s = _setup(session)
    _enabled(session, s)
    return s, _signed_in(session, s, enabled=enabled)


def test_a_refusal_is_retried_after_an_hour_even_with_the_schedule_off(session, sent):
    s, account = _account(session, enabled=False)
    ended = cloud.now() - timedelta(minutes=10)
    run = _refused(session, s, account, ended)
    assert cloud.parse_json(run.result)["reason"] == tick.APPLE_BUSY
    shown = views.account_dict(session, account)
    assert shown["status"] == tick.COOLING_DOWN
    assert shown["retry_at"] == (ended + timedelta(hours=1)).isoformat()
    summary = views.summary(session)
    assert (summary["failed"], summary["running"]) == (0, 1)  # nobody need act
    assert not tick.due(session, account, ended + timedelta(minutes=59))
    assert tick.due(session, account, ended + timedelta(hours=1))
    # The retry carries on the same full pass.
    assert tick.transfer_action(account, cloud.now()) == cloud.RECONCILE


def test_the_cooldown_doubles_then_holds_at_twelve_hours(session, sent):
    s, account = _account(session, enabled=True)
    start = cloud.now() - timedelta(days=5)
    waits = []
    for index in range(6):
        _refused(session, s, account, start + timedelta(hours=index), "apple_busy")
        retry = tick.apple_retry_at(session, account)
        waits.append(retry - (start + timedelta(hours=index)))
    assert waits == [timedelta(hours=h) for h in (1, 2, 4, 8, 12, 12)]


def test_with_the_schedule_off_it_stops_after_the_last_try(session, sent):
    s, account = _account(session, enabled=False)
    start = cloud.now() - timedelta(days=5)
    for index in range(tick.APPLE_MAX_TRIES):
        _refused(session, s, account, start + timedelta(hours=index))
    assert tick.apple_retry_at(session, account) is None
    assert not tick.due(session, account, cloud.now() + timedelta(days=2))
    shown = views.account_dict(session, account)
    assert shown["status"] == "failed" and shown["last_run"]["reason"] == "apple_busy"
    # With a schedule it keeps trying, every 12 hours.
    account.enabled = True
    assert tick.apple_retry_at(session, account) is not None


def test_a_good_run_ends_the_cooldown(session, sent):
    s, account = _account(session, enabled=False)
    start = cloud.now() - timedelta(hours=6)
    _refused(session, s, account, start)
    _finish(session, s, account, start + timedelta(hours=2),
            status="ok", exit_code=0, downloaded=5)  # fmt: skip
    assert tick.apple_refusals(session, account.id) == []
    assert tick.apple_retry_at(session, account) is None
    assert not tick.due(session, account, cloud.now())  # schedule off: done


def test_another_failure_is_not_taken_for_a_refusal(session, sent):
    s, account = _account(session, enabled=False)
    run = _finish(session, s, account, cloud.now(), status="failed", exit_code=1,
                  reason="tool_failed", detail="Traceback ...",
                  message="icloudpd exited with status 1")  # fmt: skip
    assert cloud.parse_json(run.result)["reason"] == "tool_failed"
    assert views.account_dict(session, account)["status"] == "failed"
    assert not tick.due(session, account, cloud.now() + timedelta(days=1))


def test_a_good_exit_cut_off_by_apple_is_a_refusal(session, sent):
    """icloudpd logged Apple's refusal and exited 0 (nas, 2026-11-06): the
    full pass must carry on after the cooldown, not count as the week's."""
    s, account = _account(session, enabled=True)
    ended = cloud.now() - timedelta(minutes=10)
    run = _finish(session, s, account, ended, status="ok", exit_code=0,
                  reason="some_failed", detail=REFUSED, downloaded=16445,
                  message="148 file(s) could not be downloaded")  # fmt: skip
    assert run.status == cloud.FAILED
    assert cloud.parse_json(run.result)["reason"] == tick.APPLE_BUSY
    assert run.downloaded == 16445
    assert account.last_full_at is None
    assert tick.apple_retry_at(session, account) == ended + timedelta(hours=1)
    assert tick.transfer_action(account, cloud.now()) == cloud.RECONCILE


def test_the_refusal_text_in_a_connect_is_left_alone(session, sent):
    s, account = _account(session, enabled=True)
    run = cloud.queue_account_run(session, account, cloud.CONNECT, "ops")
    results.record_result(session, s.nas.id, {
        "run_id": str(run.id), "status": "ok", "exit_code": 0, "detail": REFUSED,
    })  # fmt: skip
    assert run.status == cloud.OK


def test_a_lost_connection_to_icloud_carries_on_after_the_cooldown(session, sent):
    """Production, 2026-11-06 13:52 UTC: the reconcile reached June 2015, logged
    "Cannot connect to Apple iCloud service" and exited 0 -- recorded as the
    full pass at 17,567 of about 32,000 photos."""
    s, account = _account(session, enabled=True)
    ended = cloud.now() - timedelta(minutes=10)
    lost = "2026-11-06 13:52:01 INFO     Cannot connect to Apple iCloud service"
    run = _finish(session, s, account, ended, status="ok", exit_code=0,
                  detail=lost, downloaded=1122)  # fmt: skip
    assert run.status == cloud.FAILED
    assert cloud.parse_json(run.result)["reason"] == tick.APPLE_BUSY
    assert account.last_full_at is None
    assert tick.transfer_action(account, cloud.now()) == cloud.RECONCILE
