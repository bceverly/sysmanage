"""Tests for the air-gap collection schedule API (Phase 11 B2)."""

# pylint: disable=missing-class-docstring,missing-function-docstring


import json
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from backend.api import airgap_collection_schedule as sched_module


@contextmanager
def _engines(*, collector=True, automation=True):
    """Patch module_loader.get_module so engine availability is
    deterministic per test."""

    def _resolver(name):
        if name == "airgap_collector_engine" and collector:
            mock_collector = MagicMock()
            mock_collector.CollectorConfigError = type(
                "CollectorConfigError", (ValueError,), {}
            )
            mock_collector.validate_collection_request = lambda req: req
            return mock_collector
        if name == "automation_engine" and automation:
            mock_auto = MagicMock()
            mock_auto.CronParseError = type("CronParseError", (ValueError,), {})

            def _vc(expr):
                if len(expr.split()) != 5:
                    raise mock_auto.CronParseError("bad cron")

            mock_auto.validate_cron_expression = _vc

            from datetime import datetime, timedelta, timezone

            mock_auto.next_run_from_cron = lambda expr, anchor: anchor.replace(
                tzinfo=None
            ) + timedelta(hours=1)
            return mock_auto
        return None

    with patch.object(sched_module.module_loader, "get_module", side_effect=_resolver):
        yield


class TestScheduleAuth:
    def test_list_requires_auth(self, client):
        r = client.get("/api/v1/airgap/collector/schedules")
        assert r.status_code in (401, 403)


class TestScheduleProplusGate:
    def test_list_returns_402_without_collector_engine(self, client, auth_headers):
        with _engines(collector=False, automation=True):
            r = client.get("/api/v1/airgap/collector/schedules", headers=auth_headers)
        assert r.status_code == 402

    def test_create_returns_402_without_collector_engine(self, client, auth_headers):
        with _engines(collector=False, automation=True):
            r = client.post(
                "/api/v1/airgap/collector/schedules",
                json={
                    "name": "nightly",
                    "cron": "0 3 * * *",
                    "target_request": {"distros": [], "iso_label": "x"},
                },
                headers=auth_headers,
            )
        assert r.status_code == 402

    def test_tick_returns_402_without_collector_engine(self, client, auth_headers):
        with _engines(collector=False, automation=True):
            r = client.post(
                "/api/v1/airgap/collector/schedules/tick", headers=auth_headers
            )
        assert r.status_code == 402


class TestScheduleCrud:
    def test_create_with_invalid_cron_400(self, client, auth_headers):
        with _engines():
            r = client.post(
                "/api/v1/airgap/collector/schedules",
                json={
                    "name": "bad-cron",
                    "cron": "not a cron",
                    "target_request": {
                        "distros": [{"distro": "ubuntu", "version": "noble"}]
                    },
                },
                headers=auth_headers,
            )
        assert r.status_code == 400

    def test_create_persists_schedule(self, client, auth_headers, db_session):
        with _engines():
            r = client.post(
                "/api/v1/airgap/collector/schedules",
                json={
                    "name": "nightly",
                    "cron": "0 3 * * *",
                    "target_request": {
                        "distros": [{"distro": "ubuntu", "version": "noble"}],
                        "iso_label": "nightly",
                    },
                },
                headers=auth_headers,
            )
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "nightly"
        assert body["cron"] == "0 3 * * *"
        assert body["enabled"] is True
        # next_run computed via mocked automation engine
        assert body["next_run"] is not None

    def test_list_after_create(self, client, auth_headers):
        with _engines():
            client.post(
                "/api/v1/airgap/collector/schedules",
                json={
                    "name": "weekly",
                    "cron": "0 3 * * 0",
                    "target_request": {
                        "distros": [{"distro": "ubuntu", "version": "noble"}]
                    },
                },
                headers=auth_headers,
            )
            r = client.get("/api/v1/airgap/collector/schedules", headers=auth_headers)
        assert r.status_code == 200
        names = [s["name"] for s in r.json()]
        assert "weekly" in names


class TestScheduleTickAutomationMissing:
    def test_tick_warns_when_automation_engine_absent(
        self, client, auth_headers, db_session
    ):
        # Create schedule with both engines present
        with _engines():
            r = client.post(
                "/api/v1/airgap/collector/schedules",
                json={
                    "name": "t",
                    "cron": "0 3 * * *",
                    "target_request": {
                        "distros": [{"distro": "ubuntu", "version": "noble"}]
                    },
                },
                headers=auth_headers,
            )
            assert r.status_code == 200
        # Tick with collector loaded but automation absent — should warn,
        # not crash.  The schedule's next_run won't advance without
        # automation, but the response is still a clean 200.
        with _engines(collector=True, automation=False):
            r = client.post(
                "/api/v1/airgap/collector/schedules/tick", headers=auth_headers
            )
        assert r.status_code == 200
        body = r.json()
        assert "warning" in body
        assert "automation_engine" in body["warning"]
