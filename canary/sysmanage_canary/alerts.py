# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""When to email, and sending it.

One email when a check has failed ``failures_before_alert`` times in a row,
a reminder every ``email.reminder_minutes`` while it stays down, and one when
it works again -- never one per probe.  A check that fails fewer times than
its threshold and then passes sends nothing."""

import smtplib
import socket
import ssl
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Any, Dict, List, Optional, Tuple

from sysmanage_canary.checks import Result
from sysmanage_canary.i18n import t


@dataclass
class CheckState:
    failures: int = 0
    failing_since: Optional[datetime] = None
    down: bool = False  # alerted, and not yet recovered
    last_alert: Optional[datetime] = None
    last: Optional[Result] = None


def advance(state: CheckState, result: Result, threshold: int, reminder: timedelta,now: datetime) -> Optional[str]:  # fmt: skip
    """Fold ``result`` into ``state``; the email to send now, if any:
    ``"down"``, ``"reminder"`` or ``"up"``."""
    state.last = result
    if result.ok:
        was_down = state.down
        state.failures, state.down, state.last_alert = 0, False, None
        return "up" if was_down else None
    state.failures += 1
    if state.failures == 1:
        state.failing_since = now
    if not state.down and state.failures >= threshold:
        state.down, state.last_alert = True, now
        return "down"
    if state.down and state.last_alert and now - state.last_alert >= reminder:
        state.last_alert = now
        return "reminder"
    return None


def render(event: str, name: str, state: CheckState, config: Dict[str, Any],now: datetime) -> Tuple[str, str]:  # fmt: skip
    """(subject, body) of the email for ``event`` on check ``name``."""
    lang = config["language"]
    check = t(lang, f"check.{name}")
    detail = t(lang, state.last.key, **state.last.params) if state.last else ""
    since = state.failing_since or now
    minutes = int((now - since).total_seconds() // 60)
    values = {"server": config["server_name"], "check": check, "detail": detail,
              "since": since.strftime("%Y-%m-%d %H:%M %Z").strip(),
              "count": state.failures, "minutes": minutes}  # fmt: skip
    return t(lang, f"email.{event}.subject", **values), t(
        lang, f"email.{event}.body", **values
    )


def daily_summary(
    states: Dict[str, CheckState], config: Dict[str, Any]
) -> Tuple[str, str]:
    lang = config["language"]
    lines = []
    for name, state in states.items():
        word = t(lang, "state.down" if state.down else "state.up")
        detail = t(lang, state.last.key, **state.last.params) if state.last else ""
        lines.append(f"- {t(lang, f'check.{name}')}: {word}. {detail}")
    values = {"server": config["server_name"], "states": "\n".join(lines)}
    return t(lang, "email.daily.subject", **values), t(
        lang, "email.daily.body", **values
    )


def send(config: Dict[str, Any], subject: str, body: str) -> None:
    """Send one email through the canary's own SMTP settings; raises on
    failure (the caller logs it -- a canary must not die of a mail error)."""
    email = config["email"]
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = email["from"]
    message["To"] = ", ".join(str(r) for r in email["to"])
    footer = t(config["language"], "email.footer", host=socket.gethostname())
    message.set_content(f"{body}\n\n--\n{footer}\n")
    timeout = email["timeout_seconds"]
    context = ssl.create_default_context()
    if email["security"] == "tls":
        server: smtplib.SMTP = smtplib.SMTP_SSL(email["host"], email["port"], timeout=timeout,
                                                context=context)  # fmt: skip
    else:
        server = smtplib.SMTP(email["host"], email["port"], timeout=timeout)
    with server:
        if email["security"] == "starttls":
            server.starttls(context=context)
        if email.get("username"):
            server.login(email["username"], email.get("password") or "")
        server.send_message(message)


def recipients(config: Dict[str, Any]) -> List[str]:
    return [str(r) for r in config["email"]["to"]]
