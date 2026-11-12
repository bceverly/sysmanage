# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Backing up through restate-proxy (ROADMAP 25.5, restate 3.2.0.0).

Once a host's restate captures through a proxy, the host backs up that way
with no NFS mount, and its storage host needs no export for it (its prepare
makes the repository).  Hosts with no NFSv4 client -- OpenBSD, NetBSD -- back
up only that way.  What a host must reach is then the proxy: its port and a
certificate the host trusts, not NFS's port 2049, and NAT does not apply.
"""

# pylint: disable=redefined-outer-name

import json

from backend.services import backup_jobs as jobs
from backend.services import backup_proxy as proxy
from backend.services import backup_reach as reach
from tests.services.test_backup_results import (  # noqa: F401  # pylint: disable=unused-import
    _setup,
    sent,
)

HASH = "a" * 64
CAN_CHECK = json.dumps({"capabilities": ["backup", "backup_reach"], "commands": []})
CAPTURES = ("list", proxy.REMOTE_ABILITY, proxy.REMOTE_CAPTURE)


def _on_proxy(session, abilities=CAPTURES):
    s = _setup(session)
    s.target.transport = proxy.PROXY
    s.target.proxy_host = "nas.example.lan"
    s.target.proxy_port = 8443
    s.policy.host_abilities = json.dumps(list(abilities))
    s.policy.proxy_token_sha256 = HASH
    s.host.agent_capabilities = CAN_CHECK
    session.commit()
    return s


def test_a_host_whose_restate_captures_through_a_proxy_is_told_to(session):
    s = _on_proxy(session)
    got = jobs.host_configuration(s.policy, s.target, s.host)["target"]["proxy"]
    assert got["capture"] is True


def test_a_host_that_only_reads_through_it_still_captures_over_nfs(session):
    s = _on_proxy(session, abilities=["list", proxy.REMOTE_ABILITY])
    got = jobs.host_configuration(s.policy, s.target, s.host)["target"]["proxy"]
    assert "capture" not in got


def test_its_storage_host_is_told_it_needs_no_export(session, sent):
    s = _on_proxy(session)
    jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    assert sent[-1][2]["target"]["proxy"]["export"] is False


def test_an_nfs_host_keeps_its_export_and_sends_no_export_key(session, sent):
    # An older storage agent takes no ``export`` key; an NFS host needs none.
    s = _on_proxy(session, abilities=["list", proxy.REMOTE_ABILITY])
    jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    assert "export" not in sent[-1][2]["target"]["proxy"]


def test_openbsd_and_netbsd_back_up_only_on_a_proxy_target(session):
    s = _setup(session)
    s.host.agent_capabilities = CAN_CHECK
    for platform in ("OpenBSD", "NetBSD"):
        s.host.platform = platform
        session.commit()
        assert jobs.equipped(s.host) == (False, jobs.NO_NFSV4_CLIENT)
    s.target.transport = proxy.PROXY
    s.target.proxy_host = "nas.example.lan"
    session.commit()
    assert jobs.equipped(s.host) == (True, None)
    s.host.platform = "Linux"  # every other host as before
    s.target.transport = proxy.NFS
    session.commit()
    assert jobs.equipped(s.host) == (True, None)


def test_the_reach_check_asks_for_the_proxy_and_never_holds(session, sent):
    s = _on_proxy(session)
    s.target.proxy_pin_sha256 = HASH
    session.commit()
    reach.start(session, s.host, force=True)
    assert sent[-1][1:] == ("check_backup_storage", {
        "address": "nas.example.lan",
        "proxy": {"port": 8443, "pin_sha256": HASH},
    })  # fmt: skip


def _answer(session, s, sent, **result):
    command_id = reach.start(session, s.host, force=True)
    answer = {"success": True, "reachable": True, "address": "nas.example.lan",
              "port": 8443, "error": None}  # fmt: skip
    answer.update(result)
    kept = reach.record_result(session, s.host.id, {
        "command_id": command_id, "success": True, "result": answer})  # fmt: skip
    session.flush()
    return kept


def test_a_proxy_with_a_good_certificate_is_reached(session, sent):
    s = _on_proxy(session)
    assert _answer(session, s, sent, tls={"ok": True, "error": None,
                                          "spki_sha256": HASH})  # fmt: skip
    assert not reach.blocked(session, s.host)
    assert reach.state(session, s.host)["proxy"] is True


def test_a_certificate_the_host_would_refuse_blocks_it_and_says_why(session, sent):
    s = _on_proxy(session)
    assert _answer(session, s, sent, tls={"ok": False, "error": "pin_mismatch",
                                          "spki_sha256": "b" * 64})  # fmt: skip
    assert reach.blocked(session, s.host)
    text = reach.message(session, s.host)
    assert "restate-proxy" in text and "nas.example.lan" in text and "8443" in text
    assert "pin_mismatch" in text


def test_an_older_agent_answering_for_nfs_is_not_kept(session, sent):
    s = _on_proxy(session)
    assert not _answer(session, s, sent, port=2049)
    assert reach.state(session, s.host) is None  # unknown, and unknown never blocks
    assert not reach.blocked(session, s.host)


def test_switching_the_target_to_the_proxy_makes_the_last_answer_unknown(session, sent):
    s = _setup(session)
    s.nas.ipv4 = "192.168.4.10"
    s.host.agent_capabilities = CAN_CHECK
    session.commit()
    command_id = reach.start(session, s.host, force=True)
    reach.record_result(session, s.host.id, {
        "command_id": command_id, "success": True,
        "result": {"success": True, "reachable": False, "address": "192.168.4.10",
                   "port": 2049, "error": "timeout"}})  # fmt: skip
    session.flush()
    assert reach.blocked(session, s.host)
    s.target.transport = proxy.PROXY
    s.target.proxy_host = "192.168.4.10"  # the same address, another port
    session.commit()
    assert reach.state(session, s.host) is None
    assert reach.due(session, s.host)


def test_a_host_with_no_nfsv4_client_gets_the_proxy_before_its_abilities(session, sent):
    # It refuses an NFS policy, so it never sends the configure reply that
    # carries its abilities: its capability report is what says it can.
    s = _on_proxy(session, abilities=())
    s.host.platform = "OpenBSD"
    session.commit()
    got = jobs.host_configuration(s.policy, s.target, s.host)["target"]["proxy"]
    assert got["capture"] is True
    jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    assert sent[-1][2]["target"]["proxy"]["export"] is False


def test_a_linux_host_with_no_nfs_client_backs_up_through_the_proxy_alone(
    session, sent
):
    """Alpine with no nfs-utils, whose restate captures through the proxy:
    its agent says ``backup_proxy_only``, and it is treated as OpenBSD is --
    equipped for a proxy target, kept off an NFS one."""
    s = _on_proxy(session, abilities=())
    s.host.platform = "Linux"
    s.host.agent_capabilities = json.dumps(
        {"capabilities": ["backup", proxy.PROXY_ONLY_CAPABILITY]}
    )
    session.commit()
    assert proxy.needs_proxy(s.host)
    assert jobs.equipped(s.host) == (True, None)
    got = jobs.host_configuration(s.policy, s.target, s.host)["target"]["proxy"]
    assert got["capture"] is True
    s.target.transport = proxy.NFS
    session.commit()
    assert jobs.equipped(s.host) == (False, jobs.MISSING_NFS_CLIENT)  # its to install
    # Without the word, a Linux host is an NFS client as before.
    s.host.agent_capabilities = json.dumps({"capabilities": ["backup"]})
    session.commit()
    assert not proxy.needs_proxy(s.host)
    s.host.agent_capabilities = "not json"
    assert not proxy.needs_proxy(s.host)


def test_an_encrypted_proxy_host_s_storage_side_gets_its_public_key(session, sent):
    # Its prepare makes the repository encrypted to it (restate init
    # --encrypt-to); an NFS host's storage side never needs it.
    s = _on_proxy(session)
    s.policy.encrypt_public_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nx\n"
    session.commit()
    jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    assert sent[-1][2]["encrypt_key"].startswith("-----BEGIN PGP PUBLIC KEY BLOCK")
    s.policy.host_abilities = json.dumps(["list", proxy.REMOTE_ABILITY])
    session.commit()
    jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    assert "encrypt_key" not in sent[-1][2]
