# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Tests for the Phase 15.1 transient-DB-error retry helper."""

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from backend.persistence import db_retry


def _op_error(msg="server closed the connection unexpectedly"):
    """Build a realistic transient OperationalError."""
    return OperationalError("SELECT 1", {}, Exception(msg))


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Capture backoff sleeps instead of actually waiting."""
    slept = []
    monkeypatch.setattr(db_retry.time, "sleep", slept.append)
    return slept


def test_succeeds_first_try_no_sleep(_no_real_sleep):
    calls = {"n": 0}

    def op():
        calls["n"] += 1
        return "ok"

    assert db_retry.run_with_db_retry(op) == "ok"
    assert calls["n"] == 1
    assert _no_real_sleep == []  # never backed off


def test_retries_transient_then_succeeds(_no_real_sleep):
    calls = {"n": 0}

    def op():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _op_error()
        return "recovered"

    result = db_retry.run_with_db_retry(op, base_delay=0.5, max_delay=4.0)
    assert result == "recovered"
    assert calls["n"] == 3
    # Two backoffs before the third (successful) attempt: 0.5, then 1.0.
    assert _no_real_sleep == [0.5, 1.0]


def test_gives_up_after_max_attempts(_no_real_sleep):
    calls = {"n": 0}

    def op():
        calls["n"] += 1
        raise _op_error()

    with pytest.raises(OperationalError):
        db_retry.run_with_db_retry(op, max_attempts=3)
    assert calls["n"] == 3  # exactly max_attempts tries
    assert len(_no_real_sleep) == 2  # one fewer sleep than attempts


def test_non_transient_error_not_retried(_no_real_sleep):
    calls = {"n": 0}

    def op():
        calls["n"] += 1
        raise IntegrityError("INSERT", {}, Exception("duplicate key"))

    with pytest.raises(IntegrityError):
        db_retry.run_with_db_retry(op)
    assert calls["n"] == 1  # surfaced immediately, no retry
    assert _no_real_sleep == []


def test_backoff_is_capped_at_max_delay(_no_real_sleep):
    def op():
        raise _op_error()

    with pytest.raises(OperationalError):
        db_retry.run_with_db_retry(op, max_attempts=5, base_delay=1.0, max_delay=3.0)
    # 1.0, 2.0, 4.0->capped 3.0, 8.0->capped 3.0
    assert _no_real_sleep == [1.0, 2.0, 3.0, 3.0]


def test_decorator_form_retries(_no_real_sleep):
    calls = {"n": 0}

    @db_retry.with_db_retry(max_attempts=3)
    def op():
        calls["n"] += 1
        if calls["n"] < 2:
            raise _op_error()
        return "ok"

    assert op() == "ok"
    assert calls["n"] == 2


@pytest.fixture
def _no_real_async_sleep(monkeypatch):
    """Capture async backoff sleeps instead of awaiting them."""
    slept = []

    async def _fake_sleep(secs):
        slept.append(secs)

    monkeypatch.setattr(db_retry.asyncio, "sleep", _fake_sleep)
    return slept


@pytest.mark.asyncio
async def test_async_retries_transient_then_succeeds(_no_real_async_sleep):
    calls = {"n": 0}

    async def op():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _op_error()
        return "recovered"

    result = await db_retry.run_with_db_retry_async(op)
    assert result == "recovered"
    assert calls["n"] == 3
    assert _no_real_async_sleep == [0.5, 1.0]


@pytest.mark.asyncio
async def test_async_non_transient_not_retried(_no_real_async_sleep):
    calls = {"n": 0}

    async def op():
        calls["n"] += 1
        raise IntegrityError("INSERT", {}, Exception("dup"))

    with pytest.raises(IntegrityError):
        await db_retry.run_with_db_retry_async(op)
    assert calls["n"] == 1
    assert _no_real_async_sleep == []


@pytest.mark.asyncio
async def test_async_gives_up_after_max_attempts(_no_real_async_sleep):
    async def op():
        raise _op_error()

    with pytest.raises(OperationalError):
        await db_retry.run_with_db_retry_async(op, max_attempts=3)
    assert len(_no_real_async_sleep) == 2
