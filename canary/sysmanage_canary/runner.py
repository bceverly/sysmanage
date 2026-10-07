# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The canary's loop: run each check on its own interval (in parallel, each
bounded by its own timeout), email on state changes, ping the dead-man's
switch, and send the daily "still watching" email."""

import logging
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

from sysmanage_canary import alerts, checks
from sysmanage_canary.i18n import t

logger = logging.getLogger("sysmanage_canary")


class Canary:  # pylint: disable=too-many-instance-attributes
    def __init__(self, config: Dict[str, Any], run_check: Callable = checks.run,send: Callable = alerts.send, ping: Optional[Callable] = None):  # fmt: skip
        self.config = config
        self.enabled = [n for n, c in config["checks"].items() if c.get("enabled")]
        self.states = {name: alerts.CheckState() for name in self.enabled}
        self.next_due = {name: 0.0 for name in self.enabled}
        self.run_check = run_check
        self.send = send
        self.ping = ping or _http_ping
        self.next_ping = 0.0
        self.daily_sent_on = None
        self.pool = ThreadPoolExecutor(max_workers=max(1, len(self.enabled)))

    def _email(self, subject: str, body: str) -> None:
        try:
            self.send(self.config, subject, body)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error(t(self.config["language"], "cli.alert_failed", error=exc))

    def tick(self, mono: float, now: datetime) -> None:
        """Run what is due at monotonic time ``mono`` (wall time ``now``)."""
        due = [name for name in self.enabled if mono >= self.next_due[name]]
        futures = {
            name: self.pool.submit(self.run_check, name, self.config) for name in due
        }
        reminder = timedelta(minutes=self.config["email"]["reminder_minutes"])
        for name, future in futures.items():
            section = self.config["checks"][name]
            self.next_due[name] = mono + section["interval_seconds"]
            result = future.result()
            state = self.states[name]
            event = alerts.advance(state, result, section["failures_before_alert"],
                                   reminder, now)  # fmt: skip
            level = logging.INFO if result.ok else logging.WARNING
            logger.log(level, "%s: %s", name, t("en", result.key, **result.params))
            if event:
                self._email(*alerts.render(event, name, state, self.config, now))
        self._heartbeat(mono, now)

    def _heartbeat(self, mono: float, now: datetime) -> None:
        beat = self.config["heartbeat"]
        if beat.get("url") and mono >= self.next_ping:
            self.next_ping = mono + beat["interval_seconds"]
            try:
                self.ping(beat["url"])
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logger.warning(
                    t(self.config["language"], "cli.heartbeat_failed", error=exc)
                )
        hour = beat.get("daily_email_hour")
        local = now.astimezone()
        if (
            hour is not None
            and local.hour == hour
            and self.daily_sent_on != local.date()
        ):
            self.daily_sent_on = local.date()
            self._email(*alerts.daily_summary(self.states, self.config))

    def forever(self, sleep: Callable = time.sleep) -> None:  # pragma: no cover
        logger.info(
            t(self.config["language"], "cli.started", checks=", ".join(self.enabled))
        )
        while True:
            self.tick(time.monotonic(), datetime.now(timezone.utc))
            sleep(1)


def _http_ping(url: str) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "sysmanage-canary"})
    # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
    with urllib.request.urlopen(
        request, timeout=15
    ) as response:  # nosec B310 - admin's URL
        response.read(1024)
