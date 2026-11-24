# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A refused host configure still teaches the server what the host's restate
can do (air-gap lab, 2026-11-24).  A restate-proxy target's settings go to a
host only once it is known to read through the proxy, and that was learned
only from an ACCEPTED configure -- so on a site with no NFS the host's first
(NFS) configure was refused, forever."""

from unittest.mock import patch

from backend.services import backup_jobs as jobs
from backend.services import backup_proxy as proxy
from backend.services import backup_results as results
from tests.services.test_backup_results import (
    _setup,
    sent,
)  # noqa: F401  pylint: disable=unused-import


def _proxy_target(s):
    s.target.transport = proxy.PROXY
    s.target.proxy_host = "ag-storage"
    s.target.proxy_port = 8443


def test_a_refusal_that_reports_proxy_abilities_resends_through_the_proxy(
    session, sent
):  # noqa: F811  pylint: disable=redefined-outer-name
    s = _setup(session)
    _proxy_target(s)
    session.commit()
    first = jobs.queue_configure(session, s.policy, s.target, s.host, "host")
    assert "proxy" not in sent[-1][2]["target"]  # nothing known yet: NFS
    version = s.policy.config_version
    with patch.object(results.host_reply.backup_tick, "configure_now") as now:
        results.record_command_result(session, {
            "command_id": first.command_id, "success": False,
            "error": "mount_point is not an NFS mount on this host",
            "result": {"reason": "invalid_policy", "restate_version": "3.4.0.1",
                       "abilities": [proxy.REMOTE_ABILITY, proxy.REMOTE_CAPTURE]}})  # fmt: skip
    assert first.status == "failed"
    assert proxy.REMOTE_ABILITY in proxy.abilities(s.policy)
    assert s.policy.config_version == version + 1 and now.called
    jobs.queue_configure(session, s.policy, s.target, s.host, "host")
    assert "proxy" in sent[-1][2]["target"]


def test_a_refusal_without_abilities_changes_nothing(
    session, sent
):  # noqa: F811  pylint: disable=redefined-outer-name
    s = _setup(session)
    run = jobs.queue_configure(session, s.policy, s.target, s.host, "host")
    version = s.policy.config_version
    results.record_command_result(
        session, {"command_id": run.command_id, "success": False, "error": "busy"}
    )
    assert s.policy.config_version == version


def test_a_storage_audit_with_the_proxy_down_resends_its_configure(
    session, sent
):  # noqa: F811  pylint: disable=redefined-outer-name
    """Air-gap lab, 2026-11-24: the operator made the missing backup account,
    but nothing re-sent the storage configure that would start the proxy, and
    saving the policy was refused while the proxy could not be reached."""
    s = _setup(session)
    version = s.policy.config_version
    down = [{"code": "proxy_running", "level": "error", "params": {}}]
    with patch.object(results.host_reply.backup_tick, "configure_now") as now:
        assert proxy.resend_if_down(session, s.policy, down)
        assert s.policy.config_version == version + 1 and now.called
        up = [{"code": "proxy_running", "level": "ok", "params": {}}]
        assert not proxy.resend_if_down(session, s.policy, up)
        assert not proxy.resend_if_down(session, s.policy, None)
    assert s.policy.config_version == version + 1
