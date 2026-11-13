# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The SysManage server backs itself up (ROADMAP 25.9, Community).

Production's server had no backup at all on 2026-11-02.  Its policy is the
server host's own, marked: preset to the CA, the config, OpenBAO and
PostgreSQL; the databases always paused; OpenBAO's init material and token
never in the backup, whatever the path rules say.
"""

# pylint: disable=redefined-outer-name

import json
import uuid
from unittest.mock import patch

import pytest

from backend.api import backups as api
from backend.api import backups_server as server_api
from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_host_reply as host_reply
from backend.services import backup_server
from backend.services import backup_server_paths as paths
from backend.services import backup_views as views
from tests.services.test_backup_results import _host, _setup
from tests.test_backups_api import (  # noqa: F401  # pylint: disable=unused-import
    MANAGER,
    NOBODY,
    _status,
    sent,
)

SERVER = "sysmanage.example.com"


@pytest.fixture
def named():
    """This machine is called SERVER."""
    with patch.object(backup_server.socket, "getfqdn", return_value=SERVER), patch.object(
        backup_server.socket, "gethostname", return_value="sysmanage"
    ):  # fmt: skip
        yield


def _server(session):
    s = _setup(session)
    s.server = _host(session, fqdn=SERVER)
    return s


def _body(host, **extra):
    return server_api.ServerPolicyBody(host_id=str(host.id), **extra)


def test_the_preset_keeps_what_is_lost_with_the_server_and_never_the_unseal_key():
    found = paths.preset(["/var/mirror"])
    assert found["quiesce"] is True
    for kept in ("/etc/sysmanage/certs", "/var/lib/openbao", "/var/lib/postgresql",
                 "/var/lib/sysmanage", "/etc/letsencrypt", "/etc/sysmanage/tls"):  # fmt: skip
        assert kept in found["keep_paths"]
    for left_out in ("/var/lib/sysmanage/modules", "/var/log/sysmanage", "/var/mirror"):
        assert left_out in found["skip_paths"]
    assert {"/var/lib/openbao/init.json", "/etc/sysmanage/openbao-token"} <= set(
        found["never_paths"]
    )


def test_a_path_is_matched_literally():
    with patch.object(
        paths.config, "get_vault_config", return_value={"token_file": "/etc/a*b?"}
    ):
        assert "/etc/a\\*b\\?" in paths.never_paths()


def test_the_server_policy_always_leaves_the_secrets_out_and_pauses(session):
    s = _setup(session)
    s.policy.server_preset = True
    s.policy.quiesce = False
    s.policy.keep_paths = json.dumps(["/var/lib/openbao/init.json"])
    s.policy.skip_paths = json.dumps(["/etc/sysmanage/openbao-token", "/tmp/x"])
    capture = jobs.host_configuration(s.policy, s.target, s.host)["jobs"]["capture"]
    assert capture["quiesce"] is True
    never = paths.never_paths()
    # Last, once each: restate's last matching rule wins over the keep rule.
    assert capture["skip_paths"] == ["/tmp/x"] + never
    assert capture["quiesce_with"] == []
    s.policy.available_hooks = json.dumps(["postgresql", "openbao"])
    capture = jobs.host_configuration(s.policy, s.target, s.host)["jobs"]["capture"]
    assert capture["quiesce_with"] == ["openbao"]


def _capture(s):
    return jobs.host_configuration(s.policy, s.target, s.host)["jobs"]["capture"]


def test_the_server_keeps_postgresql_running_once_its_agent_takes_hook_options(session):
    """restate 3.0.0.0: one consistent dump while the database runs, nothing
    stopped; OpenBAO's file storage, copied stopped, is unsealed again by the
    packaged unit.  An agent that does not report the ability gets neither."""
    s = _setup(session)
    s.policy.server_preset = True
    assert "hook_option" not in _capture(s)
    s.policy.host_abilities = json.dumps(["hook_option"])
    assert _capture(s)["hook_option"] == ["postgresql.stop=never"]
    s.policy.available_hooks = json.dumps(["openbao", "postgresql"])
    vault = {"url": "http://127.0.0.1:8200/"}
    with patch.object(paths.config, "get_vault_config", return_value=vault):
        assert _capture(s)["hook_option"] == [
            "postgresql.stop=never",
            "openbao.unseal_unit=sysmanage-openbao-init",
            # The hook's default is HTTPS; a packaged OpenBAO is plain HTTP.
            "openbao.address=http://127.0.0.1:8200",
        ]
    # Only this host's own OpenBAO is ever named.
    vault = {"url": "https://vault.example.com:8200"}
    with patch.object(paths.config, "get_vault_config", return_value=vault):
        assert _capture(s)["hook_option"] == [
            "postgresql.stop=never",
            "openbao.unseal_unit=sysmanage-openbao-init",
        ]


def test_an_ordinary_policy_gets_no_hook_options(session):
    s = _setup(session)
    s.policy.host_abilities = json.dumps(["hook_option"])
    s.policy.available_hooks = json.dumps(["openbao", "postgresql"])
    assert "hook_option" not in _capture(s)


def test_a_reply_that_changes_the_servers_capture_re_sends_it(session):
    """The first configure cannot know the agent's abilities or the hooks its
    restate finds: when they change the server's capture job, it goes again."""
    s = _setup(session)
    s.policy.server_preset = True
    version = s.policy.config_version
    with patch.object(host_reply.backup_tick, "configure_now") as now:
        host_reply.store(session, s.policy, {"hooks": [], "abilities": []})
        assert s.policy.config_version == version and not now.called
        host_reply.store(
            session, s.policy, {"hooks": ["openbao"], "abilities": ["hook_option"]}
        )
        assert s.policy.config_version == version + 1 and now.called
        now.reset_mock()
        host_reply.store(
            session, s.policy, {"hooks": ["openbao"], "abilities": ["hook_option"]}
        )
        assert s.policy.config_version == version + 1 and not now.called


