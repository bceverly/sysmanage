# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The suite's own guards: no real email, no leaked auth overrides.

Both failed together on 2026-10-16: a leaked ``get_current_user`` override
let a role-escalation test's POST /user through, and the user it created was
mailed through the developer's real SMTP server."""

from backend.auth.auth_bearer import get_current_user
from backend.main import app
from backend.services import email_service
from tests.smtp_guard import FakeSMTP


def test_smtp_is_the_fake_in_every_test():
    assert email_service.smtplib.SMTP is FakeSMTP
    assert email_service.smtplib.SMTP_SSL is FakeSMTP
    with email_service.smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.sendmail("a@b.invalid", ["c@d.invalid"], "x")
    assert FakeSMTP.sent == [("a@b.invalid", ["c@d.invalid"], "x")]


def test_a_test_may_leave_an_override_behind():
    # Deliberately leaks, like the files that did; the next test proves the
    # autouse fixture cleaned it up.
    app.dependency_overrides[get_current_user] = lambda: "leaked@example.invalid"


def test_the_leak_did_not_survive_into_the_next_test():
    assert get_current_user not in app.dependency_overrides
