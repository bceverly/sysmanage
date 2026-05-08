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
