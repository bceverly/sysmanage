"""Tests for the Phase 15.1 transient-VaultError retry (OpenBAO lease path)."""

import pytest

from backend.services import vault_service
from backend.services.vault_service import VaultError, run_with_vault_retry


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(vault_service.time, "sleep", slept.append)
    return slept


def _transient(msg="server 5xx"):
    return VaultError(msg, status_code=503, transient=True)


def _permanent(msg="permission denied"):
    return VaultError(msg, status_code=403, transient=False)


def test_vaulterror_defaults_are_permanent():
    exc = VaultError("boom")
    assert exc.transient is False
    assert exc.status_code is None


def test_retries_transient_then_succeeds(_no_real_sleep):
    calls = {"n": 0}

    def mint():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _transient()
        return {"lease_id": "abc"}

    assert run_with_vault_retry(mint) == {"lease_id": "abc"}
    assert calls["n"] == 3
    assert _no_real_sleep == [0.5, 1.0]


def test_permanent_vaulterror_not_retried(_no_real_sleep):
    calls = {"n": 0}

    def mint():
        calls["n"] += 1
        raise _permanent()

    with pytest.raises(VaultError):
        run_with_vault_retry(mint)
    assert calls["n"] == 1  # surfaced immediately
    assert _no_real_sleep == []


def test_gives_up_after_max_attempts(_no_real_sleep):
    calls = {"n": 0}

    def mint():
        calls["n"] += 1
        raise _transient()

    with pytest.raises(VaultError):
        run_with_vault_retry(mint, max_attempts=3)
    assert calls["n"] == 3
    assert len(_no_real_sleep) == 2


def test_passes_through_args_and_return():
    def echo(role):
        return f"creds-for-{role}"

    assert run_with_vault_retry(echo, "tenant-42") == "creds-for-tenant-42"


def test_non_vault_error_not_caught(_no_real_sleep):
    def mint():
        raise ValueError("not a vault error")

    with pytest.raises(ValueError):
        run_with_vault_retry(mint)
    assert _no_real_sleep == []
