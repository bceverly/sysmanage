# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""restate-proxy: how hosts reach a target's storage (ROADMAP 25.5).

A target on the proxy tells each host where to read its repository over
HTTPS once the host's restate can; each host makes its own tokens and the
server keeps only their hashes; the storage host is sent the grants that name
them and every client the target has, so a grant never outlives its host.
"""

# pylint: disable=redefined-outer-name

import json

import pytest

from backend.api import backups_transport as transport_api
from backend.persistence import models
from backend.services import backup_host_reply as host_reply
from backend.services import backup_jobs as jobs
from backend.services import backup_proxy as proxy
from backend.services import backup_tick as tick
from backend.services import backup_views as views
from tests.services.test_backup_results import _host, _setup
from tests.test_backups_api import (  # noqa: F401  # pylint: disable=unused-import
    MANAGER,
    NOBODY,
    _status,
    sent,
)

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_P = "c" * 64


def _body(**extra):
    values = {"transport": "proxy", "proxy_host": "nas.example.lan"}
    values.update(extra)
    return transport_api.TransportBody(**values)


def _on_proxy(session, abilities=("list", proxy.REMOTE_ABILITY)):
    s = _setup(session)
    s.target.transport = proxy.PROXY
    s.target.proxy_host = "nas.example.lan"
    s.target.proxy_port = 8443
    s.policy.host_abilities = json.dumps(list(abilities))
    session.commit()
    return s


def test_settings_are_checked():
    good = proxy.check_settings("proxy", "NAS.Example.lan", None, None, None)
    assert good["proxy_host"] == "nas.example.lan" and good["proxy_port"] == 8443
    assert (
        proxy.check_settings("proxy", "[::1]", 9443, None, None)["proxy_host"] == "::1"
    )
    for bad in (
        ("ftp", "nas", None, None, None),
        ("proxy", "nas/evil", None, None, None),
        ("proxy", "nas", 70000, None, None),
        ("proxy", "nas", None, "not-hex", None),
        ("proxy", "nas", None, None, "-----BEGIN PRIVATE KEY-----"),
    ):
        with pytest.raises(proxy.ProxySettingsRefused):
            proxy.check_settings(*bad)
    nfs = proxy.check_settings("nfs", "nas", 8443, HASH_A, None)
    assert nfs == {"transport": "nfs", "proxy_host": None, "proxy_port": None,
                   "proxy_pin_sha256": None, "proxy_ca_pem": None}  # fmt: skip


@pytest.mark.asyncio
async def test_the_transport_needs_the_role_and_resends_every_job(session, sent):
    s = _setup(session)
    target_id = str(s.target.id)
    assert (
        await _status(transport_api.set_transport(target_id, _body(), session, NOBODY))
        == 403
    )
    assert (
        await _status(
            transport_api.set_transport(
                target_id, _body(proxy_port=0), session, MANAGER
            )
        )
        == 422
    )
    before = s.policy.config_version
    view = await transport_api.set_transport(target_id, _body(), session, MANAGER)
    assert view["transport"] == {
        "transport": "proxy", "proxy_host": "nas.example.lan", "proxy_port": 8443,
        "proxy_pin_sha256": None, "proxy_ca": False,
        "url": "https://nas.example.lan:8443",
        "certificate": None,  # until the storage host asks for one
    }  # fmt: skip
    session.refresh(s.policy)
    assert s.policy.config_version > before
    assert json.loads(s.target.proxy_clients) == [str(s.host.id)]


def test_a_host_reads_through_the_proxy_only_once_its_restate_can(session):
    s = _on_proxy(session, abilities=("list",))
    assert "proxy" not in jobs.host_configuration(s.policy, s.target, s.host)["target"]
    s.policy.host_abilities = json.dumps([proxy.REMOTE_ABILITY])
    target = jobs.host_configuration(s.policy, s.target, s.host)["target"]
    assert target["proxy"] == {"url": f"https://nas.example.lan:8443/v1/{s.host.id}"}
    # Captures stay on NFS: the mount is still there.
    assert target["mount_point"] == "/mnt/backups"


def test_the_previous_repository_has_a_url_and_a_pin_travels(session):
    s = _on_proxy(session)
    s.policy.previous_repository_dir = "web-old"
    s.target.proxy_pin_sha256 = HASH_A
    got = jobs.host_configuration(s.policy, s.target, s.host)["target"]["proxy"]
    assert got["previous_url"] == got["url"] + ".previous"
    assert got["pin_sha256"] == HASH_A


def test_an_nfs_target_sends_no_proxy_to_a_host(session):
    s = _setup(session)
    s.policy.host_abilities = json.dumps([proxy.REMOTE_ABILITY])
    assert "proxy" not in jobs.host_configuration(s.policy, s.target, s.host)["target"]


def test_the_server_keeps_only_the_hosts_token_hashes(session):
    s = _on_proxy(session)
    host_reply.store(session, s.policy, {"proxy_tokens": {"current": HASH_A}})
    assert s.policy.proxy_token_sha256 == HASH_A
    # A new token: the old one stays granted until the host reports the new
    # one again, so a job started with it still finishes.
    host_reply.store(session, s.policy, {"proxy_tokens": {"current": HASH_B}})
    assert (s.policy.proxy_token_sha256, s.policy.proxy_token_sha256_old) == (
        HASH_B, HASH_A
    )  # fmt: skip
    host_reply.store(session, s.policy, {"proxy_tokens": {"current": HASH_B}})
    assert s.policy.proxy_token_sha256_old is None
    # Anything that is not a SHA-256 is no token hash.
    host_reply.store(session, s.policy, {"proxy_tokens": {"current": "rsp_secret"}})
    assert s.policy.proxy_token_sha256 is None


def test_a_new_token_resends_the_grants(session):
    s = _on_proxy(session)
    before = s.policy.config_version
    host_reply.store(session, s.policy, {"proxy_tokens": {"current": HASH_A}})
    assert s.policy.config_version > before
    settled = s.policy.config_version
    host_reply.store(session, s.policy, {"proxy_tokens": {"current": HASH_A}})
    assert s.policy.config_version == settled


def test_the_storage_host_gets_the_grants_and_every_client(session, sent):
    s = _on_proxy(session)
    s.policy.proxy_token_sha256 = HASH_A
    s.policy.proxy_token_sha256_old = HASH_B
    s.policy.previous_repository_dir = "web-old"
    s.policy.proxy_previous_token_sha256 = HASH_P
    jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    got = sent[-1][2]["target"]["proxy"]
    client = str(s.host.id)
    assert got["target_id"] == str(s.target.id) and got["enabled"] is True
    assert got["clients"] == sorted([client, client + ".previous"])
    assert got["grants"] == [
        {"client": client, "token_sha256": [HASH_A, HASH_B],
         "operations": ["append", "read"]},
        {"client": client + ".previous", "token_sha256": [HASH_P],
         "operations": ["read"], "repo_dir": "web-old"},
    ]  # fmt: skip


def test_back_on_nfs_the_storage_host_is_told_to_drop_every_grant(session, sent):
    s = _setup(session)
    s.policy.proxy_token_sha256 = HASH_A
    jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    assert sent[-1][2]["target"]["proxy"] == {
        "target_id": str(s.target.id), "enabled": False, "grants": [], "clients": []
    }  # fmt: skip


def test_no_grant_before_the_host_has_made_its_token(session, sent):
    s = _on_proxy(session)
    jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    assert sent[-1][2]["target"]["proxy"]["grants"] == []


def test_a_deleted_host_loses_its_grant_on_the_next_tick(session):
    s = _on_proxy(session)
    other = _host(session, fqdn="db.lab")
    second = models.BackupPolicy(
        host_id=other.id, target_id=s.target.id, enabled=True, interval_hours=24,
        keep_last=14, check_interval_days=7, quiesce=False, config_version=1,
        host_acked_version=1, storage_acked_version=1,
        created_at=jobs.now(), updated_at=jobs.now(),
    )  # fmt: skip
    session.add(second)
    session.commit()
    assert proxy.sync_clients(session, s.target) is True
    assert proxy.sync_clients(session, s.target) is False  # nothing changed
    version = s.policy.config_version
    session.delete(other)  # the host goes, and its policy with it
    session.commit()
    tick.reconcile(session)
    session.refresh(s.policy)
    assert json.loads(s.target.proxy_clients) == [str(s.host.id)]
    assert s.policy.config_version > version


def test_the_proxy_findings_are_target_wide_or_per_host():
    from backend.services import backup_storage_audit as audit  # noqa: PLC0415

    assert "proxy_running" in audit.HOST_WIDE
    assert "proxy_certificate" in audit.HOST_WIDE
    assert "proxy_grants" not in audit.HOST_WIDE


def test_the_backups_page_shows_the_transport(session):
    s = _on_proxy(session)
    shown = views.target_dict(s.target, session)["transport"]
    assert (
        shown["transport"] == "proxy" and shown["url"] == "https://nas.example.lan:8443"
    )


@pytest.mark.asyncio
async def test_a_saved_ca_is_kept_unless_removed(session, sent):
    from tests.test_backup_proxy_ca import ca_pem  # noqa: PLC0415

    s = _setup(session)
    target_id = str(s.target.id)
    await transport_api.set_transport(
        target_id, _body(proxy_ca_pem=ca_pem()), session, MANAGER
    )
    saved = s.target.proxy_ca_pem
    assert saved.startswith("-----BEGIN CERTIFICATE-----")
    view = await transport_api.set_transport(
        target_id, _body(proxy_port=9443), session, MANAGER
    )
    assert s.target.proxy_ca_pem == saved and view["transport"]["proxy_ca"] is True
    await transport_api.set_transport(
        target_id, _body(remove_proxy_ca=True), session, MANAGER
    )
    assert s.target.proxy_ca_pem is None
