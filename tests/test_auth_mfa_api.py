# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""MFA enrollment, login challenge, and settings.

Three properties here are security properties, not conveniences, and each is
invisible from the outside if it breaks:

* ``/mfa/email/request`` must answer IDENTICALLY whether the userid exists,
  is inactive, or has no MFA enrolled.  Any divergence -- status code, body,
  even a different message -- turns the endpoint into an oracle for which
  accounts exist and which have a second factor.
* ``disable`` requires the account password and ``regenerate`` requires a live
  TOTP code, specifically so a STOLEN SESSION cannot quietly remove the second
  factor or swap the backup codes the real user wrote down.  A regression
  there is a session-token privilege escalation that no test above the API
  layer would notice.
* Backup codes are returned in plaintext exactly once, at issue time.  The
  stored form must be the hashed set.

``mfa_service`` is faked throughout: this is about what the ROUTES do with its
answers -- no real TOTP maths, no real crypto.
"""

import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException

from backend.api import auth_mfa as mfa
from backend.security.roles import SecurityRoles

MOD = "backend.api.auth_mfa"
USER_ID = uuid.UUID("88888888-8888-4888-8888-888888888888")


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, contains=True, **by_model):
        self._by_model = {k: list(v) for k, v in by_model.items()}
        self._contains = contains
        self.added = []
        self.deleted = []
        self.commits = 0

    def query(self, model):
        return _FakeQuery(self._by_model.get(model.__name__, []))

    def add(self, row):
        self.added.append(row)

    def delete(self, row):
        self.deleted.append(row)

    def commit(self):
        self.commits += 1

    def refresh(self, _row):
        pass

    def __contains__(self, _row):
        return self._contains


def _user(active=True, userid="admin@invalid"):
    return SimpleNamespace(
        id=USER_ID, userid=userid, active=active, hashed_password="$argon2id$..."
    )


def _enrollment(**overrides):
    row = SimpleNamespace(
        user_id=USER_ID,
        totp_secret_encrypted=b"enc",
        backup_codes_hashed=["h1", "h2"],
        enrolled_at=datetime(2026, 1, 1),
        last_used_at=datetime(2026, 2, 1),
        last_used_method="totp",
        remaining_backup_codes=lambda: 2,
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def _settings(**overrides):
    row = SimpleNamespace(
        issuer_name="SysManage",
        totp_digits=6,
        totp_period_seconds=30,
        backup_code_count=10,
        admin_required=False,
        grace_period_days=14,
        updated_by=None,
        to_dict=lambda: {"issuer_name": "SysManage"},
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


class _Service:
    """Stands in for the whole ``mfa_service`` module."""

    def __init__(self, enrollment=None, settings=None, **overrides):
        self.enrollment = enrollment
        self.settings = settings or _settings()
        self.defaults = {
            "get_settings": lambda db: self.settings,
            "get_enrollment": lambda db, uid: self.enrollment,
            "generate_totp_secret": lambda: "SECRET123",
            "encrypt_secret": lambda s: b"enc(%s)" % s.encode(),
            "decrypt_secret": lambda b: "SECRET123",
            "provisioning_uri": lambda s, u, st: f"otpauth://totp/{u}?secret={s}",
            "verify_totp": lambda secret, code, settings: code == "123456",
            "generate_backup_codes": lambda n: [f"code-{i}" for i in range(n)],
            "hash_backup_codes": lambda codes: [f"h({c})" for c in codes],
            "verify_user_code": lambda db, uid, code: (code == "123456", "totp"),
            "is_enrolled": lambda db, uid: self.enrollment is not None,
            "request_email_otp": lambda db, **kw: True,
        }
        self.defaults.update(overrides)

    def __enter__(self):
        self._patches = [
            patch(f"{MOD}.mfa_service.{name}", side_effect=fn)
            for name, fn in self.defaults.items()
        ]
        self._patches.append(patch(f"{MOD}.AuditService.log", side_effect=self._audit))
        self.audits = []
        for p in self._patches:
            p.start()
        return self

    def _audit(self, **kwargs):
        self.audits.append(kwargs)

    def __exit__(self, *_exc):
        for p in self._patches:
            p.stop()
        return False


class TestEnrollStart:
    @pytest.mark.asyncio
    async def test_a_first_enrollment_creates_the_row(self):
        db = _FakeSession(User=[_user()])
        with _Service():
            out = await mfa.enroll_start(db=db, current_user="admin@invalid")
        assert out.secret == "SECRET123"
        assert out.provisioning_uri.startswith("otpauth://totp/admin@invalid")
        assert out.issuer == "SysManage"
        assert len(db.added) == 1
        # No backup codes yet: they are issued only once the first code
        # verifies, so a half-finished enrollment can't hand out spares.
        assert db.added[0].backup_codes_hashed == []

    @pytest.mark.asyncio
    async def test_re_enrolling_wipes_the_old_secret_and_codes(self):
        enrollment = _enrollment()
        db = _FakeSession(User=[_user()])
        with _Service(enrollment=enrollment):
            await mfa.enroll_start(db=db, current_user="admin@invalid")
        assert db.added == []
        assert enrollment.totp_secret_encrypted != b"enc"
        # The old backup codes belong to the old secret; leaving them live
        # would let a discarded enrollment still authenticate.
        assert enrollment.backup_codes_hashed == []
        assert enrollment.last_used_at is None
        assert enrollment.last_used_method is None

    @pytest.mark.asyncio
    async def test_an_unknown_user_is_a_404(self):
        with _Service():
            with pytest.raises(HTTPException) as exc:
                await mfa.enroll_start(db=_FakeSession(), current_user="ghost")
        assert exc.value.status_code == 404


class TestEnrollComplete:
    async def _complete(self, code, enrollment=None, db=None, **svc_kwargs):
        db = db or _FakeSession(User=[_user()])
        with _Service(enrollment=enrollment, **svc_kwargs):
            out = await mfa.enroll_complete(
                mfa.EnrollCompleteRequest(code=code),
                db=db,
                current_user="admin@invalid",
            )
        return out, db

    @pytest.mark.asyncio
    async def test_a_correct_first_code_issues_backup_codes(self):
        enrollment = _enrollment(backup_codes_hashed=[])
        out, db = await self._complete("123456", enrollment)
        assert len(out.backup_codes) == 10
        assert out.backup_codes[0] == "code-0"
        # Plaintext goes out ONCE; the row keeps only hashes.
        assert enrollment.backup_codes_hashed == [f"h(code-{i})" for i in range(10)]
        assert all(not c.startswith("h(") for c in out.backup_codes)

    @pytest.mark.asyncio
    async def test_a_wrong_code_is_rejected_and_audited_as_a_failure(self):
        enrollment = _enrollment(backup_codes_hashed=[])
        with pytest.raises(HTTPException) as exc:
            await self._complete("000000", enrollment)
        assert exc.value.status_code == 400
        assert enrollment.backup_codes_hashed == []

    @pytest.mark.asyncio
    async def test_completing_without_starting_is_a_400(self):
        with pytest.raises(HTTPException) as exc:
            await self._complete("123456", None)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_a_row_with_no_secret_is_also_a_400(self):
        with pytest.raises(HTTPException) as exc:
            await self._complete("123456", _enrollment(totp_secret_encrypted=None))
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_a_zero_backup_code_policy_issues_none(self):
        enrollment = _enrollment(backup_codes_hashed=[])
        out, _ = await self._complete(
            "123456", enrollment, settings=_settings(backup_code_count=0)
        )
        assert out.backup_codes == []


class TestMfaVerify:
    async def _verify(self, token="pending", code="123456", db=None, **svc_kwargs):
        db = db or _FakeSession(User=[_user()])
        with _Service(**svc_kwargs) as svc:
            with patch(f"{MOD}.decode_mfa_pending_token") as decode:
                decode.return_value = {"user_id": "admin@invalid"} if token else None
                with patch(f"{MOD}.sign_jwt", return_value="jwt-token"):
                    with patch(
                        "backend.api.auth._default_tenant_id_for_user",
                        return_value="tenant-1",
                    ):
                        out = await mfa.mfa_verify(
                            mfa.VerifyRequest(pending_token=token or "x", code=code),
                            db=db,
                        )
        return out, svc

    @pytest.mark.asyncio
    async def test_a_valid_code_mints_a_tenant_scoped_session(self):
        out, _ = await self._verify()
        assert out["Authorization"] == "jwt-token"
        assert out["method"] == "totp"

    @pytest.mark.asyncio
    async def test_the_minted_token_carries_the_users_default_tenant(self):
        db = _FakeSession(User=[_user()])
        with _Service():
            with patch(
                f"{MOD}.decode_mfa_pending_token",
                return_value={"user_id": "admin@invalid"},
            ):
                with patch(f"{MOD}.sign_jwt", return_value="jwt") as sign:
                    with patch(
                        "backend.api.auth._default_tenant_id_for_user",
                        return_value="tenant-9",
                    ):
                        await mfa.mfa_verify(
                            mfa.VerifyRequest(pending_token="p", code="123456"), db=db
                        )
        # Skipping this drops an MFA user into the bootstrap tenant, where
        # none of their hosts live.
        assert sign.call_args.kwargs["tenant_id"] == "tenant-9"

    @pytest.mark.asyncio
    async def test_an_expired_pending_token_is_a_401(self):
        with pytest.raises(HTTPException) as exc:
            await self._verify(token=None)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_an_unknown_or_inactive_user_is_a_401(self):
        with pytest.raises(HTTPException) as exc:
            await self._verify(db=_FakeSession())
        assert exc.value.status_code == 401
        with pytest.raises(HTTPException) as exc:
            await self._verify(db=_FakeSession(User=[_user(active=False)]))
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_a_wrong_code_is_a_401_and_is_audited(self):
        db = _FakeSession(User=[_user()])
        with pytest.raises(HTTPException) as exc:
            await self._verify(code="000000", db=db)
        assert exc.value.status_code == 401
        # Committed even on the failure path: the service records the attempt
        # (rate limiting / lockout depends on it being persisted).
        assert db.commits == 1

    @pytest.mark.asyncio
    async def test_the_method_the_service_reports_is_echoed_back(self):
        out, _ = await self._verify(
            code="backup-1",
            verify_user_code=lambda db, uid, code: (True, "backup_code"),
        )
        assert out["method"] == "backup_code"


class TestMfaEmailRequest:
    async def _request(self, db, token=True, **svc_kwargs):
        service = _Service(**svc_kwargs)
        with service:
            with patch(f"{MOD}.decode_mfa_pending_token") as decode:
                decode.return_value = {"user_id": "admin@invalid"} if token else None
                out = await mfa.mfa_email_request(
                    mfa.EmailRequestRequest(pending_token="p"),
                    fastapi_request=SimpleNamespace(
                        client=SimpleNamespace(host="10.0.0.9")
                    ),
                    db=db,
                )
        return out, service

    @pytest.mark.asyncio
    async def test_an_enrolled_user_is_sent_a_code(self):
        db = _FakeSession(User=[_user()])
        out, svc = await self._request(db, enrollment=_enrollment())
        assert out["sent"] is True
        assert db.commits == 1

    @pytest.mark.asyncio
    async def test_the_source_ip_is_passed_through_for_the_audit_trail(self):
        captured = {}
        db = _FakeSession(User=[_user()])
        await self._request(
            db,
            enrollment=_enrollment(),
            request_email_otp=lambda db_, **kw: captured.update(kw) or True,
        )
        assert captured["ip_address"] == "10.0.0.9"
        assert captured["user_email"] == "admin@invalid"

    @pytest.mark.asyncio
    async def test_a_clientless_request_still_works(self):
        captured = {}
        db = _FakeSession(User=[_user()])
        with _Service(
            enrollment=_enrollment(),
            request_email_otp=lambda db_, **kw: captured.update(kw) or True,
        ):
            with patch(
                f"{MOD}.decode_mfa_pending_token",
                return_value={"user_id": "admin@invalid"},
            ):
                out = await mfa.mfa_email_request(
                    mfa.EmailRequestRequest(pending_token="p"),
                    fastapi_request=SimpleNamespace(client=None),
                    db=db,
                )
        assert out["sent"] is True
        assert captured["ip_address"] is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "case",
        ["enrolled", "not-enrolled", "inactive", "unknown-user"],
    )
    async def test_every_case_produces_a_byte_identical_response(self, case):
        # This is the anti-enumeration property.  Any difference between
        # these four -- body, message, even ordering -- tells an attacker
        # which userids exist and which have a second factor.
        setups = {
            "enrolled": (_FakeSession(User=[_user()]), _enrollment()),
            "not-enrolled": (_FakeSession(User=[_user()]), None),
            "inactive": (_FakeSession(User=[_user(active=False)]), _enrollment()),
            "unknown-user": (_FakeSession(), _enrollment()),
        }
        db, enrollment = setups[case]
        out, _ = await self._request(db, enrollment=enrollment)
        assert out == {
            "sent": True,
            "message": (
                "If your account has MFA configured, an email with a "
                "verification code has been dispatched."
            ),
        }

    @pytest.mark.asyncio
    async def test_a_failed_send_is_still_reported_as_sent(self):
        db = _FakeSession(User=[_user()])
        out, _ = await self._request(
            db,
            enrollment=_enrollment(),
            request_email_otp=lambda db_, **kw: False,
        )
        # A "we couldn't send that" reply would confirm the address exists.
        assert out["sent"] is True

    @pytest.mark.asyncio
    async def test_an_expired_pending_token_is_a_401(self):
        # The one case that DOES differ, deliberately: the caller never
        # passed the password step, so there is nothing to protect.
        with pytest.raises(HTTPException) as exc:
            await self._request(_FakeSession(User=[_user()]), token=False)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_nothing_is_committed_for_an_unknown_user(self):
        db = _FakeSession()
        await self._request(db, enrollment=_enrollment())
        assert db.commits == 0


class TestMfaDisable:
    async def _disable(self, db, password_ok=True, enrollment=None):
        with _Service(enrollment=enrollment):
            # argon2's PasswordHasher.verify is read-only on the instance, so
            # replace the whole hasher rather than patching its method.
            verify = (
                (lambda h, p: True)
                if password_ok
                else _raise(VerifyMismatchError("nope"))
            )
            with patch(f"{MOD}.argon2_hasher", SimpleNamespace(verify=verify)):
                out = await mfa.mfa_disable(
                    mfa.DisableRequest(password="pw"),
                    db=db,
                    current_user="admin@invalid",
                )
        return out

    @pytest.mark.asyncio
    async def test_the_correct_password_removes_the_enrollment(self):
        enrollment = _enrollment()
        db = _FakeSession(User=[_user()])
        out = await self._disable(db, enrollment=enrollment)
        assert out["enrolled"] is False
        assert db.deleted == [enrollment]

    @pytest.mark.asyncio
    async def test_a_wrong_password_is_a_401_and_nothing_is_deleted(self):
        # This is what stops a stolen SESSION from turning the second factor
        # off: the attacker has the token but not the password.
        db = _FakeSession(User=[_user()])
        with pytest.raises(HTTPException) as exc:
            await self._disable(db, password_ok=False, enrollment=_enrollment())
        assert exc.value.status_code == 401
        assert db.deleted == []

    @pytest.mark.asyncio
    async def test_disabling_when_not_enrolled_succeeds_idempotently(self):
        db = _FakeSession(User=[_user()])
        out = await self._disable(db, enrollment=None)
        assert out["enrolled"] is False
        assert db.deleted == []

    @pytest.mark.asyncio
    async def test_an_unknown_user_is_a_404(self):
        with pytest.raises(HTTPException) as exc:
            await self._disable(_FakeSession())
        assert exc.value.status_code == 404


def _raise(exc):
    def _fn(*_a, **_k):
        raise exc

    return _fn


class TestMfaStatus:
    @pytest.mark.asyncio
    async def test_an_unenrolled_user_reports_the_policy_only(self):
        db = _FakeSession(User=[_user()])
        with _Service(settings=_settings(admin_required=True, grace_period_days=7)):
            out = await mfa.mfa_status(db=db, current_user="admin@invalid")
        assert out.enrolled is False
        assert out.remaining_backup_codes == 0
        # The policy still has to reach the UI, or an unenrolled user is
        # never told MFA is mandatory.
        assert out.admin_required is True
        assert out.grace_period_days == 7

    @pytest.mark.asyncio
    async def test_an_enrolled_user_reports_usage_and_remaining_codes(self):
        db = _FakeSession(User=[_user()])
        with _Service(enrollment=_enrollment()):
            out = await mfa.mfa_status(db=db, current_user="admin@invalid")
        assert out.enrolled is True
        assert out.enrolled_at == "2026-01-01T00:00:00"
        assert out.last_used_at == "2026-02-01T00:00:00"
        assert out.last_used_method == "totp"
        assert out.remaining_backup_codes == 2

    @pytest.mark.asyncio
    async def test_a_never_used_enrollment_reports_nulls(self):
        enrollment = _enrollment(enrolled_at=None, last_used_at=None)
        db = _FakeSession(User=[_user()])
        with _Service(enrollment=enrollment):
            out = await mfa.mfa_status(db=db, current_user="admin@invalid")
        assert out.enrolled_at is None
        assert out.last_used_at is None

    @pytest.mark.asyncio
    async def test_an_unknown_user_is_a_404(self):
        with _Service():
            with pytest.raises(HTTPException) as exc:
                await mfa.mfa_status(db=_FakeSession(), current_user="ghost")
        assert exc.value.status_code == 404


class TestRegenerateBackupCodes:
    async def _regen(self, code, enrollment=None, db=None):
        db = db or _FakeSession(User=[_user()])
        with _Service(enrollment=enrollment):
            out = await mfa.regenerate_backup_codes(
                mfa.RegenerateRequest(code=code), db=db, current_user="admin@invalid"
            )
        return out, db

    @pytest.mark.asyncio
    async def test_a_valid_totp_code_issues_a_fresh_set(self):
        enrollment = _enrollment(backup_codes_hashed=["old"])
        out, _ = await self._regen("123456", enrollment)
        assert len(out.backup_codes) == 10
        assert enrollment.backup_codes_hashed[0] == "h(code-0)"
        assert "old" not in enrollment.backup_codes_hashed

    @pytest.mark.asyncio
    async def test_a_wrong_totp_code_leaves_the_old_set_intact(self):
        # A stolen session alone must not be able to swap the codes the real
        # user wrote down -- that would be a silent account takeover.
        enrollment = _enrollment(backup_codes_hashed=["old"])
        with pytest.raises(HTTPException) as exc:
            await self._regen("000000", enrollment)
        assert exc.value.status_code == 401
        assert enrollment.backup_codes_hashed == ["old"]

    @pytest.mark.asyncio
    async def test_regenerating_without_an_enrollment_is_a_400(self):
        with pytest.raises(HTTPException) as exc:
            await self._regen("123456", None)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_an_enrollment_with_no_timestamp_reports_an_empty_string(self):
        out, _ = await self._regen("123456", _enrollment(enrolled_at=None))
        assert out.enrolled_at == ""


class TestMfaSettings:
    @pytest.mark.asyncio
    async def test_any_authenticated_user_can_read_the_settings(self):
        # The login UI needs the issuer name and grace policy before it knows
        # anything about the user's roles.
        with _Service():
            out = await mfa.get_mfa_settings(
                db=_FakeSession(), current_user="anyone@invalid"
            )
        assert out == {"issuer_name": "SysManage"}

    async def _update(self, request, db=None, has_role=True, settings=None):
        db = db or _FakeSession(User=[_user()])
        with _Service(settings=settings):
            with patch(f"{MOD}._user_has_role", return_value=has_role):
                out = await mfa.update_mfa_settings(
                    request, db=db, current_user="admin@invalid"
                )
        return out, db

    @pytest.mark.asyncio
    async def test_an_admin_can_change_the_policy(self):
        settings = _settings()
        await self._update(
            mfa.MfaSettingsRequest(admin_required=True, grace_period_days=0),
            settings=settings,
        )
        assert settings.admin_required is True
        assert settings.grace_period_days == 0
        assert settings.updated_by == USER_ID

    @pytest.mark.asyncio
    async def test_every_field_is_individually_settable(self):
        settings = _settings()
        await self._update(
            mfa.MfaSettingsRequest(
                issuer_name="Acme",
                totp_digits=8,
                totp_period_seconds=60,
                backup_code_count=5,
            ),
            settings=settings,
        )
        assert settings.issuer_name == "Acme"
        assert settings.totp_digits == 8
        assert settings.totp_period_seconds == 60
        assert settings.backup_code_count == 5

    @pytest.mark.asyncio
    async def test_omitted_fields_are_left_alone(self):
        settings = _settings(issuer_name="Acme", totp_digits=8)
        await self._update(
            mfa.MfaSettingsRequest(grace_period_days=30), settings=settings
        )
        # A PUT that blanked every unstated field would reset the issuer name
        # and invalidate every enrolled authenticator entry.
        assert settings.issuer_name == "Acme"
        assert settings.totp_digits == 8

    @pytest.mark.asyncio
    async def test_a_transient_fallback_row_is_persisted_before_mutation(self):
        db = _FakeSession(contains=False, User=[_user()])
        settings = _settings()
        await self._update(
            mfa.MfaSettingsRequest(issuer_name="Acme"), db=db, settings=settings
        )
        # get_settings hands back an unsaved default when no row exists; the
        # update would otherwise commit nothing at all.
        assert db.added == [settings]

    @pytest.mark.asyncio
    async def test_a_non_admin_is_a_403(self):
        settings = _settings()
        with pytest.raises(HTTPException) as exc:
            await self._update(
                mfa.MfaSettingsRequest(admin_required=True),
                has_role=False,
                settings=settings,
            )
        assert exc.value.status_code == 403
        assert settings.admin_required is False

    @pytest.mark.asyncio
    async def test_an_unknown_user_is_a_404(self):
        with pytest.raises(HTTPException) as exc:
            await self._update(mfa.MfaSettingsRequest(), db=_FakeSession())
        assert exc.value.status_code == 404


class TestUserHasRole:
    def test_it_delegates_to_the_shared_role_cache(self):
        roles = SimpleNamespace(
            has_role=lambda r: r == SecurityRoles.EDIT_USER_SECURITY_ROLES
        )
        with patch("backend.api.auth_mfa.load_user_roles", return_value=roles):
            assert (
                mfa._user_has_role(
                    _FakeSession(), _user(), SecurityRoles.EDIT_USER_SECURITY_ROLES
                )
                is True
            )
            assert (
                mfa._user_has_role(_FakeSession(), _user(), SecurityRoles.DELETE_HOST)
                is False
            )
