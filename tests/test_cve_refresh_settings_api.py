# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""CVE feed settings, statistics, history, and refresh.

The refresh endpoint's whole design point is that ONE source failing must not
stop the others: NVD rate-limits aggressively, and a single 403 from it used
to abandon the Ubuntu, Debian, Red Hat, Microsoft, and FreeBSD feeds too, so a
fleet's vulnerability data quietly went stale everywhere because of one
upstream.  Per-source isolation is asserted directly, along with the fact that
the partial failure is still REPORTED -- a run that silently swallowed the
error would look like a clean refresh.

The other property worth pinning: the NVD API key is write-only over the wire.
Every settings response reports ``has_nvd_api_key`` as a boolean; the key
itself must never appear in a response body.

The Pro+ ``vuln_engine`` gate sits in front of all seven routes, so an
unlicensed server gets a 402 rather than a half-working feature.
"""

import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.api import cve_refresh_settings as cve
from backend.vulnerability.cve_refresh_service import CveRefreshError

MOD = "backend.api.cve_refresh_settings"
SETTINGS_ID = uuid.UUID("77777777-7777-4777-8777-777777777777")


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, **by_model):
        self._by_model = {k: list(v) for k, v in by_model.items()}
        self.commits = 0

    def query(self, model):
        return _FakeQuery(self._by_model.get(model.__name__, []))

    def commit(self):
        self.commits += 1


def _user(is_admin=True):
    return SimpleNamespace(id="u1", userid="admin@invalid", is_admin=is_admin)


def _settings(**overrides):
    row = SimpleNamespace(
        id=SETTINGS_ID,
        enabled=True,
        refresh_interval_hours=24,
        enabled_sources=["nvd", "ubuntu"],
        nvd_api_key="secret-key",
        last_refresh_at=datetime(2026, 1, 1),
        next_refresh_at=datetime(2026, 1, 2),
        created_at=datetime(2025, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def _log(**overrides):
    row = SimpleNamespace(
        id=uuid.uuid4(),
        source="nvd",
        started_at=datetime(2026, 1, 1),
        completed_at=datetime(2026, 1, 1, 1),
        status="success",
        vulnerabilities_processed=100,
        packages_processed=50,
        error_message=None,
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def _licensed():
    return patch(f"{MOD}.module_loader.get_module", return_value=object())


class _Service:
    """Stands in for ``cve_refresh_service``."""

    def __init__(self, settings=None, **overrides):
        self.settings = settings if settings is not None else _settings()
        self.refreshed = []
        self.defaults = {
            "get_settings": lambda db: self.settings,
            "update_settings": lambda db, **kw: self._update(**kw),
            "get_database_stats": lambda db: {
                "total_cves": 10,
                "total_package_mappings": 20,
                "severity_counts": {"HIGH": 5},
            },
            "get_ingestion_history": lambda db, limit: [_log()][:limit],
            "refresh_from_source": self._refresh,
        }
        self.defaults.update(overrides)

    def _update(self, **kwargs):
        for key, value in kwargs.items():
            if value is not None:
                setattr(self.settings, key, value)
        return self.settings

    async def _refresh(self, db, source, api_key):
        self.refreshed.append((source, api_key))
        return {"vulnerabilities_processed": 7, "packages_processed": 3}

    def __enter__(self):
        self._patches = [
            patch(f"{MOD}.cve_refresh_service.{name}", side_effect=fn)
            for name, fn in self.defaults.items()
        ]
        self._patches.append(patch(f"{MOD}.AuditService", MagicMock()))
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *_exc):
        for p in self._patches:
            p.stop()
        return False


# Every route behind the Pro+ gate, with a zero-argument invocation.
GATED = [
    ("get_available_sources", lambda: cve.get_available_sources()),
    (
        "get_cve_refresh_settings",
        lambda: cve.get_cve_refresh_settings(db=_FakeSession()),
    ),
    (
        "update_cve_refresh_settings",
        lambda: cve.update_cve_refresh_settings(
            cve.CveRefreshSettingsUpdate(), db=_FakeSession(), current_user="u"
        ),
    ),
    ("get_database_stats", lambda: cve.get_database_stats(db=_FakeSession())),
    ("get_ingestion_history", lambda: cve.get_ingestion_history(db=_FakeSession())),
    (
        "trigger_cve_refresh",
        lambda: cve.trigger_cve_refresh(
            background_tasks=None, db=_FakeSession(), current_user="u"
        ),
    ),
    (
        "clear_nvd_api_key",
        lambda: cve.clear_nvd_api_key(db=_FakeSession(), current_user="u"),
    ),
]


class TestLicenseGate:
    def test_an_unlicensed_server_gets_a_402_pointing_at_the_upgrade(self):
        with patch(f"{MOD}.module_loader.get_module", return_value=None):
            with pytest.raises(HTTPException) as exc:
                cve._check_vuln_engine_module()
        assert exc.value.status_code == 402
        assert "Professional+" in exc.value.detail

    def test_a_licensed_server_returns_the_engine(self):
        engine = object()
        with patch(f"{MOD}.module_loader.get_module", return_value=engine):
            assert cve._check_vuln_engine_module() is engine

    @pytest.mark.asyncio
    @pytest.mark.parametrize("name,call", GATED)
    async def test_every_route_sits_behind_the_gate(self, name, call):
        # Half a CVE feature on an OSS install is worse than none: the UI
        # would render settings that nothing acts on.
        with patch(f"{MOD}.module_loader.get_module", return_value=None):
            with pytest.raises(HTTPException) as exc:
                await call()
        assert exc.value.status_code == 402


class TestGetAvailableSources:
    @pytest.mark.asyncio
    async def test_every_configured_source_is_described(self):
        with _licensed():
            out = await cve.get_available_sources()
        assert set(out) == {"nvd", "ubuntu", "debian", "redhat", "microsoft", "freebsd"}
        assert out["nvd"].enabled_by_default is True
        assert out["nvd"].name

    @pytest.mark.asyncio
    async def test_the_base_url_is_not_leaked_into_the_response(self):
        # CveSourceInfo deliberately projects three fields; the upstream URL
        # is operational config, not something the UI needs.
        with _licensed():
            out = await cve.get_available_sources()
        assert not hasattr(out["nvd"], "base_url")


class TestUpdateValidation:
    def test_a_normal_interval_is_accepted(self):
        assert cve.CveRefreshSettingsUpdate(refresh_interval_hours=24)

    @pytest.mark.parametrize("hours", [0, -1, 169, 1000])
    def test_an_out_of_range_interval_is_rejected(self, hours):
        # Below 1 would hammer NVD's rate limit; above a week means the feed
        # is stale enough to be misleading.
        with pytest.raises(ValidationError):
            cve.CveRefreshSettingsUpdate(refresh_interval_hours=hours)

    @pytest.mark.parametrize("hours", [1, 168])
    def test_the_boundaries_are_inclusive(self, hours):
        assert cve.CveRefreshSettingsUpdate(refresh_interval_hours=hours)

    def test_an_omitted_interval_skips_the_check(self):
        assert cve.CveRefreshSettingsUpdate().refresh_interval_hours is None

    def test_known_sources_are_accepted(self):
        request = cve.CveRefreshSettingsUpdate(enabled_sources=["nvd", "debian"])
        assert request.enabled_sources == ["nvd", "debian"]

    def test_an_unknown_source_is_rejected_by_name(self):
        with pytest.raises(ValidationError) as exc:
            cve.CveRefreshSettingsUpdate(enabled_sources=["nvd", "made-up"])
        assert "made-up" in str(exc.value)

    def test_an_empty_source_list_is_allowed(self):
        # Means "no feeds"; disabling every source is a legitimate choice.
        assert cve.CveRefreshSettingsUpdate(enabled_sources=[]).enabled_sources == []


class TestGetSettings:
    @pytest.mark.asyncio
    async def test_the_settings_are_returned_without_the_key(self):
        with _licensed(), _Service():
            out = await cve.get_cve_refresh_settings(db=_FakeSession())
        assert out.id == str(SETTINGS_ID)
        assert out.enabled is True
        assert out.enabled_sources == ["nvd", "ubuntu"]
        # Write-only: the key must never travel back to the browser.
        assert out.has_nvd_api_key is True
        assert "secret-key" not in out.model_dump_json()

    @pytest.mark.asyncio
    async def test_no_stored_key_reports_false(self):
        with _licensed(), _Service(settings=_settings(nvd_api_key=None)):
            out = await cve.get_cve_refresh_settings(db=_FakeSession())
        assert out.has_nvd_api_key is False

    @pytest.mark.asyncio
    async def test_null_sources_normalise_to_an_empty_list(self):
        with _licensed(), _Service(settings=_settings(enabled_sources=None)):
            out = await cve.get_cve_refresh_settings(db=_FakeSession())
        assert out.enabled_sources == []

    @pytest.mark.asyncio
    async def test_a_service_failure_is_a_500(self):
        def _boom(db):
            raise RuntimeError("db gone")

        with _licensed(), _Service(get_settings=_boom):
            with pytest.raises(HTTPException) as exc:
                await cve.get_cve_refresh_settings(db=_FakeSession())
        assert exc.value.status_code == 500


class TestUpdateSettings:
    async def _put(self, db, update=None, service=None):
        service = service or _Service()
        with _licensed(), service:
            out = await cve.update_cve_refresh_settings(
                update or cve.CveRefreshSettingsUpdate(enabled=False),
                db=db,
                current_user="admin@invalid",
            )
        return out, service

    @pytest.mark.asyncio
    async def test_an_admin_can_change_the_settings(self):
        db = _FakeSession(User=[_user()])
        out, service = await self._put(
            db, cve.CveRefreshSettingsUpdate(enabled=False, refresh_interval_hours=48)
        )
        assert service.settings.enabled is False
        assert service.settings.refresh_interval_hours == 48
        assert out.refresh_interval_hours == 48

    @pytest.mark.asyncio
    async def test_the_response_still_hides_the_key(self):
        db = _FakeSession(User=[_user()])
        out, _ = await self._put(
            db, cve.CveRefreshSettingsUpdate(nvd_api_key="brand-new-key")
        )
        assert out.has_nvd_api_key is True
        assert "brand-new-key" not in out.model_dump_json()

    @pytest.mark.asyncio
    async def test_an_unknown_user_is_a_401(self):
        with pytest.raises(HTTPException) as exc:
            await self._put(_FakeSession())
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_a_non_admin_is_a_403(self):
        db = _FakeSession(User=[_user(is_admin=False)])
        with pytest.raises(HTTPException) as exc:
            await self._put(db)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_a_service_level_value_error_is_a_400(self):
        def _boom(db, **kwargs):
            raise ValueError("interval conflicts with the schedule")

        db = _FakeSession(User=[_user()])
        with pytest.raises(HTTPException) as exc:
            await self._put(db, service=_Service(update_settings=_boom))
        # Surfaced verbatim so the operator can see which value was refused.
        assert exc.value.status_code == 400
        assert "interval conflicts" in exc.value.detail

    @pytest.mark.asyncio
    async def test_an_unexpected_failure_is_a_500(self):
        def _boom(db, **kwargs):
            raise RuntimeError("db gone")

        db = _FakeSession(User=[_user()])
        with pytest.raises(HTTPException) as exc:
            await self._put(db, service=_Service(update_settings=_boom))
        assert exc.value.status_code == 500


class TestDatabaseStats:
    @pytest.mark.asyncio
    async def test_the_service_stats_are_projected(self):
        with _licensed(), _Service():
            out = await cve.get_database_stats(db=_FakeSession())
        assert out.total_cves == 10
        assert out.total_package_mappings == 20
        assert out.severity_counts == {"HIGH": 5}

    @pytest.mark.asyncio
    async def test_a_service_failure_is_a_500(self):
        def _boom(db):
            raise RuntimeError("db gone")

        with _licensed(), _Service(get_database_stats=_boom):
            with pytest.raises(HTTPException) as exc:
                await cve.get_database_stats(db=_FakeSession())
        assert exc.value.status_code == 500


class TestIngestionHistory:
    @pytest.mark.asyncio
    async def test_history_entries_are_serialized(self):
        with _licensed(), _Service():
            out = await cve.get_ingestion_history(db=_FakeSession())
        assert len(out) == 1
        assert out[0].source == "nvd"
        assert out[0].vulnerabilities_processed == 100

    @pytest.mark.asyncio
    async def test_a_failed_ingestion_carries_its_error(self):
        failed = _log(
            status="error", error_message="429 rate limited", completed_at=None
        )
        with _licensed(), _Service(get_ingestion_history=lambda db, limit: [failed]):
            out = await cve.get_ingestion_history(db=_FakeSession())
        assert out[0].status == "error"
        assert out[0].error_message == "429 rate limited"
        assert out[0].completed_at is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("limit", [0, -1, 101, 1000])
    async def test_an_out_of_range_limit_is_a_400(self, limit):
        with _licensed(), _Service():
            with pytest.raises(HTTPException) as exc:
                await cve.get_ingestion_history(limit=limit, db=_FakeSession())
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.parametrize("limit", [1, 100])
    async def test_the_limit_boundaries_are_inclusive(self, limit):
        with _licensed(), _Service():
            assert (
                await cve.get_ingestion_history(limit=limit, db=_FakeSession())
                is not None
            )

    @pytest.mark.asyncio
    async def test_a_service_failure_is_a_500(self):
        def _boom(db, limit):
            raise RuntimeError("db gone")

        with _licensed(), _Service(get_ingestion_history=_boom):
            with pytest.raises(HTTPException) as exc:
                await cve.get_ingestion_history(db=_FakeSession())
        assert exc.value.status_code == 500


class TestTriggerRefresh:
    async def _refresh(self, db, source=None, service=None):
        service = service or _Service()
        with _licensed(), service:
            out = await cve.trigger_cve_refresh(
                background_tasks=None,
                source=source,
                db=db,
                current_user="admin@invalid",
            )
        return out, service

    @pytest.mark.asyncio
    async def test_a_single_source_refresh_reports_just_that_source(self):
        db = _FakeSession(User=[_user()])
        out, service = await self._refresh(db, source="ubuntu")
        assert list(out.sources) == ["ubuntu"]
        assert out.sources["ubuntu"]["status"] == "success"
        assert out.total_vulnerabilities == 7
        assert out.total_packages == 3
        # The stored key is handed to the fetcher, not to the caller.
        assert service.refreshed == [("ubuntu", "secret-key")]

    @pytest.mark.asyncio
    async def test_a_full_refresh_covers_every_enabled_source(self):
        db = _FakeSession(User=[_user()])
        out, service = await self._refresh(db)
        assert [s for s, _ in service.refreshed] == ["nvd", "ubuntu"]
        assert out.total_vulnerabilities == 14
        assert out.errors == []

    @pytest.mark.asyncio
    async def test_no_configured_sources_falls_back_to_all_of_them(self):
        db = _FakeSession(User=[_user()])
        service = _Service(settings=_settings(enabled_sources=None))
        _, service = await self._refresh(db, service=service)
        assert len(service.refreshed) == 6

    @pytest.mark.asyncio
    async def test_one_failing_source_does_not_stop_the_others(self):
        # NVD rate-limits hard; before per-source isolation a single 403
        # there left every other distro's feed stale too.
        async def _refresh_one(db, source, api_key):
            if source == "nvd":
                raise RuntimeError("429 rate limited")
            return {"vulnerabilities_processed": 5, "packages_processed": 2}

        db = _FakeSession(User=[_user()])
        out, _ = await self._refresh(
            db, service=_Service(refresh_from_source=_refresh_one)
        )
        assert out.sources["nvd"]["status"] == "error"
        assert out.sources["ubuntu"]["status"] == "success"
        assert out.total_vulnerabilities == 5

    @pytest.mark.asyncio
    async def test_a_partial_failure_is_reported_not_swallowed(self):
        async def _refresh_one(db, source, api_key):
            if source == "nvd":
                raise RuntimeError("429 rate limited")
            return {"vulnerabilities_processed": 5, "packages_processed": 2}

        db = _FakeSession(User=[_user()])
        out, _ = await self._refresh(
            db, service=_Service(refresh_from_source=_refresh_one)
        )
        # Without this the run looks clean and the operator never learns NVD
        # has been failing for weeks.
        assert len(out.errors) == 1
        assert "nvd" in out.errors[0]
        assert "429 rate limited" in out.errors[0]

    @pytest.mark.asyncio
    async def test_an_unknown_source_is_a_400(self):
        db = _FakeSession(User=[_user()])
        with pytest.raises(HTTPException) as exc:
            await self._refresh(db, source="made-up")
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_an_unknown_user_is_a_401_and_a_non_admin_a_403(self):
        with pytest.raises(HTTPException) as exc:
            await self._refresh(_FakeSession())
        assert exc.value.status_code == 401
        with pytest.raises(HTTPException) as exc:
            await self._refresh(_FakeSession(User=[_user(is_admin=False)]))
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_a_single_source_failure_surfaces_rather_than_reporting_success(self):
        # The single-source path has no per-source isolation on purpose: the
        # caller asked for exactly one feed, so its failure is THE result.
        async def _boom(db, source, api_key):
            raise CveRefreshError("feed unreachable")

        db = _FakeSession(User=[_user()])
        with pytest.raises(HTTPException) as exc:
            await self._refresh(
                db, source="nvd", service=_Service(refresh_from_source=_boom)
            )
        assert exc.value.status_code == 500
        assert "feed unreachable" in exc.value.detail

    @pytest.mark.asyncio
    async def test_an_unexpected_failure_is_a_500(self):
        def _boom(db):
            raise RuntimeError("db gone")

        db = _FakeSession(User=[_user()])
        with pytest.raises(HTTPException) as exc:
            await self._refresh(db, service=_Service(get_settings=_boom))
        assert exc.value.status_code == 500


class TestClearNvdApiKey:
    async def _clear(self, db, service=None):
        service = service or _Service()
        with _licensed(), service:
            out = await cve.clear_nvd_api_key(db=db, current_user="admin@invalid")
        return out, service

    @pytest.mark.asyncio
    async def test_an_admin_can_clear_the_key(self):
        db = _FakeSession(User=[_user()])
        out, service = await self._clear(db)
        assert service.settings.nvd_api_key is None
        assert db.commits == 1
        assert "cleared" in out["message"]

    @pytest.mark.asyncio
    async def test_an_unknown_user_is_a_401_and_a_non_admin_a_403(self):
        with pytest.raises(HTTPException) as exc:
            await self._clear(_FakeSession())
        assert exc.value.status_code == 401
        with pytest.raises(HTTPException) as exc:
            await self._clear(_FakeSession(User=[_user(is_admin=False)]))
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_a_failure_message_carries_no_detail(self):
        def _boom(db):
            raise RuntimeError("api key secret-key rejected")

        db = _FakeSession(User=[_user()])
        with pytest.raises(HTTPException) as exc:
            await self._clear(db, service=_Service(get_settings=_boom))
        assert exc.value.status_code == 500
        # Deliberately generic: an exception raised while handling a
        # credential can carry the credential in its text.
        assert "secret-key" not in exc.value.detail
        assert exc.value.detail == "Failed to clear NVD API key"


class TestResponseUuidCoercion:
    """Both response models declare ``id: str`` over a UUID column."""

    def test_the_settings_id_is_stringified(self):
        out = cve.CveRefreshSettingsResponse(
            id=SETTINGS_ID,
            enabled=True,
            refresh_interval_hours=24,
            enabled_sources=[],
            has_nvd_api_key=False,
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
        assert out.id == str(SETTINGS_ID)

    def test_an_already_string_settings_id_passes_through(self):
        out = cve.CveRefreshSettingsResponse(
            id="s1",
            enabled=True,
            refresh_interval_hours=24,
            enabled_sources=[],
            has_nvd_api_key=False,
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
        assert out.id == "s1"

    def test_the_log_id_is_stringified(self):
        log_id = uuid.uuid4()
        out = cve.IngestionLogResponse(
            id=log_id, source="nvd", started_at=datetime(2026, 1, 1), status="success"
        )
        assert out.id == str(log_id)

    def test_an_already_string_log_id_passes_through(self):
        out = cve.IngestionLogResponse(
            id="l1", source="nvd", started_at=datetime(2026, 1, 1), status="success"
        )
        assert out.id == "l1"