def test_an_ordinary_policys_reply_is_only_stored(session):
    s = _setup(session)
    version = s.policy.config_version
    with patch.object(host_reply.backup_tick, "configure_now") as now:
        host_reply.store(
            session, s.policy, {"hooks": ["openbao"], "abilities": ["hook_option"]}
        )
    assert s.policy.config_version == version and not now.called
    assert json.loads(s.policy.host_abilities) == ["hook_option"]


def test_an_ordinary_policy_is_left_as_it_is(session):
    s = _setup(session)
    s.policy.available_hooks = json.dumps(["openbao"])
    capture = jobs.host_configuration(s.policy, s.target, s.host)["jobs"]["capture"]
    assert capture["quiesce"] is False and capture["quiesce_with"] == []
    assert "skip_paths" not in capture


def test_the_server_host_is_found_by_name_and_warned_on_until_backed_up(session, named):
    s = _server(session)
    found = backup_server.status(session, views.overview(session)["hosts"])
    assert found["status"] == "no_policy" and found["warn"]
    assert found["host_id"] == str(s.server.id)
    data = views.overview(session)
    assert views.attention_count(data) == 1  # the server, counted once


def test_a_short_name_matches_when_no_full_name_does(session):
    _setup(session)
    host = _host(session, fqdn="sysmanage.other.lan")
    with patch.object(backup_server.socket, "getfqdn", return_value="sysmanage"), \
            patch.object(backup_server.socket, "gethostname", return_value="sysmanage"):  # fmt: skip
        assert [h.id for h in backup_server.candidates(session)] == [host.id]


def test_no_match_warns_only_without_multitenancy(session, named):
    _setup(session)
    rows = views.overview(session)["hosts"]
    assert backup_server.status(session, rows)["warn"] is True
    with patch.object(backup_server.config, "get_multitenancy_config",
                      return_value={"enabled": True}):  # fmt: skip
        assert backup_server.status(session, rows)["warn"] is False


@pytest.mark.asyncio
async def test_the_server_policy_needs_the_role_and_is_marked_and_paused(
    session, named, sent
):
    s = _server(session)
    assert (
        await _status(server_api.put_server_policy(_body(s.server), session, NOBODY))
        == 403
    )
    saved = await server_api.put_server_policy(
        _body(s.server, quiesce=False), session, MANAGER
    )
    assert saved["server_preset"] is True and saved["quiesce"] is True
    found = await server_api.server_backup(None, session)
    assert found["status"] == "no_good_backup" and found["warn"]
    # An ordinary Configure is refused there: the server dialog changes it.
    assert (
        await _status(
            api.put_policy(str(s.server.id), api.PolicyBody(), session, MANAGER)
        )
        == 409
    )
    assert backup_server.marked(session).host_id == s.server.id


