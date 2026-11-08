# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Hosts behind NAT, said plainly (ROADMAP 25.8).

netbsd, a libvirt VM behind beast's NAT (192.168.122.133), reached nas's NFS
port, so the reach check said all was well, but nas saw it as the gateway
(192.168.4.11) and refused the mount its export made for 192.168.122.133
(2026-11-03).  The reach check now holds its connection and reports its
source port; the storage host lists who it sees on 2049.
"""

# pylint: disable=redefined-outer-name

import json

from backend.services import backup_reach as reach
from tests.services.test_backup_results import (  # noqa: F401  # pylint: disable=unused-import
    _setup,
    sent,
)

NAS = "192.168.4.10"
VM = "192.168.122.133"
GATEWAY = "192.168.4.11"
CAN_CHECK = json.dumps({"capabilities": ["backup", "backup_reach"], "commands": []})
LISTS_PEERS = json.dumps({"capabilities": ["backup", "backup_peers"], "commands": []})


def _ready(session, storage_lists_peers=True):
    s = _setup(session)
    s.nas.ipv4 = NAS
    s.host.ipv4 = VM
    s.host.agent_capabilities = CAN_CHECK
    if storage_lists_peers:
        s.nas.agent_capabilities = LISTS_PEERS
    session.flush()
    return s


def _reached(session, s, sent, local_port=818):
    command_id = reach.start(session, s.host, force=True)
    assert reach.record_result(session, s.host.id, {
        "command_id": command_id, "success": True,
        "result": {"success": True, "reachable": True, "address": NAS, "port": 2049,
                   "error": None, "local_address": VM, "local_port": local_port}})  # fmt: skip
    session.flush()
    return sent[-1]


def _peers(session, s, command_id, peers):
    assert reach.record_peers(session, s.nas.id, {
        "command_id": command_id, "success": True,
        "result": {"success": True, "peers": peers, "error": None}})  # fmt: skip
    session.flush()


def _peers_command(session, s):
    row = session.query(reach.models.BackupReach).filter_by(host_id=s.host.id).one()
    return row.peers_command_id


def test_the_check_holds_its_connection_when_the_storage_host_can_look(session, sent):
    s = _ready(session)
    reach.start(session, s.host)
    assert sent[-1][1:] == ("check_backup_storage",
                            {"address": NAS, "hold_seconds": reach.HOLD_SECONDS})  # fmt: skip


def test_an_older_storage_agent_is_not_asked_and_nothing_is_held(session, sent):
    s = _ready(session, storage_lists_peers=False)
    reach.start(session, s.host)
    assert sent[-1][1:] == ("check_backup_storage", {"address": NAS})
    _reached(session, s, sent)
    assert _peers_command(session, s) is None
    assert not reach.blocked(session, s.host)


def test_a_host_behind_nat_is_named_and_not_offered_backups(session, sent):
    s = _ready(session)
    asked = _reached(session, s, sent, local_port=818)
    assert asked[:2] == (str(s.nas.id), "list_nfs_peers")
    _peers(
        session,
        s,
        _peers_command(session, s),
        [
            {"address": "192.168.4.109", "port": 666},  # another host, direct
            {"address": GATEWAY, "port": 818},  # the VM, through the gateway
        ],
    )
    found = reach.state(session, s.host)
    assert found["reachable"] is True and found["seen_as"] == GATEWAY
    assert reach.blocked(session, s.host)
    text = reach.message(session, s.host)
    assert "behind NAT" in text and GATEWAY in text and VM in text


def test_a_host_seen_as_itself_is_not_behind_nat(session, sent):
    s = _ready(session)
    _reached(session, s, sent, local_port=900)
    _peers(session, s, _peers_command(session, s), [{"address": VM, "port": 900}])
    assert reach.state(session, s.host)["seen_as"] is None
    assert not reach.blocked(session, s.host)


def test_no_match_or_two_matches_is_unknown_and_never_blocks(session, sent):
    s = _ready(session)
    _reached(session, s, sent, local_port=901)
    _peers(session, s, _peers_command(session, s), [{"address": GATEWAY, "port": 5}])
    assert not reach.blocked(session, s.host)  # NAT rewrote the port: unknown
    _reached(session, s, sent, local_port=902)
    _peers(
        session,
        s,
        _peers_command(session, s),
        [{"address": GATEWAY, "port": 902}, {"address": "192.168.4.50", "port": 902}],
    )
    assert not reach.blocked(session, s.host)


def test_a_peers_answer_from_another_host_or_for_no_check_is_ignored(session, sent):
    s = _ready(session)
    _reached(session, s, sent)
    command_id = _peers_command(session, s)
    assert not reach.record_peers(session, s.host.id, {"command_id": command_id})
    assert not reach.record_peers(session, s.nas.id, {"command_id": "nope"})
    assert not reach.record_peers(session, s.nas.id, {
        "command_id": command_id, "result": {"success": False, "peers": "x"}})  # fmt: skip
