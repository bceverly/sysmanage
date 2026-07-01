"""Tests for backend/api/logging_settings.py PUT glue (Phase 13.3).

Focus: turning an OS family's override off (omitting it from the payload) must
delete its stored row and push a revert-to-yaml to that family's agents.
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.api import logging_settings as mod
from backend.api.logging_settings import (
    LoggingConfig,
    UpdateLoggingSettingsRequest,
    update_logging_settings,
)


def _admin():
    user = MagicMock()
    user.is_admin = True
    return user


def _patched_session():
    """A _sessionmaker() whose () yields a context-manager mock session."""
    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    session_local = MagicMock(return_value=session)
    return session, session_local


@pytest.mark.asyncio
async def test_override_off_deletes_and_reverts():
    """agents={} (all overrides off) → every family deleted → reverts pushed."""
    session, session_local = _patched_session()
    body = UpdateLoggingSettingsRequest(server=None, agents={})

    # Only "linux" actually had a row to delete.
    def fake_delete(_db, family):
        return family == "linux"

    with patch.object(mod, "_sessionmaker", return_value=session_local), patch.object(
        mod.svc, "delete_agent_setting", side_effect=fake_delete
    ), patch.object(mod.svc, "apply_server_native_logging"), patch.object(
        mod.svc, "resolve_server_logging", return_value={}
    ), patch.object(
        mod.svc, "push_logging_to_all_agents"
    ) as push, patch.object(
        mod, "_build_response", return_value={"ok": True}
    ), patch.object(
        mod.config, "get_config", return_value={}
    ):
        result = await update_logging_settings(body, current_user=_admin())

    assert result == {"ok": True}
    push.assert_called_once()
    assert push.call_args.kwargs["revert_families"] == ["linux"]


@pytest.mark.asyncio
async def test_agents_none_does_not_prune():
    """agents=None (server-only save) leaves agent rows untouched."""
    session, session_local = _patched_session()
    body = UpdateLoggingSettingsRequest(
        server=LoggingConfig(native_enabled=False), agents=None
    )

    with patch.object(mod, "_sessionmaker", return_value=session_local), patch.object(
        mod.svc, "upsert_setting"
    ), patch.object(mod.svc, "delete_agent_setting") as delete, patch.object(
        mod.svc, "apply_server_native_logging"
    ), patch.object(
        mod.svc, "resolve_server_logging", return_value={}
    ), patch.object(
        mod.svc, "push_logging_to_all_agents"
    ) as push, patch.object(
        mod, "_build_response", return_value={}
    ), patch.object(
        mod.config, "get_config", return_value={}
    ):
        await update_logging_settings(body, current_user=_admin())

    delete.assert_not_called()
    assert push.call_args.kwargs["revert_families"] == []


@pytest.mark.asyncio
async def test_kept_family_not_reverted():
    """A family present in the payload is upserted, not deleted/reverted."""
    session, session_local = _patched_session()
    body = UpdateLoggingSettingsRequest(
        server=None,
        agents={"linux": LoggingConfig(native_enabled=True, native_target="auto")},
    )

    with patch.object(mod, "_sessionmaker", return_value=session_local), patch.object(
        mod.svc, "upsert_setting"
    ) as upsert, patch.object(
        mod.svc, "delete_agent_setting", return_value=False
    ) as delete, patch.object(
        mod, "_validate_target"
    ), patch.object(
        mod.svc, "apply_server_native_logging"
    ), patch.object(
        mod.svc, "resolve_server_logging", return_value={}
    ), patch.object(
        mod.svc, "push_logging_to_all_agents"
    ) as push, patch.object(
        mod, "_build_response", return_value={}
    ), patch.object(
        mod.config, "get_config", return_value={}
    ):
        await update_logging_settings(body, current_user=_admin())

    upsert.assert_called_once()  # linux upserted
    # linux kept; the other three families are delete-probed (all absent → False).
    assert delete.call_count == 3
    assert push.call_args.kwargs["revert_families"] == []