@pytest.mark.asyncio
async def test_the_servers_host_is_never_configured_as_an_ordinary_host(
    session, named, sent
):
    """Production, 2026-11-12: Configure on the server's host made a plain
    policy that stopped PostgreSQL.  Found by name, it is refused before
    anything is marked; another host is not."""
    s = _server(session)
    assert backup_server.server_host_id(session) == str(s.server.id)
    assert (
        await _status(
            api.put_policy(str(s.server.id), api.PolicyBody(), session, MANAGER)
        )
        == 409
    )
    assert (
        session.query(models.BackupPolicy).filter_by(host_id=s.server.id).count() == 0
    )
    await api.put_policy(str(s.host.id), api.PolicyBody(), session, MANAGER)
    row = views.host_status(session, s.host)
    assert row["server_host"] is False and row["needs_server_policy"] is False


@pytest.mark.asyncio
async def test_an_ordinary_policy_already_on_the_servers_host_is_flagged(
    session, named, sent
):
    s = _server(session)
    session.add(models.BackupPolicy(host_id=s.server.id, target_id=s.target.id,
                                    config_version=1, host_acked_version=0,
                                    storage_acked_version=0, created_at=jobs.now(),
                                    updated_at=jobs.now()))  # fmt: skip
    session.commit()
    overview = views.overview(session)
    row = next(r for r in overview["hosts"] if r["host_id"] == str(s.server.id))
    assert row["server_host"] and row["needs_server_policy"]
    assert (
        overview["server"]["status"] == "ordinary_policy" and overview["server"]["warn"]
    )
    # The server dialog makes it the server's policy, and the flag goes.
    await server_api.put_server_policy(_body(s.server), session, MANAGER)
    row = views.host_status(session, s.server)
    assert row["server_host"] and not row["needs_server_policy"]


def test_a_tag_policy_never_takes_the_servers_host(session, named):
    from backend.services import backup_tag_policies  # noqa: PLC0415

    s = _server(session)
    with patch.object(backup_tag_policies.jobs, "equipped", return_value=(True, None)):
        assert backup_tag_policies._skip_reason(session, s.server) == "sysmanage_server"
        assert backup_tag_policies._skip_reason(session, s.host) in ("", "unreachable")


@pytest.mark.asyncio
async def test_a_good_capture_clears_the_warning(session, named, sent):
    s = _server(session)
    await server_api.put_server_policy(_body(s.server), session, MANAGER)
    policy = backup_server.marked(session)
    session.add(models.BackupRun(id=uuid.uuid4(), policy_id=policy.id, host_id=s.server.id,
                                 action="capture", status="ok", queued_at=jobs.now(),
                                 finished_at=jobs.now()))  # fmt: skip
    session.commit()
    found = await server_api.server_backup(None, session)
    assert found["status"] == "ok" and not found["warn"]
    assert views.attention_count(views.overview(session)) == 0


@pytest.mark.asyncio
async def test_marking_another_host_moves_the_mark_and_says_so(session, named, sent):
    s = _server(session)
    await server_api.put_server_policy(_body(s.host), session, MANAGER)
    await server_api.put_server_policy(_body(s.server), session, MANAGER)
    marked = session.query(models.BackupPolicy).filter_by(server_preset=True).all()
    assert [p.host_id for p in marked] == [s.server.id]
    audit = session.query(models.AuditLog).all()
    assert any("moved to this host" in a.description for a in audit)


@pytest.mark.asyncio
async def test_the_summary_says_the_server_is_unprotected(session, named):
    _server(session)
    assert (await api.backups_summary(session))["server_unprotected"] is True


@pytest.mark.asyncio
async def test_the_preset_for_a_picked_host_leaves_its_mirror_out(session):
    s = _setup(session)
    session.add(models.MirrorPlatformConfig(id=uuid.uuid4(), platform="linux",
                                            host_id=s.host.id, mirror_root_path="/srv/mirror"))  # fmt: skip
    session.commit()
    found = await server_api.server_backup(str(s.host.id), session)
    assert "/srv/mirror" in found["preset"]["skip_paths"]
    assert await _status(server_api.server_backup(str(uuid.uuid4()), session)) == 404
