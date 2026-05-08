"""
Tests for the Phase 8.2 upgrade-profile API + cron parser.

The cron parser tests live alongside the API tests because they're
the same delivery slice.  Phase 10.6 moved the cron parser and per-host
dispatch into the Pro+ ``automation_engine`` Cython module; the OSS
``upgrade_scheduler`` shims still re-export the helpers so these tests
can keep importing from there, but the API routes now go through the
engine.  CRUD/trigger/tick tests use ``_engine_loaded`` to satisfy the
``_check_automation_module`` gate.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.services import upgrade_scheduler

# ----------------------------------------------------------------------
# Cron parser unit tests (no DB)
# ----------------------------------------------------------------------


class TestCronParse:
    def test_simple_daily(self):
        m, h, dom, mon, dow = upgrade_scheduler.parse_cron("0 3 * * *")
        assert m == {0}
        assert h == {3}
        assert dom == set(range(1, 32))
        assert mon == set(range(1, 13))
        assert dow == set(range(0, 7))

    def test_step_minutes(self):
        m, *_ = upgrade_scheduler.parse_cron("*/15 * * * *")
        assert m == {0, 15, 30, 45}

    def test_range_with_step(self):
        _, h, *_ = upgrade_scheduler.parse_cron("0 0-23/2 * * *")
        assert h == {0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22}

    def test_list_and_range(self):
        m, h, *_ = upgrade_scheduler.parse_cron("0 9-17 * * 1-5")
        assert m == {0}
        assert h == set(range(9, 18))

    def test_day_names(self):
        *_, dow = upgrade_scheduler.parse_cron("0 3 * * mon")
        assert dow == {1}

    def test_sunday_is_zero_or_seven(self):
        *_, dow0 = upgrade_scheduler.parse_cron("0 3 * * 0")
        *_, dow7 = upgrade_scheduler.parse_cron("0 3 * * 7")
        assert dow0 == dow7 == {0}

    def test_invalid_field_count(self):
        with pytest.raises(upgrade_scheduler.CronParseError):
            upgrade_scheduler.parse_cron("0 3 * *")

    def test_invalid_token(self):
        with pytest.raises(upgrade_scheduler.CronParseError):
            upgrade_scheduler.parse_cron("0 abc * * *")

    def test_out_of_range(self):
        with pytest.raises(upgrade_scheduler.CronParseError):
            upgrade_scheduler.parse_cron("60 * * * *")


class TestNextRun:
    """next_run_from_cron is the load-bearing piece — verify the most
    common patterns produce monotonically-increasing future timestamps."""

    def test_daily_at_3am(self):
        anchor = datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc)
        nxt = upgrade_scheduler.next_run_from_cron("0 3 * * *", anchor)
        # Should fire 03:00 the NEXT day (since anchor is 12:00 already past 03:00 today)
        assert nxt.hour == 3
        assert nxt.minute == 0
        assert nxt > anchor.replace(tzinfo=None)

    def test_every_15_minutes(self):
        anchor = datetime(2026, 4, 29, 12, 7, tzinfo=timezone.utc)
        nxt = upgrade_scheduler.next_run_from_cron("*/15 * * * *", anchor)
        # Next quarter-hour after 12:08 (anchor + 1m) is 12:15.
        assert nxt == datetime(2026, 4, 29, 12, 15)

    def test_weekday_business_hours(self):
        # 0 9-17 * * 1-5: Tuesday at 17:30 → next is Tuesday 09:00... wait,
        # 9-17 includes 17 so "Tuesday at 17:30" → next is Wed 09:00.
        anchor = datetime(2026, 4, 28, 17, 30, tzinfo=timezone.utc)  # Tuesday
        nxt = upgrade_scheduler.next_run_from_cron("0 9-17 * * 1-5", anchor)
        # 17:30 → 18:00 won't match (out of 9-17 hour set), so next is
        # Wed 09:00.  Validate it's a business-hour minute on a weekday.
        assert nxt.hour in range(9, 18)
        assert nxt.weekday() in range(0, 5)
        assert nxt > anchor.replace(tzinfo=None)

    def test_validate_cron_accepts_default(self):
        # validate_cron should not raise on the schema default
        upgrade_scheduler.validate_cron("0 3 * * *")

    def test_validate_cron_rejects_garbage(self):
        with pytest.raises(upgrade_scheduler.CronParseError):
            upgrade_scheduler.validate_cron("not a cron")


# ----------------------------------------------------------------------
# API tests (use the test client + auth headers)
# ----------------------------------------------------------------------


class TestUpgradeProfilesAuth:
    def test_list_requires_auth(self, client):
        r = client.get("/api/upgrade-profiles")
        assert r.status_code in [401, 403]

    def test_create_requires_auth(self, client):
        r = client.post("/api/upgrade-profiles", json={"name": "no-auth"})
        assert r.status_code in [401, 403]


class TestUpgradeProfilesProplusGate:
    """When ``automation_engine`` isn't loaded, every route returns 402."""

    @pytest.fixture
    def _engine_absent(self):
        with patch(
            "backend.api.upgrade_profiles.module_loader.get_module",
            return_value=None,
        ):
            yield

    def test_list_returns_402(self, client, auth_headers, _engine_absent):
        r = client.get("/api/upgrade-profiles", headers=auth_headers)
        assert r.status_code == 402

    def test_create_returns_402(self, client, auth_headers, _engine_absent):
        r = client.post(
            "/api/upgrade-profiles",
            json={"name": "x"},
            headers=auth_headers,
        )
        assert r.status_code == 402

    def test_trigger_returns_402(self, client, auth_headers, _engine_absent):
        r = client.post(
            "/api/upgrade-profiles/00000000-0000-0000-0000-000000000000/trigger",
            headers=auth_headers,
        )
        assert r.status_code == 402

    def test_tick_returns_402(self, client, auth_headers, _engine_absent):
        r = client.post("/api/upgrade-profiles/tick", headers=auth_headers)
        assert r.status_code == 402


