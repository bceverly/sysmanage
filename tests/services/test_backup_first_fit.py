# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Will a host's first backup fit? (ROADMAP 24.8): estimate first, hold a
scheduled first backup that would not fit, never hold one that does or a
host whose estimate failed, and say so on the dashboard."""

import json
from datetime import timedelta

from backend.services import backup_first_fit as first_fit
from backend.services import backup_results as results
from backend.services import backup_tick as tick
from backend.services import backup_views as views
from tests.services.test_backup_storage_health import GB, _disk
from tests.services.test_backup_tick import NOW, _actions, _finish
from tests.services.test_backup_tick import (  # noqa: F401  # pylint: disable=unused-import
    no_spread,
    sent,
)
from tests.services.test_backup_results import _setup


def _estimated(session, s, gb, at=NOW, status="ok", dirs=None):
    s.policy.estimate_bytes = gb * GB
    s.policy.estimate_dirs = json.dumps(dirs or [])
    _finish(session, s.policy, s.host.id, "estimate", status, at=at)
    session.commit()


def test_the_largest_directories_come_first_and_junk_is_dropped():
    found = first_fit.largest_dirs(
        {"/etc": 10, "/home/u": 900, "/var/lib": 50, 7: 1, "/bad": "x", "/neg": -1}
    )
    assert [d["path"] for d in found] == ["/home/u", "/var/lib", "/etc"]
    assert first_fit.largest_dirs(None) == []


def test_an_estimate_result_stores_its_size_and_largest_directories(session):
    s = _setup(session)
    run = _finish(session, s.policy, s.host.id, "estimate", "ok")
    results._after_estimate(  # pylint: disable=protected-access
        session,
        run,
        s.policy,
        {"bytes": 5 * GB, "by_dir": {"/home/u": 4 * GB, "/etc": 1}},
    )
    assert s.policy.estimate_bytes == 5 * GB
    assert json.loads(s.policy.estimate_dirs)[0] == {"path": "/home/u", "bytes": 4 * GB}


def test_a_first_backup_that_does_not_fit_is_held(session, sent):
    s = _setup(session)
    _disk(session, s.nas, "/srv/backups", 100, 10)
    _estimated(session, s, 40, dirs=[{"path": "/home/u", "bytes": 38 * GB}])
    tick.reconcile(session, NOW + timedelta(minutes=5))
    assert ("backup_run", "capture") not in _actions(sent)
    row = views.host_status(session, s.host, NOW)
    assert row["first_fit"]["fits"] is False
    assert row["first_fit"]["available_bytes"] == 10 * GB
    assert row["first_fit"]["largest"][0]["path"] == "/home/u"
    assert views.attention_count(views.overview(session)) == 1


def test_a_first_backup_that_fits_goes_ahead(session, sent):
    s = _setup(session)
    _disk(session, s.nas, "/srv/backups", 100, 90)
    _estimated(session, s, 40)
    tick.reconcile(session, NOW + timedelta(minutes=5))
    assert ("backup_run", "capture") in _actions(sent)


def test_a_failed_estimate_does_not_stop_backups(session, sent):
    s = _setup(session)
    _disk(session, s.nas, "/srv/backups", 100, 1)
    _finish(session, s.policy, s.host.id, "estimate", "failed", at=NOW)
    session.commit()
    tick.reconcile(session, NOW + timedelta(minutes=5))
    assert ("backup_run", "capture") in _actions(sent)


def test_a_stale_estimate_is_run_again(session, sent):
    s = _setup(session)
    _estimated(session, s, 1, at=NOW - first_fit.ESTIMATE_FRESH - timedelta(hours=1))
    tick.reconcile(session, NOW)
    assert ("backup_run", "estimate") in _actions(sent)


def test_after_a_good_backup_the_check_is_over(session):
    s = _setup(session)
    _disk(session, s.nas, "/srv/backups", 100, 1)
    _estimated(session, s, 40)
    _finish(session, s.policy, s.host.id, "capture", "ok", at=NOW)
    session.commit()
    assert first_fit.fit(session, s.policy, s.target) is None
    assert (
        first_fit.first_capture_decision(session, s.policy, s.target, NOW)
        == first_fit.GO
    )


def test_back_up_now_is_never_held(session, sent):
    s = _setup(session)
    _disk(session, s.nas, "/srv/backups", 100, 10)
    _estimated(session, s, 40)
    s.policy.capture_requested_at = NOW
    session.commit()
    tick.start_requested(session)
    assert ("backup_run", "capture") in _actions(sent)
