"""
Extended tests for backend.licensing.license_service.

Targets the substantial uncovered paths the original test file leaves alone:
- initialize() with a valid license (validation success, persistence, task start)
- _save_license_to_db() insert and update branches
- _phone_home() HTTP 200 valid / revoked / non-200 / network-error / unexpected
- _update_phone_home_timestamp() success and exception
- _check_offline_grace() expired-period and fail-open exception branches
- _deactivate_license() exception handler
- install_license() validation-success path including task restart
- background loop functions (_phone_home_loop, _module_update_loop) — first
  iteration only, with asyncio.sleep stubbed.

The aiohttp client is faked with simple awaitable context managers so we never
hit the network and the assertions can stay deterministic.
"""

import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


@contextmanager
def _patch_session(rows=None, raise_on_query=None):
    """Mock backend.licensing.license_service.sessionmaker."""
    mock_session = MagicMock()
    if raise_on_query is not None:
        mock_session.query.side_effect = raise_on_query
    else:
        mock_session.query.return_value.filter.return_value.first.return_value = rows

    with patch(
        "backend.licensing.license_service.sessionmaker"
    ) as mock_sessionmaker, patch(
        "backend.licensing.license_service.db_module.get_engine"
    ):
        cm = mock_sessionmaker.return_value.return_value
        cm.__enter__ = MagicMock(return_value=mock_session)
        cm.__exit__ = MagicMock(return_value=None)
        yield mock_session


class _AioJson:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self):
        return self._payload


class _AioPostSession:
    """Tiny aiohttp.ClientSession stand-in supporting only `.post`."""

    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def post(self, url, json=None, timeout=None):
        return self._response


def _payload(modules=None, features=None, tier="professional"):
    """A LicensePayload-shaped MagicMock for cached_license."""
    p = MagicMock()
    p.tier.value = tier
    p.modules = modules or ["health_engine"]
    p.features = features or ["health"]
    p.license_id = "LIC-123"
    p.expires_at = datetime(2099, 12, 31)
    p.offline_days = 7
    p.customer_name = "Acme"
    p.parent_hosts = 10
    p.child_hosts = 100
    return p


# ---------------------------------------------------------------------------
# initialize() — license-key happy path
# ---------------------------------------------------------------------------


