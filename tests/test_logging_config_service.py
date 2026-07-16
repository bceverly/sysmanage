# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Tests for backend/services/logging_config_service.py (Phase 13.3)."""

import logging

import pytest

from backend.services import logging_config_service as svc
from backend.persistence.models.logging_config import SCOPE_AGENT, SCOPE_SERVER


class TestOsFamily:
    """os_family_for_system + valid_targets_for_family."""

    def test_family_mapping(self):
        assert svc.os_family_for_system("Windows") == "windows"
        assert svc.os_family_for_system("Darwin") == "macos"
        assert svc.os_family_for_system("FreeBSD") == "bsd"
        assert svc.os_family_for_system("OpenBSD") == "bsd"
        assert svc.os_family_for_system("Linux") == "linux"
        assert svc.os_family_for_system(None) == "linux"

    def test_valid_targets(self):
        assert "journald" in svc.valid_targets_for_family("linux")
        assert "eventlog" in svc.valid_targets_for_family("windows")
        assert "journald" not in svc.valid_targets_for_family("windows")
        assert "syslog" in svc.valid_targets_for_family("macos")

    def test_syslog_remote_valid_for_every_family(self):
        """syslog_remote is network-based → offered on every family incl. Windows."""
        for family in ("linux", "windows", "macos", "bsd"):
            assert "syslog_remote" in svc.valid_targets_for_family(family)


class TestResolveServer:
    """resolve_server_logging — DB wins over yaml."""

    def test_yaml_fallback(self, db_session):
        resolved = svc.resolve_server_logging(
            db_session,
            {"native": True, "native_target": "syslog", "level": "INFO"},
        )
        assert resolved["native_enabled"] is True
        assert resolved["native_target"] == "syslog"
        assert resolved["log_level"] == "INFO"

    def test_db_wins(self, db_session):
        svc.upsert_setting(
            db_session,
            SCOPE_SERVER,
            None,
            {"native_enabled": True, "native_target": "journald", "log_level": "DEBUG"},
        )
        db_session.commit()
        resolved = svc.resolve_server_logging(
            db_session, {"native": False, "native_target": "syslog"}
        )
        assert resolved["native_target"] == "journald"
        assert resolved["native_enabled"] is True
        assert resolved["log_level"] == "DEBUG"


class TestResolveAgent:
    """resolve_agent_logging + upsert."""

    def test_unset_returns_none(self, db_session):
        assert svc.resolve_agent_logging(db_session, "linux") is None

    def test_set_and_update(self, db_session):
        svc.upsert_setting(
            db_session,
            SCOPE_AGENT,
            "linux",
            {"native_enabled": True, "native_target": "auto", "verbosity": "high"},
        )
        db_session.commit()
        out = svc.resolve_agent_logging(db_session, "linux")
        assert out["native_enabled"] is True
        assert out["verbosity"] == "high"

        # update in place (no duplicate row)
        svc.upsert_setting(
            db_session,
            SCOPE_AGENT,
            "linux",
            {"native_enabled": False, "native_target": "syslog"},
        )
        db_session.commit()
        out2 = svc.resolve_agent_logging(db_session, "linux")
        assert out2["native_enabled"] is False
        assert out2["native_target"] == "syslog"

    def test_syslog_remote_fields_round_trip(self, db_session):
        """The remote-syslog fields survive upsert → resolve → agent payload."""
        svc.upsert_setting(
            db_session,
            SCOPE_AGENT,
            "linux",
            {
                "native_enabled": True,
                "native_target": "syslog_remote",
                "syslog_host": "loghost.example",
                "syslog_port": 6514,
                "syslog_facility": "local0",
                "syslog_protocol": "tcp",
            },
        )
        db_session.commit()
        out = svc.resolve_agent_logging(db_session, "linux")
        assert out["syslog_host"] == "loghost.example"
        assert out["syslog_port"] == 6514
        assert out["syslog_facility"] == "local0"
        assert out["syslog_protocol"] == "tcp"

        payload = svc._agent_payload(out)
        assert payload["native_target"] == "syslog_remote"
        assert payload["syslog_host"] == "loghost.example"
        assert payload["syslog_port"] == 6514
        assert payload["syslog_protocol"] == "tcp"


