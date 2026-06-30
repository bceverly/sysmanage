"""Tests for livepatch ingestion in handle_ubuntu_pro_update (Phase 13.3)."""

import json
from unittest.mock import Mock

import pytest

from backend.api.handlers.os_hardware_handlers import handle_ubuntu_pro_update
from backend.persistence import models

HOST_ID = "550e8400-e29b-41d4-a716-4466554400aa"


@pytest.fixture
def sample_host(session):
    host = models.Host(
        id=HOST_ID,
        fqdn="lp-host.example.com",
        ipv4="192.168.1.77",
        active=True,
        platform="Ubuntu",
        platform_release="22.04",
        approval_status="approved",
    )
    session.add(host)
    session.commit()
    return host


def _msg(livepatch):
    pro = {
        "attached": True,
        "version": "35.1",
        "services": [{"name": "livepatch", "status": "enabled", "entitled": True}],
    }
    if livepatch is not None:
        pro["livepatch"] = livepatch
    return {"os_info": {"ubuntu_pro": pro}}


@pytest.mark.asyncio
async def test_stores_livepatch_detail(session, sample_host):
    msg = _msg(
        {
            "enabled": True,
            "client_version": "10.6.1",
            "patch_state": "applied",
            "check_state": "checked",
            "patch_version": "97.1",
            "kernel": "5.15.0-101-generic",
            "last_check": "2026-06-30T12:00:00Z",
            "fixes": ["CVE-2026-1111", "CVE-2026-2222"],
        }
    )
    await handle_ubuntu_pro_update(session, Mock(), msg, sample_host)

    row = (
        session.query(models.UbuntuProInfo)
        .filter(models.UbuntuProInfo.host_id == HOST_ID)
        .first()
    )
    assert row.livepatch_enabled is True
    assert row.livepatch_client_version == "10.6.1"
    assert row.livepatch_patch_state == "applied"
    assert row.livepatch_patch_version == "97.1"
    assert row.livepatch_kernel == "5.15.0-101-generic"
    assert row.livepatch_last_check is not None
    assert json.loads(row.livepatch_fixes) == ["CVE-2026-1111", "CVE-2026-2222"]


@pytest.mark.asyncio
async def test_no_livepatch_leaves_columns_empty(session, sample_host):
    await handle_ubuntu_pro_update(session, Mock(), _msg(None), sample_host)

    row = (
        session.query(models.UbuntuProInfo)
        .filter(models.UbuntuProInfo.host_id == HOST_ID)
        .first()
    )
    assert row.livepatch_enabled is False
    assert row.livepatch_client_version is None
    assert row.livepatch_fixes is None


@pytest.mark.asyncio
async def test_bad_last_check_is_tolerated(session, sample_host):
    msg = _msg({"enabled": True, "last_check": "not-a-date", "fixes": []})
    await handle_ubuntu_pro_update(session, Mock(), msg, sample_host)

    row = (
        session.query(models.UbuntuProInfo)
        .filter(models.UbuntuProInfo.host_id == HOST_ID)
        .first()
    )
    assert row.livepatch_enabled is True
    assert row.livepatch_last_check is None
    assert row.livepatch_fixes is None  # empty list -> stored as NULL