class TestInitializeWithLicense:
    @pytest.mark.asyncio
    async def test_invalid_license_marks_initialized_without_caching(self):
        from backend.licensing.license_service import LicenseService
        from backend.licensing.validator import ValidationResult

        service = LicenseService()
        invalid = ValidationResult(valid=False, error="signature mismatch")

        with patch(
            "backend.licensing.license_service.get_config",
            return_value={"license": {"key": "k"}},
        ), patch(
            "backend.licensing.license_service.get_public_key_pem",
            new=AsyncMock(return_value="PEM"),
        ), patch(
            "backend.licensing.license_service.validate_license",
            return_value=invalid,
        ), patch.object(
            service, "_log_validation"
        ) as log:
            await service.initialize()

        assert service._initialized is True
        assert service._cached_license is None
        log.assert_called_with("local", "failure", "signature mismatch")

    @pytest.mark.asyncio
    async def test_valid_license_caches_and_starts_phone_home_task(self):
        from backend.licensing.license_service import LicenseService
        from backend.licensing.validator import ValidationResult

        service = LicenseService()
        payload = _payload()
        valid = ValidationResult(valid=True, payload=payload, warning=None)

        # Real asyncio task creation would warn on unawaited coroutine — wrap
        # with a stub that returns a sentinel Task-like object.
        sentinel_task = MagicMock(spec=asyncio.Task)

        with patch(
            "backend.licensing.license_service.get_config",
            return_value={
                "license": {
                    "key": "k",
                    "phone_home_url": "https://license.example.com",
                }
            },
        ), patch(
            "backend.licensing.license_service.get_public_key_pem",
            new=AsyncMock(return_value="PEM"),
        ), patch(
            "backend.licensing.license_service.validate_license",
            return_value=valid,
        ), patch(
            "backend.licensing.license_service.hash_license_key",
            return_value="HASH",
        ), patch.object(
            service, "_save_license_to_db"
        ) as save_db, patch.object(
            service, "_log_validation"
        ), patch(
            "backend.licensing.license_service.module_loader"
        ) as ml, patch(
            "backend.licensing.license_service.asyncio.create_task",
            return_value=sentinel_task,
        ), patch.object(
            service, "_phone_home_loop", return_value=None
        ), patch.object(
            service, "_module_update_loop", return_value=None
        ):
            ml.check_and_update_on_startup = AsyncMock()
            await service.initialize()

        assert service._initialized is True
        assert service._cached_license is payload
        assert service._license_key == "k"
        assert service._license_key_hash == "HASH"
        save_db.assert_called_once()
        # Both background tasks should have been started (phone_home_url present).
        assert service._phone_home_task is sentinel_task
        assert service._module_update_task is sentinel_task

    @pytest.mark.asyncio
    async def test_valid_license_with_warning_still_caches(self):
        from backend.licensing.license_service import LicenseService
        from backend.licensing.validator import ValidationResult

        service = LicenseService()
        payload = _payload()
        valid = ValidationResult(valid=True, payload=payload, warning="expires soon")

        with patch(
            "backend.licensing.license_service.get_config",
            return_value={"license": {"key": "k"}},  # no phone_home_url
        ), patch(
            "backend.licensing.license_service.get_public_key_pem",
            new=AsyncMock(return_value="PEM"),
        ), patch(
            "backend.licensing.license_service.validate_license",
            return_value=valid,
        ), patch(
            "backend.licensing.license_service.hash_license_key",
            return_value="HASH",
        ), patch.object(
            service, "_save_license_to_db"
        ), patch.object(
            service, "_log_validation"
        ), patch(
            "backend.licensing.license_service.module_loader"
        ) as ml:
            ml.check_and_update_on_startup = AsyncMock()
            await service.initialize()

        assert service._cached_license is payload
        # No phone_home_url → background tasks are NOT started.
        assert service._phone_home_task is None
        assert service._module_update_task is None


# ---------------------------------------------------------------------------
# _save_license_to_db
# ---------------------------------------------------------------------------


class TestSaveLicenseToDb:
    def test_inserts_when_no_existing_record(self):
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        service._cached_license = _payload()
        service._license_key_hash = "HASH"

        with _patch_session(rows=None) as session:
            service._save_license_to_db()
        session.add.assert_called_once()
        session.commit.assert_called_once()

    def test_updates_existing_record(self):
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        service._cached_license = _payload()
        service._license_key_hash = "HASH"

        existing = MagicMock()
        with _patch_session(rows=existing) as session:
            service._save_license_to_db()
        session.add.assert_not_called()
        # The update path mutates several fields on the existing record.
        assert existing.license_key_hash == "HASH"
        assert existing.is_active is True
        session.commit.assert_called_once()

    def test_db_error_rolls_back(self):
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        service._cached_license = _payload()
        service._license_key_hash = "HASH"

        with _patch_session(raise_on_query=RuntimeError("db down")) as session:
            service._save_license_to_db()  # must not raise
        session.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# _log_validation exception path
# ---------------------------------------------------------------------------


class TestLogValidationException:
    def test_exception_during_log_is_swallowed(self):
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        # _log_validation does not call .query() — failure has to happen on
        # add() or commit(). Make commit() raise so the except branch runs.
        mock_session = MagicMock()
        mock_session.commit.side_effect = RuntimeError("db down")

        with patch(
            "backend.licensing.license_service.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.licensing.license_service.db_module.get_engine"
        ):
            cm = mock_sessionmaker.return_value.return_value
            cm.__enter__ = MagicMock(return_value=mock_session)
            cm.__exit__ = MagicMock(return_value=None)
            # Exception must not propagate from a validation log call.
            service._log_validation("local", "success")

        mock_session.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# _phone_home — HTTP branches
