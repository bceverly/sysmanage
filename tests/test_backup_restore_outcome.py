# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A restore's outcome from restate after 2.2.0.14: an include that matched
nothing, or a restore hook that failed, ends it with exit 3, which is
Incomplete (never Succeeded), for the restore and its preview alike; its
``resolved``, ``unmatched`` and ``hooks`` reach the run's view whole."""

from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_results as results
from backend.services import backup_views as views
from tests.services.test_backup_results import (  # noqa: F401  pylint: disable=unused-import
    _result,
    _setup,
    sent,
)

RESTORE = {
    "from": "repo::snap1",
    "root": "/",
    "resolved": [{"include": "/var/snap/nextcloud/current/nextcloud/config",
                  "path": "/var/snap/nextcloud/54589/nextcloud/config",
                  "through": ["/var/snap/nextcloud/current"]}],  # fmt: skip
    "unmatched": ["/etc/nothing-here"],
    "hooks": [{"dump_dir": "/var/lib/restate/dumps/nextcloud-nextcloud",
               "kind": "nextcloud", "name": "nextcloud", "status": "failed"}],  # fmt: skip
}


def _restore(session, s, dry_run):
    return jobs.queue_restore(
        session, s.policy, s.host, "snap1", ["/etc"], dry_run, True, "ops"
    )


def test_an_incomplete_restore_is_incomplete_and_keeps_what_restate_said(session, sent):
    s = _setup(session)
    for dry_run in (True, False):
        run = _restore(session, s, dry_run)
        results.record_result(
            session, s.host.id, _result(run, "incomplete", restore=RESTORE)
        )
        assert (run.status, run.exit_code) == ("incomplete", 3)
        shown = views.run_dict(run)
        assert shown["status"] == "incomplete"
        assert shown["result"]["restore"] == RESTORE
    # A restore queues nothing after it (no prune, no seal).
    assert {r.action for r in session.query(models.BackupRun).all()} == {"restore"}


def test_an_exit_3_with_an_unknown_status_word_is_never_succeeded(session, sent):
    s = _setup(session)
    run = _restore(session, s, False)
    payload = _result(run, "incomplete", restore=RESTORE)
    payload["status"] = "something-new"
    results.record_result(session, s.host.id, payload)
    assert (run.status, run.exit_code) == ("failed", 3)
