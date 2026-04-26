"""
Tests for backend.api.handlers.infrastructure_handlers.

These four async handlers receive websocket messages from agents and persist
the resulting state. The tests below mock the SQLAlchemy session and the
agent connection so we can drive each branch (host-not-found, validation
error, duplicate execution, success path, exception → rollback) without
spinning up the real DB or the websocket layer.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.api.handlers.infrastructure_handlers import (
    handle_host_certificates_update,
    handle_host_role_data_update,
    handle_reboot_status_update,
    handle_script_execution_result,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _connection(host_id="conn-host-id", hostname="conn-host.example"):
    c = MagicMock()
    c.host_id = host_id
    c.hostname = hostname
    return c


def _query_chain(returned_first):
    """Build a mock that resolves db.query().filter().first() == returned_first."""
    chain = MagicMock()
    chain.filter.return_value.first.return_value = returned_first
    return chain


def _query_chain_with_in(returned_first):
    """db.query().filter().filter().first() == returned_first (script duplicate)."""
    chain = MagicMock()
    chain.filter.return_value.filter.return_value.first.return_value = returned_first
    chain.filter.return_value.first.return_value = returned_first
    return chain


def _validate_host_id_ok():
    """Patch helper — validate_host_id returns True (host registered)."""
    return patch(
        "backend.utils.host_validation.validate_host_id",
        new=AsyncMock(return_value=True),
    )


def _validate_host_id_fail():
    return patch(
        "backend.utils.host_validation.validate_host_id",
        new=AsyncMock(return_value=False),
    )


# ---------------------------------------------------------------------------
# handle_script_execution_result
# ---------------------------------------------------------------------------


class TestScriptExecutionResult:
    @pytest.mark.asyncio
    async def test_returns_error_when_host_id_invalid(self):
        db = MagicMock()
        with _validate_host_id_fail():
            result = await handle_script_execution_result(
                db,
                _connection(),
                {"host_id": "bogus", "execution_id": "x", "hostname": "h"},
            )
        assert result["error_type"] == "host_not_registered"

    @pytest.mark.asyncio
    async def test_returns_error_when_no_execution_id(self):
        result = await handle_script_execution_result(
            MagicMock(), _connection(), {"hostname": "h"}
        )
        assert result["error_type"] == "missing_execution_id"

    @pytest.mark.asyncio
    async def test_duplicate_execution_uuid_short_circuits(self):
        db = MagicMock()
        # First query (duplicate-check on execution_uuid) returns an existing row.
        existing = MagicMock(status="completed")
        db.query.return_value.filter.return_value.filter.return_value.first.return_value = (
            existing
        )

        result = await handle_script_execution_result(
            db,
            _connection(),
            {
                "host_id": None,  # Skip validate_host_id branch.
                "execution_id": "exec-1",
                "execution_uuid": "uuid-1",
                "hostname": "h",
            },
        )
        assert result["error_type"] == "duplicate_execution"
        # No add() should have happened.
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_hostname_when_no_connection_host_id(self):
        db = MagicMock()
        # No execution_uuid → skip duplicate check; no hostname → branch.
        connection = _connection(host_id=None, hostname=None)
        # query for ScriptExecutionLog returns None (no dup) and no host found.
        # We'll bypass duplicate-check by not setting execution_uuid.
        result = await handle_script_execution_result(
            db,
            connection,
            {
                "execution_id": "exec-1",
                # no execution_uuid, no hostname → missing_hostname error
            },
        )
        assert result["error_type"] == "missing_hostname"

    @pytest.mark.asyncio
    async def test_host_not_found_by_hostname(self):
        db = MagicMock()
        connection = _connection(host_id=None)
        # Two queries: ScriptExecutionLog (no row), Host by ilike (no row).
        # Set up the chained mocks. db.query returns the same MagicMock so any
        # follow-up filter().first() must resolve to None for both.
        db.query.return_value.filter.return_value.first.return_value = None

        result = await handle_script_execution_result(
            db,
            connection,
            {
                "execution_id": "exec-1",
                "hostname": "missing.example",
            },
        )
        assert result["error_type"] == "host_not_found"

    @pytest.mark.asyncio
    async def test_updates_existing_execution_log_on_success(self):
        db = MagicMock()
        connection = _connection(host_id="h-1")
        host = MagicMock(id="h-1", fqdn="h.example")
        execution_log = MagicMock(started_at=None)

        # query call sequence:
        #  1. ScriptExecutionLog dup check by execution_id → first() depends on
        #     filter().first(); but we have to be careful with chains.
        # Simpler: have any query().filter().first() return host or execution
        # depending on a side-effect counter.
        call_count = {"n": 0}

        def filter_side_effect(*a, **kw):
            inner = MagicMock()
            # Two patterns:
            #   .filter().first()        — host lookup or execution lookup
            #   .filter().filter().first() — script_uuid dedup (skipped here)
            inner.filter.return_value.first.return_value = None  # dedup
            return inner

        # Pattern walk: db.query(Host).filter(Host.id == ...).first() → host
        # then db.query(ScriptExecutionLog).filter(...).first() → execution_log
        responses = [host, execution_log]

        def query_side_effect(model):
            chain = MagicMock()

            def filter_first(*args, **kwargs):
                v = chain  # placeholder
                return _ChainResult()

            class _ChainResult:
                def first(self_inner):
                    return responses.pop(0) if responses else None

                def filter(self_inner, *a, **kw):
                    return _ChainResult()

            chain.filter.return_value = _ChainResult()
            return chain

        db.query.side_effect = query_side_effect

        with patch("backend.api.handlers.infrastructure_handlers.AuditService"):
            result = await handle_script_execution_result(
                db,
                connection,
                {
                    "execution_id": "exec-2",
                    "hostname": "h.example",
                    "success": True,
                    "exit_code": 0,
                    "stdout": "ok",
                    "stderr": "",
                    "shell_used": "bash",
                    "execution_time": 1.5,
                },
            )

        assert result["message_type"] == "script_execution_result_stored"
        assert execution_log.status == "completed"
        assert execution_log.exit_code == 0
        # started_at is set when previously None.
        assert execution_log.started_at is not None
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_creates_new_execution_log_when_none_exists_and_marks_failed(
        self,
    ):
        db = MagicMock()
        connection = _connection(host_id="h-1")
        host = MagicMock(id="h-1", fqdn="h.example")
        responses = [host, None]  # host found, no execution_log

        def query_side_effect(model):
            class _Chain:
                def filter(self_inner, *a, **kw):
                    return self_inner

                def first(self_inner):
                    return responses.pop(0) if responses else None

            return _Chain()

        db.query.side_effect = query_side_effect

        with patch("backend.api.handlers.infrastructure_handlers.AuditService"):
            result = await handle_script_execution_result(
                db,
                connection,
                {
                    "execution_id": "exec-3",
                    "hostname": "h.example",
                    "success": False,
                    "exit_code": 1,
                    "stderr": "boom",
                    "shell_used": "bash",
                },
            )

        assert result["message_type"] == "script_execution_result_stored"
        # add() was called for the new ScriptExecutionLog row.
        assert db.add.called
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception_during_processing_rolls_back(self):
        db = MagicMock()
        # Make any query call blow up so the outer try-except triggers.
        db.query.side_effect = RuntimeError("db down")
        result = await handle_script_execution_result(
            db,
            _connection(host_id=None),
            {"execution_id": "exec-1", "hostname": "h"},
        )
        assert result["error_type"] == "operation_failed"
        db.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# handle_reboot_status_update
# ---------------------------------------------------------------------------


class TestRebootStatusUpdate:
    @pytest.mark.asyncio
    async def test_validate_host_id_failure(self):
        db = MagicMock()
        with _validate_host_id_fail():
            result = await handle_reboot_status_update(
                db,
                _connection(),
                {"host_id": "bogus", "hostname": "h"},
            )
        assert result["error_type"] == "host_not_registered"

    @pytest.mark.asyncio
    async def test_host_not_found(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = await handle_reboot_status_update(
            db,
            _connection(),
            {"hostname": "missing.example"},
        )
        assert result["error_type"] == "host_not_found"

    @pytest.mark.asyncio
    async def test_protected_reboot_reason_is_preserved(self):
        db = MagicMock()
        host = MagicMock(
            reboot_required=True,
            reboot_required_reason="WSL feature enablement pending",
        )
        db.query.return_value.filter.return_value.first.return_value = host
        result = await handle_reboot_status_update(
            db,
            _connection(),
            {"hostname": "h", "reboot_required": False},
        )
        assert result["message_type"] == "reboot_status_preserved"
        # The host row was NOT mutated.
        assert host.reboot_required is True

    @pytest.mark.asyncio
    async def test_updates_status_with_reason(self):
        db = MagicMock()
        host = MagicMock(reboot_required=False, reboot_required_reason=None)
        db.query.return_value.filter.return_value.first.return_value = host
        result = await handle_reboot_status_update(
            db,
            _connection(),
            {
                "hostname": "h",
                "reboot_required": True,
                "reboot_required_reason": "kernel update",
            },
        )
        assert result["message_type"] == "reboot_status_updated"
        assert host.reboot_required is True
        assert host.reboot_required_reason == "kernel update"
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_clearing_reboot_required_clears_reason(self):
        db = MagicMock()
        host = MagicMock(
            reboot_required=True,
            reboot_required_reason="some old reason",  # NOT in protected list
        )
        db.query.return_value.filter.return_value.first.return_value = host
        await handle_reboot_status_update(
            db, _connection(), {"hostname": "h", "reboot_required": False}
        )
        assert host.reboot_required is False
        assert host.reboot_required_reason is None

    @pytest.mark.asyncio
    async def test_falls_back_to_connection_info_hostname(self):
        db = MagicMock()
        host = MagicMock(reboot_required=False, reboot_required_reason=None)
        # No top-level hostname → the first hostname-query branch is skipped
        # entirely, and the _connection_info branch runs the only query.
        db.query.return_value.filter.return_value.first.return_value = host
        result = await handle_reboot_status_update(
            db,
            _connection(),
            {
                "_connection_info": {"hostname": "via-conn-info.example"},
                "reboot_required": True,
            },
        )
        assert result["message_type"] == "reboot_status_updated"

    @pytest.mark.asyncio
    async def test_exception_rolls_back(self):
        db = MagicMock()
        db.query.side_effect = RuntimeError("boom")
        result = await handle_reboot_status_update(db, _connection(), {"hostname": "h"})
        assert result["error_type"] == "operation_failed"
        db.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# handle_host_certificates_update
# ---------------------------------------------------------------------------


class TestHostCertificatesUpdate:
    @pytest.mark.asyncio
    async def test_validate_host_id_failure(self):
        with _validate_host_id_fail():
            result = await handle_host_certificates_update(
                MagicMock(),
                _connection(),
                {"host_id": "bogus", "certificates": []},
            )
        assert result["error_type"] == "host_not_registered"

    @pytest.mark.asyncio
    async def test_host_identification_failure(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        # No connection.hostname AND no agent_host_id → no host found.
        connection = _connection(hostname=None)
        result = await handle_host_certificates_update(
            db, connection, {"certificates": []}
        )
        assert result["error_type"] == "host_identification_failed"

    @pytest.mark.asyncio
    async def test_stores_well_formed_certificates(self):
        db = MagicMock()
        host = MagicMock(id="h-1", fqdn="h.example")
        db.query.return_value.filter.return_value.first.return_value = host

        cert = {
            "file_path": "/etc/ssl/x.pem",
            "certificate_name": "x",
            "subject": "CN=x",
            "issuer": "CN=ca",
            "not_before": "2024-01-01T00:00:00Z",
            "not_after": "2099-01-01T00:00:00Z",
            "serial_number": "01",
            "fingerprint_sha256": "deadbeef",
            "is_ca": False,
            "key_usage": "digitalSignature",
        }
        result = await handle_host_certificates_update(
            db,
            _connection(),
            {"certificates": [cert], "collected_at": "2025-01-01T00:00:00Z"},
        )
        assert result["status"] == "processed"
        assert result["certificates_stored"] == 1
        # delete() then add() then commit().
        db.add.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_malformed_certificates_but_continues(self):
        db = MagicMock()
        host = MagicMock(id="h-1", fqdn="h.example")
        db.query.return_value.filter.return_value.first.return_value = host

        # First cert has invalid date → datetime.fromisoformat raises.
        # Second cert is fine.
        certs = [
            {"file_path": "/bad.pem", "not_before": "not-a-date"},
            {"file_path": "/good.pem"},
        ]
        result = await handle_host_certificates_update(
            db, _connection(), {"certificates": certs}
        )
        # Only the good cert was added.
        assert result["certificates_stored"] == 1

    @pytest.mark.asyncio
    async def test_exception_rolls_back(self):
        db = MagicMock()
        db.query.side_effect = RuntimeError("boom")
        result = await handle_host_certificates_update(
            db, _connection(), {"certificates": []}
        )
        assert result["error_type"] == "operation_failed"
        db.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# handle_host_role_data_update
# ---------------------------------------------------------------------------


class TestHostRoleDataUpdate:
    @pytest.mark.asyncio
    async def test_validate_host_id_failure(self):
        with _validate_host_id_fail():
            result = await handle_host_role_data_update(
                MagicMock(),
                _connection(),
                {"host_id": "bogus", "roles": []},
            )
        assert result["error_type"] == "host_not_registered"

    @pytest.mark.asyncio
    async def test_host_identification_failure(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = await handle_host_role_data_update(
            db, _connection(hostname=None), {"roles": []}
        )
        assert result["error_type"] == "host_identification_failed"

    @pytest.mark.asyncio
    async def test_stores_roles_with_collection_timestamp(self):
        db = MagicMock()
        host = MagicMock(id="h-1", fqdn="h.example")
        db.query.return_value.filter.return_value.first.return_value = host

        role_data = {
            "role": "web-server",
            "package_name": "nginx",
            "package_version": "1.24",
            "service_name": "nginx",
            "service_status": "running",
            "is_active": True,
        }
        result = await handle_host_role_data_update(
            db,
            _connection(),
            {
                "roles": [role_data],
                "collection_timestamp": "2025-01-01T00:00:00Z",
            },
        )
        assert result["status"] == "processed"
        assert result["roles_stored"] == 1
        db.add.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_malformed_role_entry_continues(self):
        db = MagicMock()
        host = MagicMock(id="h-1", fqdn="h.example")
        db.query.return_value.filter.return_value.first.return_value = host

        # The per-role try/except wraps construction. Patch the module-level
        # HostRole symbol so the first call raises and the second succeeds.
        call = {"n": 0}

        def fake_host_role(*a, **kw):
            call["n"] += 1
            if call["n"] == 1:
                raise RuntimeError("synthetic role parse error")
            return MagicMock()

        with patch(
            "backend.api.handlers.infrastructure_handlers.HostRole",
            side_effect=fake_host_role,
        ):
            result = await handle_host_role_data_update(
                db,
                _connection(),
                {
                    "roles": [
                        {"role": "bad", "package_name": "x"},
                        {"role": "good", "package_name": "y"},
                    ],
                },
            )
        # Exactly one role survived.
        assert result["roles_stored"] == 1

    @pytest.mark.asyncio
    async def test_exception_rolls_back(self):
        db = MagicMock()
        db.query.side_effect = RuntimeError("boom")
        result = await handle_host_role_data_update(db, _connection(), {"roles": []})
        assert result["error_type"] == "operation_failed"
        db.rollback.assert_called_once()