# ---------------------------------------------------------------------------


class TestPhoneHomeHttpPaths:
    @pytest.mark.asyncio
    async def test_phone_home_200_valid_returns_true(self):
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        service._cached_license = _payload()
        service._license_key = "k"

        with patch(
            "backend.licensing.license_service.get_config",
            return_value={"license": {"phone_home_url": "https://l.example/"}},
        ), patch(
            "backend.licensing.license_service.aiohttp.ClientSession",
            return_value=_AioPostSession(_AioJson(200, {"valid": True})),
        ), patch.object(
            service, "_update_phone_home_timestamp"
        ) as upd, patch.object(
            service, "_log_validation"
        ) as log:
            assert await service._phone_home() is True
        upd.assert_called_once()
        log.assert_called_with("phone_home", "success")

    @pytest.mark.asyncio
    async def test_phone_home_200_revoked_deactivates(self):
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        service._cached_license = _payload()
        service._license_key = "k"

        with patch(
            "backend.licensing.license_service.get_config",
            return_value={"license": {"phone_home_url": "https://l.example/"}},
        ), patch(
            "backend.licensing.license_service.aiohttp.ClientSession",
            return_value=_AioPostSession(
                _AioJson(200, {"valid": False, "reason": "revoked"})
            ),
        ), patch.object(
            service, "_log_validation"
        ) as log, patch.object(
            service, "_deactivate_license"
        ) as deact:
            assert await service._phone_home() is False
        deact.assert_called_once()
        # The reason is included in the log message.
        args, _ = log.call_args
        assert "revoked" in args[2]

    @pytest.mark.asyncio
    async def test_phone_home_non_200_falls_back_to_offline_grace(self):
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        service._cached_license = _payload()
        service._license_key = "k"

        with patch(
            "backend.licensing.license_service.get_config",
            return_value={"license": {"phone_home_url": "https://l.example/"}},
        ), patch(
            "backend.licensing.license_service.aiohttp.ClientSession",
            return_value=_AioPostSession(_AioJson(503, {})),
        ), patch.object(
            service, "_log_validation"
        ), patch.object(
            service, "_check_offline_grace", return_value=True
        ) as grace:
            assert await service._phone_home() is True
        grace.assert_called_once()

    @pytest.mark.asyncio
    async def test_phone_home_network_error_falls_back_to_offline_grace(self):
        from backend.licensing.license_service import LicenseService
        import aiohttp

        service = LicenseService()
        service._cached_license = _payload()
        service._license_key = "k"

        class _Boom:
            async def __aenter__(self):
                raise aiohttp.ClientError("offline")

            async def __aexit__(self, *a):
                return False

        with patch(
            "backend.licensing.license_service.get_config",
            return_value={"license": {"phone_home_url": "https://l.example/"}},
        ), patch(
            "backend.licensing.license_service.aiohttp.ClientSession",
            return_value=_Boom(),
        ), patch.object(
            service, "_log_validation"
        ), patch.object(
            service, "_check_offline_grace", return_value=False
        ) as grace:
            assert await service._phone_home() is False
        grace.assert_called_once()

    @pytest.mark.asyncio
    async def test_phone_home_unexpected_error_falls_back_to_offline_grace(self):
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        service._cached_license = _payload()
        service._license_key = "k"

        class _Crash:
            async def __aenter__(self):
                raise RuntimeError("bug")

            async def __aexit__(self, *a):
                return False

        with patch(
            "backend.licensing.license_service.get_config",
            return_value={"license": {"phone_home_url": "https://l.example/"}},
        ), patch(
            "backend.licensing.license_service.aiohttp.ClientSession",
            return_value=_Crash(),
        ), patch.object(
            service, "_log_validation"
        ), patch.object(
            service, "_check_offline_grace", return_value=True
        ):
            assert await service._phone_home() is True


