# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Not safe to reboot (2026-11-19): three production hosts were left with a
half-configured kernel and no initramfs, one reboot from not booting.  The
agent's verdict is stored on the host; a person's reboot is refused with it,
and an automatic one waits until the host is safe."""

# pylint: disable=redefined-outer-name,unused-argument

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from backend.api.update_handlers import handle_update_apply_result
from backend.persistence import models
from backend.services import auto_update_results, reboot_safety
from backend.services import package_manager_repair as repair
from tests.services.test_auto_update_runner import (  # noqa: F401  pylint: disable=unused-import
    _automation,
    _commands,
    _host,
    _now,
    _policy,
    _tick,
    _update,
)

UNSAFE = {
    "manager": "dpkg", "needs_repair": True, "repairable": True,
    "reason": "Packages not fully installed: linux-image-7.0.0-44-generic",
    "reboot_unsafe": True,
    "reboot_unsafe_reason": "Not safe to reboot: linux-image-7.0.0-44-generic "
    "is only partly installed",
}  # fmt: skip
SAFE = {"manager": "dpkg", "needs_repair": False, "repairable": True,
        "reboot_unsafe": False, "reboot_unsafe_reason": None}  # fmt: skip


def test_the_scan_sets_and_clears_the_verdict(session):
    host = _host(session)
    assert repair.store(host, UNSAFE) is True
    assert host.reboot_unsafe and "linux-image" in host.reboot_unsafe_reason
    assert reboot_safety.reason(host) == host.reboot_unsafe_reason
    repair.store(host, SAFE)
    assert not host.reboot_unsafe and host.reboot_unsafe_reason is None
    assert reboot_safety.reason(host) is None


def test_an_older_agent_leaves_the_verdict_alone(session):
    host = _host(session)
    reboot_safety.store(host, UNSAFE)
    old = {k: v for k, v in SAFE.items() if not k.startswith("reboot")}
    assert reboot_safety.store(host, old) is False
    assert host.reboot_unsafe is True


def test_a_persons_reboot_is_refused_with_the_reason(session):
    host = _host(session)
    reboot_safety.store(host, UNSAFE)
    with pytest.raises(HTTPException) as refused:
        reboot_safety.refuse_if_unsafe(host)
    assert refused.value.status_code == 409
    assert "linux-image-7.0.0-44-generic" in refused.value.detail
    reboot_safety.store(host, SAFE)
    reboot_safety.refuse_if_unsafe(host)  # no longer raises


@pytest.fixture(name="mock_connection")
def _mock_connection():
    connection = MagicMock()
    connection.websocket = AsyncMock()
    return connection


@pytest.mark.asyncio
async def test_an_automatic_reboot_waits_until_the_host_is_safe(
    session, automation, mock_connection
):
    host = _host(session)
    _update(session, host, "linux-image-generic")
    _policy(session, reboot_mode="when_needed")
    session.commit()
    _tick(session, automation)
    reboot_safety.store(host, UNSAFE)
    session.commit()

    mock_connection.host_id = host.id
    await handle_update_apply_result(
        session,
        mock_connection,
        {
            "hostname": "web1",
            "updated_packages": [
                {"package_name": "linux-image-generic", "package_manager": "apt"}
            ],
            "failed_packages": [],
            "requires_reboot": True,
        },
    )
    session.expire_all()
    run = session.query(models.AutoUpdateRun).one()
    assert run.reboot_status == auto_update_results.UNSAFE
    assert _commands(session, host, "reboot_system") == []

    # Still unsafe: it keeps waiting.
    auto_update_results.follow_reboots(session, automation, _now())
    assert session.query(models.AutoUpdateRun).one().reboot_status == "unsafe"

    # Repaired: the next follow-up sends the one reboot.
    host = session.get(models.Host, host.id)
    reboot_safety.store(host, SAFE)
    host.reboot_required = True
    session.commit()
    auto_update_results.follow_reboots(session, automation, _now())
    session.commit()  # the tick commits; follow_reboots leaves it to it
    session.expire_all()
    assert session.query(models.AutoUpdateRun).one().reboot_status == "queued"
    assert len(_commands(session, host, "reboot_system")) == 1


def test_the_reboot_endpoints_refuse(session):
    """The single-host, fleet and orchestrated reboots all ask first."""
    import inspect  # pylint: disable=import-outside-toplevel

    from backend.api import fleet, host_operations, reboot_orchestration

    for module, func in (
        (host_operations, host_operations.reboot_host),
        (fleet, fleet.reboot_system),
        (reboot_orchestration, reboot_orchestration.orchestrated_reboot),
    ):
        assert "reboot_safety.refuse_if_unsafe(host)" in inspect.getsource(
            func
        ), module.__name__


def test_the_columns_come_and_go_idempotently():
    import os  # pylint: disable=import-outside-toplevel
    import tempfile  # pylint: disable=import-outside-toplevel

    from tests.test_backup_proxy_migration import (  # pylint: disable=import-outside-toplevel
        _columns,
    )
    from tests.test_backup_rules_migration import (  # pylint: disable=import-outside-toplevel
        _alembic,
    )

    wanted = {"reboot_unsafe", "reboot_unsafe_reason"}
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        assert wanted <= set(_columns(db_path, "host"))
        _alembic(["stamp", "q97fedbackuprollup"], db_path)
        _alembic(["upgrade", "head"], db_path)  # again: nothing to add
        _alembic(["downgrade", "q97fedbackuprollup"], db_path)
        assert not wanted & set(_columns(db_path, "host"))
        _alembic(["upgrade", "head"], db_path)
        assert wanted <= set(_columns(db_path, "host"))
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_the_health_message_reaches_the_host_on_its_own(session):
    """2026-11-19: health rode only on the update scan, so a half-configured
    kernel showed healthy for hours; now it is its own message."""
    from types import SimpleNamespace  # pylint: disable=import-outside-toplevel

    from backend.websocket.message_router import (  # pylint: disable=import-outside-toplevel
        route_inbound_message,
    )
    from backend.websocket.messages import (  # pylint: disable=import-outside-toplevel
        MessageType,
    )

    host = _host(session)
    session.commit()
    connection = SimpleNamespace(host_id=host.id)
    assert await route_inbound_message(
        MessageType.PACKAGE_MANAGER_HEALTH, session, connection,
        {**UNSAFE, "host_id": str(host.id)},
    )  # fmt: skip
    session.expire_all()
    host = session.get(models.Host, host.id)
    assert host.package_manager_needs_repair and host.reboot_unsafe
    await route_inbound_message(
        MessageType.PACKAGE_MANAGER_HEALTH, session, connection, dict(SAFE)
    )
    session.expire_all()
    host = session.get(models.Host, host.id)
    assert not host.package_manager_needs_repair and not host.reboot_unsafe


def _manual_log(session, host, name, age_hours, run_id=None):
    from datetime import timedelta  # pylint: disable=import-outside-toplevel

    when = _now() - timedelta(hours=age_hours)
    session.add(models.PackageUpdate(
        host_id=host.id, package_name=name, current_version="1", available_version="2",
        package_manager="apt", update_type="security", status="updating",
        discovered_at=when, created_at=when, updated_at=when,
    ))  # fmt: skip
    session.add(models.UpdateExecutionLog(
        host_id=host.id, package_name=name, package_manager="apt",
        from_version="1", to_version="2", execution_status="pending",
        created_at=when, updated_at=when, run_id=run_id,
    ))  # fmt: skip
    session.commit()


def test_a_manual_update_the_host_never_answered_times_out(session):
    """2026-11-19: seven hosts never answered an "update all", and their
    packages stayed "updating" with no end -- manual runs had no timeout."""
    from backend.services import (
        auto_update_runner,
    )  # pylint: disable=import-outside-toplevel

    host = _host(session)
    _manual_log(session, host, "old-pkg", auto_update_runner.RUN_TIMEOUT_HOURS + 1)
    _manual_log(session, host, "new-pkg", 1)
    assert auto_update_runner.expire_stale_manual(session, _now()) == 1
    session.commit()
    logs = {log.package_name: log for log in session.query(models.UpdateExecutionLog)}
    assert logs["old-pkg"].execution_status == "failed"
    assert logs["old-pkg"].error_log == "The host never reported the result"
    assert logs["new-pkg"].execution_status == "pending"
    statuses = {u.package_name: u.status for u in session.query(models.PackageUpdate)}
    assert statuses == {"old-pkg": "failed", "new-pkg": "updating"}


def test_an_automatic_runs_logs_are_left_to_its_own_timeout(session):
    import uuid  # pylint: disable=import-outside-toplevel

    from backend.services import (
        auto_update_runner,
    )  # pylint: disable=import-outside-toplevel

    host = _host(session)
    _manual_log(session, host, "auto-pkg", 100, run_id=uuid.uuid4())
    assert auto_update_runner.expire_stale_manual(session, _now()) == 0


def test_the_manual_timeout_runs_without_the_automation_engine(session, monkeypatch):
    """Community has no automation engine; the timeout must still run."""
    from backend.services import (
        auto_update_runner,
    )  # pylint: disable=import-outside-toplevel

    host = _host(session)
    _manual_log(session, host, "old-pkg", auto_update_runner.RUN_TIMEOUT_HOURS + 1)
    monkeypatch.setattr(auto_update_runner, "engine", lambda: None)
    monkeypatch.setattr(
        auto_update_runner, "iter_host_databases",
        lambda: iter([("default", None, session)]),
    )  # fmt: skip
    monkeypatch.setattr(session, "close", lambda: None)
    assert auto_update_runner.run_one_tick()["timed_out"] == 1
