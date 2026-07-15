"""Tests for backend/api/fips_actions.py — FIPS enable/disable dispatch and the
fleet posture read (Phase 14.4)."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.api import fips_actions as mod
from backend.api.fips_actions import (
    FipsChangeRequest,
    disable_fips,
    enable_fips,
    fleet_fips_posture,
    host_fips_status,
)
from backend.persistence import models


def _seed_host(db, **over):
    host_id = uuid.uuid4()
    fields = dict(
        id=host_id,
        fqdn="fips-host.example.com",
        ipv4="192.168.1.91",
        active=True,
        platform="Ubuntu",
        platform_release="22.04",
        approval_status="approved",
    )
    fields.update(over)
    db.add(models.Host(**fields))
    db.commit()
    return host_id


def _fake_engine(plan):
    """A stand-in compliance_engine whose plan_fips_change returns a fixed dict."""
    engine = MagicMock()
    engine.plan_fips_change.return_value = plan
    return engine


def _license_on():
    """Patch the license gate + module loader to a permissive fake engine."""
    return (
        patch.object(mod.license_service, "has_feature", return_value=True),
        patch.object(mod.license_service, "has_module", return_value=True),
    )


@pytest.mark.asyncio
async def test_unlicensed_is_402(db_session):
    with patch.object(mod.license_service, "has_feature", return_value=False):
        with pytest.raises(HTTPException) as exc:
            await enable_fips(
                str(uuid.uuid4()),
                FipsChangeRequest(),
                tenant_db=db_session,
                current_user="admin@example.com",
            )
    assert exc.value.status_code == 402


@pytest.mark.asyncio
async def test_module_missing_is_503(db_session):
    with patch.object(
        mod.license_service, "has_feature", return_value=True
    ), patch.object(mod.license_service, "has_module", return_value=True), patch.object(
        mod.module_loader, "get_module", return_value=None
    ):
        with pytest.raises(HTTPException) as exc:
            await enable_fips(
                str(uuid.uuid4()),
                FipsChangeRequest(),
                tenant_db=db_session,
                current_user="admin@example.com",
            )
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_missing_host_is_404(db_session):
    with patch.object(
        mod.license_service, "has_feature", return_value=True
    ), patch.object(mod.license_service, "has_module", return_value=True), patch.object(
        mod.module_loader, "get_module", return_value=_fake_engine({})
    ):
        with pytest.raises(HTTPException) as exc:
            await enable_fips(
                str(uuid.uuid4()),
                FipsChangeRequest(),
                tenant_db=db_session,
                current_user="admin@example.com",
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_engine_rejection_is_400(db_session):
    host_id = _seed_host(db_session)
    engine = MagicMock()
    engine.plan_fips_change.side_effect = ValueError("FIPS mode is not available")
    with patch.object(
        mod.license_service, "has_feature", return_value=True
    ), patch.object(mod.license_service, "has_module", return_value=True), patch.object(
        mod.module_loader, "get_module", return_value=engine
    ):
        with pytest.raises(HTTPException) as exc:
            await enable_fips(
                str(host_id),
                FipsChangeRequest(),
                tenant_db=db_session,
                current_user="admin@example.com",
            )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_enable_dispatches_command(db_session):
    host_id = _seed_host(db_session)
    plan = {
        "method": "ubuntu-pro",
        "method_label": "Ubuntu Pro",
        "enable": True,
        "reboot_required": True,
        "parameters": {"method": "ubuntu-pro", "vendor": "ubuntu-pro", "enable": True},
    }
    engine = _fake_engine(plan)
    with patch.object(
        mod.license_service, "has_feature", return_value=True
    ), patch.object(mod.license_service, "has_module", return_value=True), patch.object(
        mod.module_loader, "get_module", return_value=engine
    ), patch.object(
        mod.queue_ops, "enqueue_message"
    ) as enqueue, patch.object(
        mod.AuditService, "log"
    ):
        result = await enable_fips(
            str(host_id),
            FipsChangeRequest(),
            tenant_db=db_session,
            current_user="admin@example.com",
        )

    assert result["result"] is True
    assert result["plan"] == plan
    engine.plan_fips_change.assert_called_once()
    # enable=True was threaded to the engine.
    assert engine.plan_fips_change.call_args.kwargs["enable"] is True
    kwargs = enqueue.call_args.kwargs
    assert kwargs["message_type"] == "command"
    assert kwargs["host_id"] == str(host_id)
    cmd = kwargs["message_data"]
    payload = cmd.get("data", cmd)
    assert payload["command_type"] == "fips_enable"
    assert payload["parameters"]["method"] == "ubuntu-pro"


@pytest.mark.asyncio
async def test_disable_dispatches_command(db_session):
    host_id = _seed_host(db_session, fips_enabled=True)
    plan = {
        "method": "rhel",
        "enable": False,
        "reboot_required": True,
        "parameters": {"method": "rhel", "vendor": "rhel", "enable": False},
    }
    engine = _fake_engine(plan)
    with patch.object(
        mod.license_service, "has_feature", return_value=True
    ), patch.object(mod.license_service, "has_module", return_value=True), patch.object(
        mod.module_loader, "get_module", return_value=engine
    ), patch.object(
        mod.queue_ops, "enqueue_message"
    ) as enqueue, patch.object(
        mod.AuditService, "log"
    ):
        result = await disable_fips(
            str(host_id),
            FipsChangeRequest(),
            tenant_db=db_session,
            current_user="admin@example.com",
        )

    assert result["result"] is True
    assert engine.plan_fips_change.call_args.kwargs["enable"] is False
    payload = enqueue.call_args.kwargs["message_data"]
    payload = payload.get("data", payload)
    assert payload["command_type"] == "fips_disable"


@pytest.mark.asyncio
async def test_host_status_returns_posture(db_session):
    host_id = _seed_host(
        db_session, fips_status="enabled", fips_enabled=True, fips_vendor="rhel"
    )
    with patch.object(mod.license_service, "has_feature", return_value=True):
        result = await host_fips_status(
            str(host_id), tenant_db=db_session, current_user="admin@example.com"
        )
    assert result["host_id"] == str(host_id)
    assert result["fips_status"] == "enabled"
    assert result["fips_enabled"] is True
    assert result["fips_vendor"] == "rhel"


@pytest.mark.asyncio
async def test_host_status_null_is_not_applicable(db_session):
    host_id = _seed_host(db_session, fips_status=None)
    with patch.object(mod.license_service, "has_feature", return_value=True):
        result = await host_fips_status(
            str(host_id), tenant_db=db_session, current_user="admin@example.com"
        )
    assert result["fips_status"] == "not_applicable"


@pytest.mark.asyncio
async def test_host_status_missing_is_404(db_session):
    with patch.object(mod.license_service, "has_feature", return_value=True):
        with pytest.raises(HTTPException) as exc:
            await host_fips_status(
                str(uuid.uuid4()),
                tenant_db=db_session,
                current_user="admin@example.com",
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_host_status_unlicensed_is_402(db_session):
    with patch.object(mod.license_service, "has_feature", return_value=False):
        with pytest.raises(HTTPException) as exc:
            await host_fips_status(
                str(uuid.uuid4()),
                tenant_db=db_session,
                current_user="admin@example.com",
            )
    assert exc.value.status_code == 402


@pytest.mark.asyncio
async def test_fleet_posture_counts(db_session):
    _seed_host(db_session, fqdn="a.example.com", ipv4="10.0.0.1", fips_status="enabled")
    _seed_host(db_session, fqdn="b.example.com", ipv4="10.0.0.2", fips_status="enabled")
    _seed_host(
        db_session, fqdn="c.example.com", ipv4="10.0.0.3", fips_status="disabled"
    )
    _seed_host(db_session, fqdn="d.example.com", ipv4="10.0.0.4", fips_status=None)

    with patch.object(mod.license_service, "has_feature", return_value=True):
        result = await fleet_fips_posture(
            tenant_db=db_session, current_user="admin@example.com"
        )

    assert result["total"] == 4
    assert result["counts"]["enabled"] == 2
    assert result["counts"]["disabled"] == 1
    # A null status is bucketed as not_applicable.
    assert result["counts"]["not_applicable"] == 1
    assert len(result["hosts"]) == 4


@pytest.mark.asyncio
async def test_fleet_posture_unlicensed_is_402(db_session):
    with patch.object(mod.license_service, "has_feature", return_value=False):
        with pytest.raises(HTTPException) as exc:
            await fleet_fips_posture(
                tenant_db=db_session, current_user="admin@example.com"
            )
    assert exc.value.status_code == 402
