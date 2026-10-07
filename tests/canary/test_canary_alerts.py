# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.9: one email when a check goes down, reminders while it stays
down, one when it recovers -- never one per probe."""

from datetime import datetime, timedelta, timezone

from sysmanage_canary import alerts
from sysmanage_canary.checks import Result
from sysmanage_canary.runner import Canary

T0 = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
FAIL = Result(False, "http.status", {"status": 503})
OK = Result(True, "http.ok", {"status": 200, "ms": 12})
HOUR = timedelta(minutes=60)


def _events(results, threshold=3, step=timedelta(minutes=1)):
    state = alerts.CheckState()
    return [alerts.advance(state, r, threshold, HOUR, T0 + i * step)
            for i, r in enumerate(results)]  # fmt: skip


def test_down_after_the_threshold_then_silence():
    assert _events([FAIL] * 5) == [None, None, "down", None, None]


def test_a_blip_below_the_threshold_sends_nothing():
    assert _events([FAIL, FAIL, OK, FAIL, FAIL, OK]) == [None] * 6


def test_recovery_is_sent_only_after_a_down():
    assert _events([FAIL, FAIL, FAIL, OK, OK]) == [None, None, "down", "up", None]


def test_reminders_at_the_interval_while_down():
    events = _events([FAIL] * 130)  # one result a minute
    assert events.count("down") == 1
    assert [i for i, e in enumerate(events) if e == "reminder"] == [62, 122]


def _config(**over):
    config = {
        "language": "en", "server_name": "Prod",
        "email": {"reminder_minutes": 60, "to": ["ops@x"], "from": "a@x"},
        "heartbeat": {"url": None, "interval_seconds": 300, "daily_email_hour": None},
        "checks": {"backend": {"enabled": True, "interval_seconds": 60,
                               "failures_before_alert": 2},
                   "database": {"enabled": False}},
    }  # fmt: skip
    config.update(over)
    return config


def test_the_email_says_what_failed_and_since_when():
    state = alerts.CheckState()
    for minute in range(3):
        alerts.advance(state, FAIL, 3, HOUR, T0 + timedelta(minutes=minute))
    subject, body = alerts.render(
        "down", "backend", state, _config(), T0 + timedelta(minutes=2)
    )
    assert subject == "[Prod] Backend API is DOWN"
    assert (
        "3 checks in a row" in body
        and "HTTP 503" in body
        and "2026-10-06 12:00" in body
    )


def test_emails_come_in_the_configured_language():
    state = alerts.CheckState()
    alerts.advance(state, FAIL, 1, HOUR, T0)
    subject, _body = alerts.render("down", "backend", state, _config(language="xx"), T0)
    assert subject.startswith("[Prod]")  # an unknown language falls back to English


class TestRunner:
    def _canary(self, results, **config):
        sent, pings = [], []
        feed = iter(results)
        canary = Canary(_config(**config), run_check=lambda *_: next(feed),
                        send=lambda _c, s, b: sent.append(s), ping=pings.append)  # fmt: skip
        return canary, sent, pings

    def test_only_due_checks_run_and_emails_go_out(self):
        canary, sent, _ = self._canary([FAIL, FAIL, OK])
        canary.tick(0, T0)
        canary.tick(30, T0)  # not due again until 60
        canary.tick(60, T0 + timedelta(minutes=1))
        assert sent == ["[Prod] Backend API is DOWN"]
        canary.tick(120, T0 + timedelta(minutes=2))
        assert sent[-1] == "[Prod] Backend API has recovered"

    def test_a_mail_failure_does_not_stop_the_canary(self):
        canary = Canary(_config(), run_check=lambda *_: FAIL,
                        send=lambda *_: (_ for _ in ()).throw(OSError("smtp down")))  # fmt: skip
        canary.tick(0, T0)
        canary.tick(60, T0)  # the down email fails; no exception escapes

    def test_the_dead_mans_switch_is_pinged_on_its_interval(self):
        beat = {
            "url": "https://hc.example/abc",
            "interval_seconds": 300,
            "daily_email_hour": None,
        }
        canary, _, pings = self._canary([OK] * 10, heartbeat=beat)
        for mono in (0, 60, 120, 300, 360):
            canary.tick(mono, T0)
        assert pings == ["https://hc.example/abc"] * 2

    def test_the_daily_email_once_a_day_at_its_hour(self):
        hour = T0.astimezone().hour
        beat = {"url": None, "interval_seconds": 300, "daily_email_hour": hour}
        canary, sent, _ = self._canary([OK] * 10, heartbeat=beat)
        canary.tick(0, T0)
        canary.tick(60, T0 + timedelta(minutes=1))
        canary.tick(120, T0 + timedelta(days=1))
        assert sent.count("[Prod] sysmanage-canary is watching") == 2