class TestDeleteAgent:
    """delete_agent_setting removes a row so the OS reverts to yaml."""

    def test_delete_existing_returns_true(self, db_session):
        svc.upsert_setting(db_session, SCOPE_AGENT, "linux", {"native_enabled": True})
        db_session.commit()
        assert svc.resolve_agent_logging(db_session, "linux") is not None

        assert svc.delete_agent_setting(db_session, "linux") is True
        db_session.commit()
        assert svc.resolve_agent_logging(db_session, "linux") is None

    def test_delete_missing_returns_false(self, db_session):
        assert svc.delete_agent_setting(db_session, "windows") is False


class TestEnqueueRevert:
    """_enqueue_logging_update sends an empty override to mean 'revert to yaml'."""

    def test_none_resolved_sends_empty_payload(self):
        from unittest.mock import MagicMock, patch

        fake_queue = MagicMock()
        with patch(
            "backend.websocket.queue_operations.QueueOperations",
            return_value=fake_queue,
        ):
            svc._enqueue_logging_update(MagicMock(), "host-1", None)

        assert fake_queue.enqueue_message.call_count == 1
        sent = fake_queue.enqueue_message.call_args.kwargs["message_data"]
        assert sent["data"] == {"logging": {}}

    def test_resolved_sends_full_payload(self):
        from unittest.mock import MagicMock, patch

        fake_queue = MagicMock()
        resolved = {"native_enabled": True, "native_target": "syslog"}
        with patch(
            "backend.websocket.queue_operations.QueueOperations",
            return_value=fake_queue,
        ):
            svc._enqueue_logging_update(MagicMock(), "host-1", resolved)

        sent = fake_queue.enqueue_message.call_args.kwargs["message_data"]
        assert sent["data"]["logging"]["native_enabled"] is True


class TestPushRevert:
    """push_logging_to_all_agents reverts agents of a removed OS family."""

    def test_revert_family_enqueues_empty_override(self):
        from unittest.mock import MagicMock, patch

        host = MagicMock()
        host.id = "host-linux"
        host.platform = "Linux"
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [host]

        calls = []
        # iter_host_databases is imported lazily from backend.persistence.partitions.
        with patch.object(svc, "_main_session", return_value=MagicMock()), patch.object(
            svc, "resolve_agent_logging", return_value=None
        ), patch(
            "backend.persistence.partitions.iter_host_databases",
            return_value=[("bootstrap", None, session)],
        ), patch.object(
            svc,
            "_enqueue_logging_update",
            side_effect=lambda db, hid, resolved: calls.append((hid, resolved)),
        ):
            count = svc.push_logging_to_all_agents(revert_families=["linux"])

        assert count == 1
        assert calls == [("host-linux", None)]  # None => revert to yaml


class TestApplyServerNative:
    """apply_server_native_logging attaches/removes the native handler."""

    @pytest.fixture(autouse=True)
    def _restore_root(self):
        root = logging.getLogger()
        saved = root.handlers[:]
        yield
        for handler in root.handlers[:]:
            if getattr(handler, "_sysmanage_native", False):
                handler.close()
                root.removeHandler(handler)
        # restore any of ours we removed (none expected) — saved is reference
        _ = saved

    def _native_handlers(self):
        return [
            h
            for h in logging.getLogger().handlers
            if getattr(h, "_sysmanage_native", False)
        ]

    def test_enabled_adds_then_disabled_removes(self):
        from unittest.mock import patch

        fake = logging.StreamHandler()
        with patch.object(svc, "build_native_handler", return_value=fake):
            svc.apply_server_native_logging(
                {"native_enabled": True, "native_target": "syslog"}
            )
        assert fake in logging.getLogger().handlers
        assert getattr(fake, "_sysmanage_native", False) is True

        # Re-apply disabled → the previously-added native handler is removed.
        svc.apply_server_native_logging({"native_enabled": False})
        assert self._native_handlers() == []

    def test_reapply_replaces_not_duplicates(self):
        from unittest.mock import patch

        with patch.object(
            svc, "build_native_handler", side_effect=lambda **_: logging.StreamHandler()
        ):
            svc.apply_server_native_logging(
                {"native_enabled": True, "native_target": "syslog"}
            )
            svc.apply_server_native_logging(
                {"native_enabled": True, "native_target": "syslog"}
            )
        assert len(self._native_handlers()) == 1
