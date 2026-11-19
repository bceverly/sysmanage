# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The site's backup status snapshot from the REAL Backups overview
(Phase 27.1): one host backed up, one waiting for its first backup.  Keeps
the snapshot honest if the overview's shape changes."""

import json
from datetime import timedelta

from backend.services import federation_site_backup_rollup as site_backup
from tests.services.test_backup_results import _host, _setup
from tests.services.test_backup_tick import NOW, _finish


def test_snapshot_from_the_real_overview(session):
    s = _setup(session)
    s.policy.repository_bytes = 4096
    _finish(session, s.policy, s.host.id, "capture", "ok", at=NOW - timedelta(hours=2))
    late = _host(session, fqdn="late.lab")
    late_policy = type(s.policy)(
        host_id=late.id,
        target_id=s.target.id,
        enabled=True,
        interval_hours=24,
        keep_last=14,
        check_interval_days=7,
        quiesce=False,
        config_version=1,
        host_acked_version=1,
        storage_acked_version=1,
        created_at=s.policy.created_at,
        updated_at=s.policy.updated_at,
    )
    session.add(late_policy)
    session.commit()

    body = site_backup.collect_backup_rollup(session)

    assert body["configured"] is True
    assert body["hosts_with_policy"] == 2
    assert body["never_backed_up"] == 1
    assert body["repository_bytes"] == 4096
    assert body["oldest_last_good_at"].startswith(
        (NOW - timedelta(hours=2)).isoformat()[:16]
    )
    assert sum(body["status_counts"].values()) == 2
    # Status only: the target's paths stay on the site.
    text = json.dumps(body)
    assert "/srv/backups" not in text
    assert "/mnt/backups" not in text
