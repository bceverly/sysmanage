# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.6: ClamAV signature downloads are spread per host.

A deploy plan downloaded signatures (and started the updater) at once on
every host it reached, and the Windows update task had no start time, so a
fleet deployed together updated in the same minute ever after.
"""

import uuid

from backend.services import av_plan_builder as builder
from backend.services import av_scan_schedule as schedule

LINUX = {"platform": "Linux", "platform_release": "Ubuntu 24.04"}
WINDOWS = {"platform": "Windows", "platform_release": "Windows 11"}


def _hosts(n=200):
    return [str(uuid.uuid4()) for _ in range(n)]


def _delay(plan):
    first = plan["commands"][0]
    return first if first.get("description") == schedule.PRE_DOWNLOAD_DELAY else None


def _seconds(command):
    return int(command["argv"][-1].split()[-1])


class TestPreDownloadDelay:
    def test_linux_plan_waits_its_hosts_share_first(self):
        waits = []
        for host_id in _hosts():
            plan = builder.build_deploy_plan({**LINUX, "host_id": host_id}, "clamav")
            delay = _delay(plan)
            if delay is None:  # a share under one second
                continue
            assert delay["argv"][0] == "sleep" and delay["ignore_errors"]
            assert plan["commands"][1]["description"] == builder.REFRESH_SIGNATURES
            waits.append(_seconds(delay))
        assert all(1 <= w < schedule.PRE_DOWNLOAD_SPLAY_SECONDS for w in waits)
        assert len(set(waits)) > 100  # spread, not one moment

    def test_the_wait_is_fixed_per_host(self):
        info = {**LINUX, "host_id": "6f1c8a2e-0000-4000-8000-000000000001"}
        first = builder.build_deploy_plan(info, "clamav")["commands"][0]
        again = builder.build_deploy_plan(info, "clamav")["commands"][0]
        assert first == again

    def test_windows_waits_with_powershell(self):
        for host_id in _hosts(20):
            plan = builder.build_deploy_plan({**WINDOWS, "host_id": host_id}, "clamav")
            delay = _delay(plan)
            if delay:
                assert delay["argv"][:3] == ["powershell", "-NoProfile", "-Command"]
                assert delay["argv"][3].startswith("Start-Sleep -Seconds ")
                return
        raise AssertionError("no Windows plan had a wait")

    def test_no_host_id_no_wait(self):
        plan = builder.build_deploy_plan(LINUX, "clamav")
        assert _delay(plan) is None
        assert plan["commands"][0]["description"] == builder.REFRESH_SIGNATURES

    def test_the_command_timeout_covers_the_wait(self):
        info = {**LINUX, "host_id": "any-host"}
        delay = schedule.pre_download_delay_command(info)
        assert delay is None or delay["timeout"] > _seconds(delay)


class TestWindowsUpdateTaskStart:
    def _start(self, host_id, checks=None):
        plan = builder.build_deploy_plan(
            {**WINDOWS, "host_id": host_id}, "clamav", {"checks_per_day": checks}
        )
        task = next(c for c in plan["commands"] if "/TN" in c["argv"]
                    and builder.WINDOWS_UPDATE_TASK in c["argv"])  # fmt: skip
        argv = task["argv"]
        return argv[argv.index("/ST") + 1], int(argv[argv.index("/MO") + 1])

    def test_starts_spread_within_one_period(self):
        starts = set()
        for host_id in _hosts():
            start, every = self._start(host_id, checks=12)  # every 2 hours
            hours, minutes = map(int, start.split(":"))
            assert hours * 60 + minutes < every * 60
            starts.add(start)
        assert len(starts) > 60

    def test_start_time_is_a_valid_clock_time(self):
        for host_id in _hosts(50):
            start, _every = self._start(host_id, checks=1)  # daily
            hours, minutes = map(int, start.split(":"))
            assert 0 <= hours < 24 and 0 <= minutes < 60


def test_plan_version_bumped_so_equipped_hosts_get_it():
    assert builder.PLAN_VERSION >= 7