# ---------------------------------------------------------------------------
# _update_phone_home_timestamp
# ---------------------------------------------------------------------------


class TestUpdatePhoneHomeTimestamp:
    def test_no_license_is_noop(self):
        from backend.licensing.license_service import LicenseService

        # Should simply return without touching DB.
        LicenseService()._update_phone_home_timestamp()

    def test_updates_record_when_found(self):
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        service._cached_license = _payload()
        existing = MagicMock()
        with _patch_session(rows=existing) as session:
            service._update_phone_home_timestamp()
        # last_phone_home_at should have been set to a datetime.
        assert isinstance(existing.last_phone_home_at, datetime)
        session.commit.assert_called_once()

    def test_does_nothing_when_record_missing(self):
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        service._cached_license = _payload()
        with _patch_session(rows=None) as session:
            service._update_phone_home_timestamp()
        # No commit when there's no record to update — covers the if-branch.
        session.commit.assert_not_called()

    def test_db_error_rolls_back(self):
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        service._cached_license = _payload()
        with _patch_session(raise_on_query=RuntimeError("db down")) as session:
            service._update_phone_home_timestamp()
        session.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# _check_offline_grace — expired and fail-open paths
# ---------------------------------------------------------------------------


class TestCheckOfflineGraceExtra:
    def test_expired_grace_returns_false(self):
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        service._cached_license = _payload()
        record = MagicMock()
        # last phone-home was a year ago, offline_days=7 → expired.
        record.last_phone_home_at = datetime.now() - timedelta(days=365)
        record.offline_days = 7
        with _patch_session(rows=record):
            assert service._check_offline_grace() is False

    def test_db_error_fails_open(self):
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        service._cached_license = _payload()
        with _patch_session(raise_on_query=RuntimeError("db down")):
            # Documented behaviour: fail open on DB errors.
            assert service._check_offline_grace() is True


# ---------------------------------------------------------------------------
# _deactivate_license — exception path
# ---------------------------------------------------------------------------


class TestDeactivateLicenseException:
    def test_exception_rolls_back_and_still_clears_state(self):
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        service._cached_license = _payload()
        service._license_key = "k"

        with _patch_session(raise_on_query=RuntimeError("db down")) as session:
            service._deactivate_license()

        session.rollback.assert_called_once()
        # Even if the DB write fails, the in-memory state is cleared so that
        # the running process refuses Pro+ requests immediately.
        assert service._cached_license is None
        assert service._license_key is None


# ---------------------------------------------------------------------------
# install_license — happy path
# ---------------------------------------------------------------------------


class TestInstallLicenseHappyPath:
    @pytest.mark.asyncio
    async def test_install_success_caches_and_restarts_task(self):
        from backend.licensing.license_service import LicenseService
        from backend.licensing.validator import ValidationResult

        service = LicenseService()
        payload = _payload()
        valid = ValidationResult(valid=True, payload=payload, warning=None)
        sentinel_task = MagicMock(spec=asyncio.Task)
        # Pretend an old phone-home task is running so we exercise the cancel.
        old_task = MagicMock(spec=asyncio.Task)
        service._phone_home_task = old_task

        with patch(
            "backend.licensing.license_service.get_public_key_pem",
            new=AsyncMock(return_value="PEM"),
        ), patch(
            "backend.licensing.license_service.validate_license",
            return_value=valid,
        ), patch(
            "backend.licensing.license_service.hash_license_key",
            return_value="HASH",
        ), patch.object(
            service, "_save_license_to_db"
        ) as save_db, patch.object(
            service, "_log_validation"
        ), patch.object(
            service, "_get_phone_home_url", return_value="https://l.example/"
        ), patch(
            "backend.licensing.license_service.asyncio.create_task",
            return_value=sentinel_task,
        ), patch.object(
            service, "_phone_home_loop", return_value=None
        ):
            result = await service.install_license("new-key")

        assert result.valid is True
        assert service._cached_license is payload
        assert service._license_key == "new-key"
        save_db.assert_called_once()
        old_task.cancel.assert_called_once()
        assert service._phone_home_task is sentinel_task

    @pytest.mark.asyncio
    async def test_install_failure_logs_and_returns_result(self):
        from backend.licensing.license_service import LicenseService
        from backend.licensing.validator import ValidationResult

        service = LicenseService()
        invalid = ValidationResult(valid=False, error="bad sig")

        with patch(
            "backend.licensing.license_service.get_public_key_pem",
            new=AsyncMock(return_value="PEM"),
        ), patch(
            "backend.licensing.license_service.validate_license",
            return_value=invalid,
        ), patch.object(
            service, "_log_validation"
        ) as log:
            result = await service.install_license("bad-key")

        assert result.valid is False
        log.assert_called_with("install", "failure", "bad sig")
        assert service._cached_license is None


