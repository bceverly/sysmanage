"""Tests for the air-gap collection schedule periodic-tick service."""

# pylint: disable=missing-class-docstring,missing-function-docstring,protected-access

import asyncio
import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.persistence import models
from backend.services import airgap_schedule_tick as tick_module


@contextmanager
def _engines(*, collector=True, automation=True):
    """Patch module_loader.get_module so engine availability is
    deterministic per test — mirrors the helper in
    tests/api/test_airgap_collection_schedule.py."""

    def _resolver(name):
        if name == "airgap_collector_engine" and collector:
            return MagicMock()
        if name == "automation_engine" and automation:
            mock_auto = MagicMock()
            mock_auto.next_run_from_cron = lambda expr, anchor: anchor.replace(
                tzinfo=None
            ) + timedelta(hours=1)
            return mock_auto
        return None

    with patch.object(tick_module.module_loader, "get_module", side_effect=_resolver):
        yield


def _seed_schedule(
    db_session,
    *,
    name="nightly",
    cron="0 3 * * *",
    enabled=True,
    next_run_delta_seconds=-60,
    target_request=None,
):
    """Insert a schedule row whose ``next_run`` is in the past by
    default (so a tick will fire it)."""
    if target_request is None:
        target_request = {
            "distros": [{"family": "ubuntu", "version": "24.04"}],
            "iso_label": "test-iso",
            "media_size_bytes": 4_700_000_000,
            "include_cve": True,
            "include_compliance": False,
        }
    sched = models.AirgapCollectionSchedule(
        id=uuid.uuid4(),
        name=name,
        cron=cron,
        enabled=enabled,
        target_request_json=json.dumps(target_request),
        next_run=(
            datetime.now(timezone.utc).replace(tzinfo=None)
            + timedelta(seconds=next_run_delta_seconds)
        ),
    )
    db_session.add(sched)
    db_session.commit()
    return sched