# ----------------------------------------------------------------------
# Engine-loaded fixture for route tests.
#
# Phase 10.6 gates every route on ``automation_engine`` being loaded.
# These tests don't exercise the real Cython .so — they verify route
# behaviour, so we hand the route a MagicMock whose methods delegate to
# the OSS ``upgrade_scheduler`` (cron) and a small inline implementation
# of ``build_upgrade_profile_dispatch`` (the engine version is itself a
# port of the OSS logic).  The Pro+ engine's own tests cover the
# Cython implementation under ``module-source/automation_engine/``.
# ----------------------------------------------------------------------


def _build_dispatch_oss(profile, host_ids):
    """OSS-side mirror of automation_engine.build_upgrade_profile_dispatch."""
    if not host_ids:
        return []
    window_min = profile.get("staggered_window_min") or 0
    n = len(host_ids)
    pkg_str = profile.get("package_managers")
    package_managers = pkg_str.split(",") if pkg_str else None
    out = []
    for idx, host_id in enumerate(host_ids):
        delay_seconds = int((idx * window_min * 60) / n) if window_min > 0 else 0
        out.append(
            {
                "host_id": str(host_id),
                "command_type": "apply_updates",
                "parameters": {
                    "profile_id": str(profile["id"]),
                    "profile_name": profile.get("name", ""),
                    "security_only": bool(profile.get("security_only")),
                    "package_managers": package_managers,
                    "delay_seconds": delay_seconds,
                },
            }
        )
    return out


@pytest.fixture
def _engine_loaded():
    """Patch ``module_loader.get_module`` so the ``_check_automation_module``
    gate inside upgrade_profiles routes finds an engine surface."""
    mock_engine = MagicMock()
    mock_engine.validate_cron_expression = upgrade_scheduler.validate_cron
    mock_engine.next_run_from_cron = upgrade_scheduler.next_run_from_cron
    mock_engine.CronParseError = upgrade_scheduler.CronParseError
    mock_engine.build_upgrade_profile_dispatch = _build_dispatch_oss
    with patch(
        "backend.api.upgrade_profiles.module_loader.get_module",
        return_value=mock_engine,
    ):
        yield mock_engine