# ---------------------------------------------------------------------------
# Background loops — first iteration only
# ---------------------------------------------------------------------------


class TestBackgroundLoops:
    @pytest.mark.asyncio
    async def test_phone_home_loop_calls_phone_home_then_sleeps(self):
        """We can't let the loop run forever — patch asyncio.sleep so the
        second call raises CancelledError, which exits the loop cleanly."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        sleeps = {"count": 0}

        async def _sleep(seconds):
            sleeps["count"] += 1
            if sleeps["count"] >= 2:
                raise asyncio.CancelledError()

        with patch(
            "backend.licensing.license_service.asyncio.sleep", side_effect=_sleep
        ), patch.object(
            service, "_phone_home", new=AsyncMock(return_value=True)
        ) as ph, patch.object(
            service, "_get_phone_home_interval", return_value=1
        ):
            with pytest.raises(asyncio.CancelledError):
                await service._phone_home_loop()
        ph.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_phone_home_loop_swallows_per_iteration_errors(self):
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        sleeps = {"count": 0}

        async def _sleep(seconds):
            sleeps["count"] += 1
            if sleeps["count"] >= 2:
                raise asyncio.CancelledError()

        with patch(
            "backend.licensing.license_service.asyncio.sleep", side_effect=_sleep
        ), patch.object(
            service,
            "_phone_home",
            new=AsyncMock(side_effect=RuntimeError("transient")),
        ), patch.object(
            service, "_get_phone_home_interval", return_value=1
        ):
            # A transient error in one iteration must not kill the loop —
            # CancelledError from the sleep is the only way out.
            with pytest.raises(asyncio.CancelledError):
                await service._phone_home_loop()

    @pytest.mark.asyncio
    async def test_module_update_loop_invokes_check_and_update(self):
        from backend.licensing.license_service import LicenseService
        import backend.licensing.license_service as lic_svc

        service = LicenseService()
        sleeps = {"count": 0}

        async def _sleep(seconds):
            sleeps["count"] += 1
            if sleeps["count"] >= 2:
                raise asyncio.CancelledError()

        with patch(
            "backend.licensing.license_service.asyncio.sleep", side_effect=_sleep
        ), patch("backend.licensing.license_service.module_loader") as ml, patch.object(
            service, "_get_module_update_interval", return_value=1
        ):
            ml.check_and_update_on_startup = AsyncMock()
            with pytest.raises(asyncio.CancelledError):
                await service._module_update_loop()
            ml.check_and_update_on_startup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_module_update_loop_swallows_per_iteration_errors(self):
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        sleeps = {"count": 0}

        async def _sleep(seconds):
            sleeps["count"] += 1
            if sleeps["count"] >= 2:
                raise asyncio.CancelledError()

        with patch(
            "backend.licensing.license_service.asyncio.sleep", side_effect=_sleep
        ), patch("backend.licensing.license_service.module_loader") as ml, patch.object(
            service, "_get_module_update_interval", return_value=1
        ):
            ml.check_and_update_on_startup = AsyncMock(
                side_effect=RuntimeError("flaky")
            )
            with pytest.raises(asyncio.CancelledError):
                await service._module_update_loop()
