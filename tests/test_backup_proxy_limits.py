# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""restate-proxy bandwidth by the hour (ROADMAP 25.5 limits, 25.7 editions).

Rules are checked as restate-proxy checks a grant's ``bandwidth`` lines;
setting them needs the Pro+ backup engine (402), clearing them never does;
they reach the storage host only while the engine is loaded and only once
its restate reads them, so a lapsed license or an old storage host never
breaks a proxy backup -- it only lifts the cap.
"""

# pylint: disable=redefined-outer-name

import json

import pytest

from backend.api import backups_transport as transport_api
from backend.services import backup_jobs as jobs
from backend.services import backup_proxy_limits as limits
from tests.test_backup_proxy import HASH_A, _on_proxy
from tests.test_backups_api import (  # noqa: F401  # pylint: disable=unused-import
    MANAGER,
    NOBODY,
    _status,
    sent,
)


@pytest.fixture
def licensed(monkeypatch):
    state = {"on": True}
    monkeypatch.setattr(limits, "licensed", lambda: state["on"])
    return state


def _rules(*rules):
    return transport_api.BandwidthBody(rules=list(rules))


def test_rules_are_read_as_restate_proxy_reads_them():
    assert limits.check_rules(["08-18 2MiB/s", "22-06 512KiB/s", "20MiB/s"]) == [
        "08-18 2MiB/s", "22-06 512KiB/s", "20MiB/s"
    ]  # fmt: skip
    assert limits.check_rules(["00-24 unlimited"]) == ["00-24 unlimited"]
    assert limits.check_rules([" 1GiB/s "]) == ["1GiB/s"]
    assert limits.check_rules(None) == []
    for bad in (
        ["2 MiB/s"],  # restate wants no space in a rate
        ["2MB/s"],
        ["32KiB/s"],  # under 64 KiB/s
        ["0MiB/s"],
        ["8-18 2MiB/s"],  # hours are two digits
        ["18-18 2MiB/s"],
        ["24-06 2MiB/s"],
        ["08-25 2MiB/s"],
        ["08-18 2MiB/s", "17-20 1MiB/s"],  # 17:00 in both
        ["22-06 2MiB/s", "05-07 1MiB/s"],  # across midnight, 05:00 in both
        ["2MiB/s", "3MiB/s"],
        "2MiB/s",
        ["1MiB/s"] * 26,
        [7],
    ):
        with pytest.raises(limits.BandwidthRefused):
            limits.check_rules(bad)


def test_hours_across_midnight_and_the_whole_day():
    assert limits._hours(22, 6) == sum(1 << h for h in (22, 23, 0, 1, 2, 3, 4, 5))
    assert limits._hours(0, 24) == (1 << 24) - 1
    assert limits._hours(8, 9) == 1 << 8


@pytest.mark.asyncio
async def test_setting_rules_needs_the_role_and_the_engine(session, sent, licensed):
    s = _on_proxy(session)
    target_id = str(s.target.id)
    assert await _status(transport_api.set_proxy_bandwidth(
        target_id, _rules("2MiB/s"), session, NOBODY)) == 403  # fmt: skip
    assert await _status(transport_api.set_proxy_bandwidth(
        target_id, _rules("2 MiB/s"), session, MANAGER)) == 422  # fmt: skip
    licensed["on"] = False
    assert await _status(transport_api.set_proxy_bandwidth(
        target_id, _rules("2MiB/s"), session, MANAGER)) == 402  # fmt: skip
    # Clearing never needs the license.
    view = await transport_api.set_proxy_bandwidth(
        target_id, _rules(), session, MANAGER
    )
    assert view["proxy_bandwidth"]["rules"] == [] and s.target.proxy_bandwidth is None
    licensed["on"] = True
    before = s.policy.config_version
    view = await transport_api.set_proxy_bandwidth(
        target_id, _rules("08-18 2MiB/s", "20MiB/s"), session, MANAGER
    )
    assert json.loads(s.target.proxy_bandwidth) == ["08-18 2MiB/s", "20MiB/s"]
    assert view["proxy_bandwidth"]["rules"] == ["08-18 2MiB/s", "20MiB/s"]
    session.refresh(s.policy)
    assert s.policy.config_version > before  # the storage host rewrites its grants


def _grants(session, sent, s):
    jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    return sent[-1][2]["target"]["proxy"]["grants"]


def _limited(session, abilities=(limits.ABILITY,)):
    s = _on_proxy(session)
    s.policy.proxy_token_sha256 = HASH_A
    s.policy.storage_abilities = json.dumps(list(abilities))
    s.target.proxy_bandwidth = json.dumps(["08-18 2MiB/s", "20MiB/s"])
    session.commit()
    return s


def test_the_grants_carry_the_rules(session, sent, licensed):
    s = _limited(session)
    assert _grants(session, sent, s)[0]["bandwidth"] == ["08-18 2MiB/s", "20MiB/s"]


def test_a_lapsed_license_lifts_the_cap_and_nothing_else(session, sent, licensed):
    s = _limited(session)
    licensed["on"] = False
    grants = _grants(session, sent, s)
    assert grants and "bandwidth" not in grants[0]  # the grant itself is unchanged
    view = limits.view(s.target, [limits.ABILITY])
    assert view["applied"] is False and view["reason"] == "unlicensed"


def test_a_storage_host_too_old_for_limits_never_gets_the_key(session, sent, licensed):
    s = _limited(session, abilities=("keep_yearly",))
    assert "bandwidth" not in _grants(session, sent, s)[0]
    view = limits.view(s.target, ["keep_yearly"])
    assert view["applied"] is False and view["reason"] == "storage_too_old"


def test_the_view_says_when_the_rules_apply(session, licensed):
    s = _limited(session)
    assert limits.view(s.target, [limits.ABILITY])["applied"] is True
    # Before the storage host has reported, nothing is claimed either way.
    assert limits.view(s.target, None) == {
        "rules": ["08-18 2MiB/s", "20MiB/s"], "licensed": True, "applied": False
    }  # fmt: skip
    s.target.proxy_bandwidth = "not json"
    assert limits.view(s.target, None)["rules"] == []