class TestUpgradeProfilesCrud:
    @pytest.fixture(autouse=True)
    def _gate(self, _engine_loaded):
        yield

    def test_create_with_default_cron(self, client, auth_headers):
        r = client.post(
            "/api/upgrade-profiles",
            json={"name": "daily-3am"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"] == "daily-3am"
        assert body["cron"] == "0 3 * * *"
        assert body["next_run"] is not None

    def test_create_with_invalid_cron_400(self, client, auth_headers):
        r = client.post(
            "/api/upgrade-profiles",
            json={"name": "bad-cron", "cron": "not a cron"},
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_create_with_security_only(self, client, auth_headers):
        r = client.post(
            "/api/upgrade-profiles",
            json={"name": "sec-only", "security_only": True},
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json()["security_only"] is True

    def test_list_after_create(self, client, auth_headers):
        client.post(
            "/api/upgrade-profiles",
            json={"name": "weekly"},
            headers=auth_headers,
        )
        r = client.get("/api/upgrade-profiles", headers=auth_headers)
        assert r.status_code == 200
        names = [p["name"] for p in r.json()]
        assert "weekly" in names

    def test_get_one(self, client, auth_headers):
        created = client.post(
            "/api/upgrade-profiles",
            json={"name": "one-shot"},
            headers=auth_headers,
        ).json()
        r = client.get(f"/api/upgrade-profiles/{created['id']}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["id"] == created["id"]

    def test_update_cron_recomputes_next_run(self, client, auth_headers):
        created = client.post(
            "/api/upgrade-profiles",
            json={"name": "rebench", "cron": "0 3 * * *"},
            headers=auth_headers,
        ).json()
        original_next = created["next_run"]
        r = client.put(
            f"/api/upgrade-profiles/{created['id']}",
            json={"cron": "*/5 * * * *"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json()["cron"] == "*/5 * * * *"
        # next_run should be much sooner now
        assert r.json()["next_run"] != original_next

    def test_delete(self, client, auth_headers):
        created = client.post(
            "/api/upgrade-profiles",
            json={"name": "ephemeral"},
            headers=auth_headers,
        ).json()
        r = client.delete(
            f"/api/upgrade-profiles/{created['id']}", headers=auth_headers
        )
        assert r.status_code == 200


class TestUpgradeProfileTrigger:
    @pytest.fixture(autouse=True)
    def _gate(self, _engine_loaded):
        yield

    def test_trigger_updates_last_run_and_returns_targets(self, client, auth_headers):
        created = client.post(
            "/api/upgrade-profiles",
            json={"name": "fire-now"},
            headers=auth_headers,
        ).json()
        r = client.post(
            f"/api/upgrade-profiles/{created['id']}/trigger",
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["profile_id"] == created["id"]
        assert "host_count" in body
        assert "host_ids" in body
        assert body["next_run"] is not None

        # Verify last_run was set.
        get_resp = client.get(
            f"/api/upgrade-profiles/{created['id']}", headers=auth_headers
        )
        assert get_resp.json()["last_run"] is not None
        assert get_resp.json()["last_status"] == "SUCCESS"

    def test_trigger_unknown_profile_404(self, client, auth_headers):
        r = client.post(
            "/api/upgrade-profiles/00000000-0000-0000-0000-000000000abc/trigger",
            headers=auth_headers,
        )
        assert r.status_code == 404


class TestUpgradeProfileTick:
    @pytest.fixture(autouse=True)
    def _gate(self, _engine_loaded):
        yield

    def test_tick_endpoint_runs(self, client, auth_headers):
        # Create a profile with cron that's already due (every minute).
        client.post(
            "/api/upgrade-profiles",
            json={"name": "everyminute", "cron": "* * * * *"},
            headers=auth_headers,
        )
        r = client.post("/api/upgrade-profiles/tick", headers=auth_headers)
        assert r.status_code == 200
        assert "fired_count" in r.json()
        assert "fired" in r.json()


class TestUpgradeProfileDispatch:
    @pytest.fixture(autouse=True)
    def _gate(self, _engine_loaded):
        yield

    """Phase 8.2 wire-up: trigger and tick must actually queue
    apply_updates command messages, not just update timestamps."""

    def test_trigger_response_carries_enqueued_count(self, client, auth_headers):
        created = client.post(
            "/api/upgrade-profiles",
            json={"name": "real-fire"},
            headers=auth_headers,
        ).json()
        r = client.post(
            f"/api/upgrade-profiles/{created['id']}/trigger",
            headers=auth_headers,
        )
        assert r.status_code == 200
        body = r.json()
        # enqueued_count must be present.  In the unit-test DB, no real
        # hosts exist so it's 0 — that's the expected value.  We're
        # checking the FIELD, not the count.
        assert "enqueued_count" in body
        assert body["enqueued_count"] >= 0

    def test_dispatch_helper_handles_zero_hosts(self, client, auth_headers):
        """Empty target list must not raise — common when a profile is
        scoped to a tag with no current hosts."""
        from backend.api.upgrade_profiles import _dispatch_profile_to_hosts

        from types import SimpleNamespace

        fake_profile = SimpleNamespace(
            id="00000000-0000-0000-0000-000000000001",
            name="empty",
            staggered_window_min=0,
            security_only=False,
            package_managers=None,
        )
        # We pass a None DB — the function returns early on empty list,
        # so the DB is never touched.
        result = _dispatch_profile_to_hosts(fake_profile, [], None)
        assert result == 0
