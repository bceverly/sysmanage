# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""No test may send real email.

The suite reads the developer's own ``/etc/sysmanage.yaml``, and on a box
with email enabled a test that reached ``EmailService`` connected to the real
SMTP server: on 2026-10-16 two "initial setup" mails went out through Gmail
to ``should-never-be-created@example.com`` (a security test's fixture
address) and bounced back to the owner.  Every ``smtplib`` connection the
email service opens is replaced with :class:`FakeSMTP`, which records what
would have been sent; a test that wants to assert on mail reads
``FakeSMTP.sent``.
"""

from typing import List, Tuple


class FakeSMTP:
    """Stands in for ``smtplib.SMTP`` / ``SMTP_SSL``: no network, ever."""

    sent: List[Tuple[str, list, str]] = []

    def __init__(self, *_args, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def ehlo(self, *_a, **_k):
        return (250, b"fake")

    def starttls(self, *_a, **_k):
        return (220, b"fake")

    def login(self, *_a, **_k):
        return (235, b"fake")

    def send_message(self, msg, from_addr=None, to_addrs=None, **_k):
        FakeSMTP.sent.append((from_addr or msg.get("From"), to_addrs, msg.as_string()))
        return {}

    def sendmail(self, from_addr, to_addrs, msg, *_a, **_k):
        FakeSMTP.sent.append((from_addr, to_addrs, msg))
        return {}

    def quit(self):
        return (221, b"fake")

    close = quit


def install(monkeypatch):
    """Point the email service's smtplib at FakeSMTP for one test."""
    from backend.services import email_service  # noqa: PLC0415

    FakeSMTP.sent = []
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(email_service.smtplib, "SMTP_SSL", FakeSMTP)