class TestRunOneTick:
    def test_no_op_when_collector_engine_absent(self, db_session):
        _seed_schedule(db_session)
        with _engines(collector=False, automation=True):
            summary = tick_module._run_one_tick()
        assert summary == {
            "fired": 0,
            "errors": 0,
            "skipped_automation_absent": False,
        }
        # Schedule was untouched.
        schedule = db_session.query(models.AirgapCollectionSchedule).one()
        assert schedule.last_status is None

    def test_fires_due_schedule(self, db_session):
        sched = _seed_schedule(db_session)
        sched_id = sched.id

        # Wrap the session so the production code's ``db.close()`` is
        # absorbed (the test still needs the session for verification).
        class _NonClosingWrapper:
            def __init__(self, inner):
                self._inner = inner

            def __getattr__(self, name):
                return getattr(self._inner, name)

            def close(self):
                pass  # noqa: PIE790

        wrapped = _NonClosingWrapper(db_session)
        with _engines(collector=True, automation=True), patch.object(
            tick_module, "get_db", return_value=iter([wrapped])
        ):
            summary = tick_module._run_one_tick()
        assert summary["fired"] == 1
        assert summary["errors"] == 0
        # Re-fetch from the same session (the wrapper kept it alive).
        sched_after = (
            db_session.query(models.AirgapCollectionSchedule)
            .filter(models.AirgapCollectionSchedule.id == sched_id)
            .one()
        )
        assert sched_after.last_status == "QUEUED"
        assert sched_after.last_run is not None
        assert sched_after.last_run_id is not None
        # And a run row was created.
        run = (
            db_session.query(models.AirgapCollectionRun)
            .filter(models.AirgapCollectionRun.id == sched_after.last_run_id)
            .one()
        )
        assert run.status == "QUEUED"
        assert run.iso_label == "test-iso"
        assert run.include_cve is True

    def test_skips_disabled_schedule(self, db_session):
        _seed_schedule(db_session, enabled=False)

        class _NonClosingWrapper:
            def __init__(self, inner):
                self._inner = inner

            def __getattr__(self, name):
                return getattr(self._inner, name)

            def close(self):
                pass  # noqa: PIE790

        wrapped = _NonClosingWrapper(db_session)
        with _engines(collector=True, automation=True), patch.object(
            tick_module, "get_db", return_value=iter([wrapped])
        ):
            summary = tick_module._run_one_tick()
        assert summary["fired"] == 0

    def test_skips_future_next_run(self, db_session):
        _seed_schedule(db_session, next_run_delta_seconds=600)

        class _NonClosingWrapper:
            def __init__(self, inner):
                self._inner = inner

            def __getattr__(self, name):
                return getattr(self._inner, name)

            def close(self):
                pass  # noqa: PIE790

        wrapped = _NonClosingWrapper(db_session)
        with _engines(collector=True, automation=True), patch.object(
            tick_module, "get_db", return_value=iter([wrapped])
        ):
            summary = tick_module._run_one_tick()
        assert summary["fired"] == 0

    def test_malformed_target_request_marks_failure(self, db_session):
        sched = _seed_schedule(db_session)
        sched_id = sched.id
        sched.target_request_json = "not-json{"
        db_session.commit()

        class _NonClosingWrapper:
            def __init__(self, inner):
                self._inner = inner

            def __getattr__(self, name):
                return getattr(self._inner, name)

            def close(self):
                pass  # noqa: PIE790

        wrapped = _NonClosingWrapper(db_session)
        with _engines(collector=True, automation=True), patch.object(
            tick_module, "get_db", return_value=iter([wrapped])
        ):
            summary = tick_module._run_one_tick()
        assert summary["fired"] == 0
        assert summary["errors"] == 1
        sched_after = (
            db_session.query(models.AirgapCollectionSchedule)
            .filter(models.AirgapCollectionSchedule.id == sched_id)
            .one()
        )
        assert sched_after.last_status == "FAILURE"

    def test_automation_engine_absent_skips_next_run_advance(self, db_session):
        sched = _seed_schedule(db_session)
        sched_id = sched.id
        original_next_run = sched.next_run

        class _NonClosingWrapper:
            def __init__(self, inner):
                self._inner = inner

            def __getattr__(self, name):
                return getattr(self._inner, name)

            def close(self):
                pass  # noqa: PIE790

        wrapped = _NonClosingWrapper(db_session)
        with _engines(collector=True, automation=False), patch.object(
            tick_module, "get_db", return_value=iter([wrapped])
        ):
            summary = tick_module._run_one_tick()
        assert summary["fired"] == 1
        assert summary["skipped_automation_absent"] is True
        sched_after = (
            db_session.query(models.AirgapCollectionSchedule)
            .filter(models.AirgapCollectionSchedule.id == sched_id)
            .one()
        )
        # next_run unchanged because automation engine couldn't advance it.
        assert sched_after.next_run == original_next_run


class TestTickServiceLoop:
    @pytest.mark.asyncio
    async def test_service_calls_run_one_tick_repeatedly(self):
        call_count = 0

        def _fake_tick():
            nonlocal call_count
            call_count += 1
            return {"fired": 0, "errors": 0, "skipped_automation_absent": False}

        with patch.object(
            tick_module, "_run_one_tick", side_effect=_fake_tick
        ), patch.object(tick_module, "TICK_INTERVAL_SECONDS", 0.01):
            task = asyncio.create_task(tick_module.airgap_schedule_tick_service())
            # Yield long enough for several tick iterations.
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                _ = await task  # assignment placates py/ineffectual-statement
        # At least 2 iterations should have completed in 50ms with a 10ms cadence.
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_service_survives_inner_exception(self):
        call_count = 0

        def _flaky_tick():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient DB hiccup")
            return {"fired": 0, "errors": 0, "skipped_automation_absent": False}

        # Shorten both the happy-path and error-back-off intervals so
        # the loop iterates fast enough to verify recovery.  Patching
        # the constants is preferred over patching ``asyncio.sleep``
        # itself (which is shared with the test harness).
        with patch.object(
            tick_module, "_run_one_tick", side_effect=_flaky_tick
        ), patch.object(tick_module, "TICK_INTERVAL_SECONDS", 0.005), patch.object(
            tick_module, "ERROR_BACKOFF_SECONDS", 0.005
        ):
            task = asyncio.create_task(tick_module.airgap_schedule_tick_service())
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                _ = await task  # assignment placates py/ineffectual-statement
        # First call raised, subsequent calls succeeded — loop kept going.
        assert call_count >= 2
