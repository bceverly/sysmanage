"""Tests for ``backend.services.mfa_service`` and the at-rest crypto helper.

These exercise the pure-logic surface — secret generation, TOTP verify,
backup-code generation/hash/consume, encryption round-trip, and the
combined ``verify_user_code`` path used by the login challenge.

Endpoint-level tests (``/api/auth/mfa/*``) live in
``test_auth_mfa_endpoints.py`` and use the FastAPI client.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pyotp
import pytest

from backend.persistence.models import UserMfaEnrollment
from backend.security import mfa_crypto
from backend.services import mfa_service


@pytest.fixture(autouse=True)
def _mfa_test_config():
    """Patch the config so mfa_crypto can derive a Fernet key without /etc/sysmanage.yaml."""
    test_config = {
        "security": {
            "jwt_secret": "test_jwt_secret_key_for_testing_purposes_32bytes",
        }
    }
    with patch("backend.config.config.get_config", return_value=test_config):
        yield


class _FakeSettings:
    """Minimal stand-in for an MfaSettings row — avoids hitting the DB."""

    issuer_name = "TestIssuer"
    totp_digits = 6
    totp_period_seconds = 30
    backup_code_count = 10


class TestEncryption:
    def test_roundtrip(self):
        secret = mfa_service.generate_totp_secret()
        ct = mfa_service.encrypt_secret(secret)
        assert ct != secret  # actually encrypted
        assert mfa_service.decrypt_secret(ct) == secret

    def test_distinct_ciphertexts_for_same_plaintext(self):
        # Fernet includes random IV, so encrypting the same secret
        # twice should yield different ciphertexts.
        secret = "ABCDEFGHIJKLMNOP"
        a = mfa_crypto.encrypt_totp_secret(secret)
        b = mfa_crypto.encrypt_totp_secret(secret)
        assert a != b

    def test_decrypt_invalid_raises(self):
        from cryptography.fernet import InvalidToken

        with pytest.raises(InvalidToken):
            mfa_service.decrypt_secret("not-a-valid-token")


class TestTotp:
    def test_generated_secret_is_base32(self):
        secret = mfa_service.generate_totp_secret()
        # pyotp's base32 is 32 characters from the standard alphabet
        assert len(secret) == 32
        assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for c in secret)

    def test_verify_accepts_current_code(self):
        secret = mfa_service.generate_totp_secret()
        code = pyotp.TOTP(secret).now()
        assert mfa_service.verify_totp(secret, code, _FakeSettings()) is True

    def test_verify_rejects_wrong_code(self):
        secret = mfa_service.generate_totp_secret()
        assert mfa_service.verify_totp(secret, "000000", _FakeSettings()) is False

    def test_verify_rejects_blank(self):
        secret = mfa_service.generate_totp_secret()
        assert mfa_service.verify_totp(secret, "", _FakeSettings()) is False
        assert mfa_service.verify_totp(secret, "   ", _FakeSettings()) is False

    def test_verify_rejects_non_numeric(self):
        secret = mfa_service.generate_totp_secret()
        assert mfa_service.verify_totp(secret, "abcdef", _FakeSettings()) is False

    def test_provisioning_uri_carries_issuer(self):
        secret = mfa_service.generate_totp_secret()
        uri = mfa_service.provisioning_uri(secret, "alice@example.com", _FakeSettings())
        assert uri.startswith("otpauth://totp/")
        assert "TestIssuer" in uri
        assert "alice%40example.com" in uri or "alice@example.com" in uri


class TestBackupCodes:
    def test_generates_correct_count(self):
        codes = mfa_service.generate_backup_codes(7)
        assert len(codes) == 7

    def test_zero_count_returns_empty(self):
        assert mfa_service.generate_backup_codes(0) == []

    def test_codes_are_unique(self):
        codes = mfa_service.generate_backup_codes(20)
        assert len(set(codes)) == len(codes)

    def test_codes_have_dash_separator(self):
        codes = mfa_service.generate_backup_codes(3)
        for c in codes:
            assert len(c) == 9  # 4 + dash + 4
            assert c[4] == "-"

    def test_hash_then_consume_succeeds(self):
        codes = mfa_service.generate_backup_codes(3)
        enrollment = UserMfaEnrollment(
            user_id="00000000-0000-0000-0000-000000000000",
            totp_secret_encrypted="x",
            backup_codes_hashed=mfa_service.hash_backup_codes(codes),
            enrolled_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        assert enrollment.remaining_backup_codes() == 3
        assert mfa_service.consume_backup_code(enrollment, codes[1]) is True
        # Used code is removed; can't be consumed again.
        assert enrollment.remaining_backup_codes() == 2
        assert mfa_service.consume_backup_code(enrollment, codes[1]) is False

    def test_consume_accepts_normalized_input(self):
        codes = mfa_service.generate_backup_codes(1)
        enrollment = UserMfaEnrollment(
            user_id="00000000-0000-0000-0000-000000000000",
            totp_secret_encrypted="x",
            backup_codes_hashed=mfa_service.hash_backup_codes(codes),
            enrolled_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        # Same code without dash, lower-case, with whitespace.
        raw = codes[0].replace("-", "").lower()
        assert mfa_service.consume_backup_code(enrollment, f"  {raw}  ") is True

    def test_consume_rejects_wrong_code(self):
        codes = mfa_service.generate_backup_codes(2)
        enrollment = UserMfaEnrollment(
            user_id="00000000-0000-0000-0000-000000000000",
            totp_secret_encrypted="x",
            backup_codes_hashed=mfa_service.hash_backup_codes(codes),
            enrolled_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        assert mfa_service.consume_backup_code(enrollment, "WRON-GCOD") is False
        assert enrollment.remaining_backup_codes() == 2


class TestVerifyUserCode:
    def _build_session(self, enrollment, settings=None):
        """Build a MagicMock session whose query path returns our row."""
        session = MagicMock()
        # mfa_service.get_enrollment(): db.query(UserMfaEnrollment).filter(...).first()
        session.query.return_value.filter.return_value.first.return_value = enrollment
        return session

    def test_accepts_totp_path(self):
        secret = mfa_service.generate_totp_secret()
        enrollment = UserMfaEnrollment(
            user_id="00000000-0000-0000-0000-000000000000",
            totp_secret_encrypted=mfa_service.encrypt_secret(secret),
            backup_codes_hashed=[],
            enrolled_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        # Session that returns enrollment for the enrollment query AND
        # None for the settings query (so get_settings falls back to
        # defaults).
        session = MagicMock()
        session.query.return_value.filter.return_value.first.side_effect = [
            enrollment,  # enrollment lookup
            None,  # settings lookup → fallback defaults
        ]
        ok, method = mfa_service.verify_user_code(
            session, "00000000-0000-0000-0000-000000000000", pyotp.TOTP(secret).now()
        )
        assert ok is True
        assert method == "totp"
        assert enrollment.last_used_method == "totp"

    def test_falls_back_to_backup_code(self):
        secret = mfa_service.generate_totp_secret()
        codes = mfa_service.generate_backup_codes(2)
        enrollment = UserMfaEnrollment(
            user_id="00000000-0000-0000-0000-000000000000",
            totp_secret_encrypted=mfa_service.encrypt_secret(secret),
            backup_codes_hashed=mfa_service.hash_backup_codes(codes),
            enrolled_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session = MagicMock()
        session.query.return_value.filter.return_value.first.side_effect = [
            enrollment,
            None,
        ]
        ok, method = mfa_service.verify_user_code(
            session, "00000000-0000-0000-0000-000000000000", codes[0]
        )
        assert ok is True
        assert method == "backup_code"
        assert enrollment.last_used_method == "backup_code"
        assert enrollment.remaining_backup_codes() == 1

    def test_rejects_unknown_user(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None
        ok, method = mfa_service.verify_user_code(session, "missing-user", "000000")
        assert ok is False
        assert method is None

    def test_falls_back_to_email_otp_when_totp_and_backup_miss(self):
        """Email-OTP is the third path: when TOTP doesn't validate
        the code AND no backup code matches, the verifier checks live
        email-OTP challenges as a last resort."""
        secret = mfa_service.generate_totp_secret()
        enrollment = UserMfaEnrollment(
            user_id="00000000-0000-0000-0000-000000000000",
            totp_secret_encrypted=mfa_service.encrypt_secret(secret),
            backup_codes_hashed=[],
            enrolled_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        # Build a live email challenge for the same user, with the
        # plaintext code "123456".
        live_challenge = MagicMock()
        live_challenge.code_hash = mfa_service._EMAIL_CODE_HASHER.hash("123456")
        live_challenge.consumed_at = None

        session = MagicMock()
        # Enrollment lookup → enrollment; settings lookup → None;
        # live challenge query → [live_challenge].
        session.query.return_value.filter.return_value.first.side_effect = [
            enrollment,
            None,
        ]
        session.query.return_value.filter.return_value.all.return_value = [
            live_challenge
        ]

        ok, method = mfa_service.verify_user_code(
            session, "00000000-0000-0000-0000-000000000000", "123456"
        )
        assert ok is True
        assert method == "email_otp"
        assert enrollment.last_used_method == "email_otp"
        assert live_challenge.consumed_at is not None


class TestEmailOtpFlow:
    """Coverage for the email-OTP request/verify path used as the
    third MFA factor (Phase 10.3 follow-up)."""

    def test_generate_email_otp_returns_six_digits(self):
        code = mfa_service.generate_email_otp_code()
        assert len(code) == 6
        assert code.isdigit()

    def test_generate_email_otp_pads_leading_zeros(self):
        """Re-roll a few hundred times and verify NONE come back
        shorter than 6 chars — the zfill is the only thing keeping
        small ``randbelow`` outputs at full width."""
        for _ in range(200):
            code = mfa_service.generate_email_otp_code()
            assert len(code) == 6, f"got short code {code!r}; zfill regressed?"

    def test_request_invalidates_existing_live_challenges(self):
        """Issuing a new code must mark any prior unconsumed challenge
        as consumed.  Without this, two open codes would coexist and
        the second-issued one would be the user-facing "fresh" one
        while the first stays valid — a confusing-and-exploitable
        ambiguity."""
        old_challenge = MagicMock()
        old_challenge.consumed_at = None

        captured = {}

        def fake_send(to_addresses, subject, body):
            captured["to"] = to_addresses
            captured["subject"] = subject
            captured["body"] = body
            return True

        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [
            old_challenge
        ]
        session.add = MagicMock()

        sent = mfa_service.request_email_otp(
            session,
            user_id="user-1",
            user_email="user@example.com",
            email_send_fn=fake_send,
        )
        assert sent is True
        assert (
            old_challenge.consumed_at is not None
        ), "prior live challenge was not invalidated"
        assert captured["to"] == ["user@example.com"]
        # The 6-digit code must appear in the email body (otherwise the
        # user has no way to find it).
        import re

        assert re.search(r"\b\d{6}\b", captured["body"]), captured["body"]

    def test_request_returns_false_when_email_send_raises(self):
        """SMTP failures must NOT propagate — the user-facing endpoint
        always returns "if your account exists we sent a code" to
        avoid user-enumeration.  This locks in the "swallow and
        report False" contract."""

        def fake_send(to_addresses, subject, body):
            raise RuntimeError("smtp connection refused")

        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = []
        session.add = MagicMock()

        sent = mfa_service.request_email_otp(
            session,
            user_id="user-1",
            user_email="user@example.com",
            email_send_fn=fake_send,
        )
        assert sent is False

    def test_consume_rejects_wrong_code(self):
        challenge = MagicMock()
        challenge.code_hash = mfa_service._EMAIL_CODE_HASHER.hash("123456")
        challenge.consumed_at = None

        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [challenge]
        ok = mfa_service._consume_email_challenge(session, "user-1", "000000")
        assert ok is False
        # The miss must NOT consume the challenge — a wrong-then-right
        # retry within the lifetime window has to still work.
        assert challenge.consumed_at is None

    def test_consume_accepts_correct_code_and_marks_consumed(self):
        challenge = MagicMock()
        challenge.code_hash = mfa_service._EMAIL_CODE_HASHER.hash("424242")
        challenge.consumed_at = None

        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [challenge]
        ok = mfa_service._consume_email_challenge(session, "user-1", "424242")
        assert ok is True
        assert challenge.consumed_at is not None

    def test_consume_with_no_live_challenges_returns_false(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = []
        ok = mfa_service._consume_email_challenge(session, "user-1", "424242")
        assert ok is False

    def test_consume_rejects_empty_or_whitespace_code(self):
        session = MagicMock()
        # No query should be made — the early-return on falsy code
        # short-circuits before db.query is touched.
        assert mfa_service._consume_email_challenge(session, "u", "") is False
        assert mfa_service._consume_email_challenge(session, "u", "   ") is False
        # Confirm we didn't bother the DB for the empty-code path.
        session.query.assert_not_called()

    def test_rejects_invalid_code(self):
        secret = mfa_service.generate_totp_secret()
        enrollment = UserMfaEnrollment(
            user_id="00000000-0000-0000-0000-000000000000",
            totp_secret_encrypted=mfa_service.encrypt_secret(secret),
            backup_codes_hashed=[],
            enrolled_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session = MagicMock()
        session.query.return_value.filter.return_value.first.side_effect = [
            enrollment,
            None,
        ]
        ok, method = mfa_service.verify_user_code(
            session, "00000000-0000-0000-0000-000000000000", "000000"
        )
        assert ok is False
        assert method is None
