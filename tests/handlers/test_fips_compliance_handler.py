# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for backend.api.handlers.os_hardware_handlers.handle_fips_compliance_update
(Phase 14.4 — OSS FIPS posture ingestion).

The DB is mocked; the test exercises the orchestration (validation, prefix
stripping, the UPDATE payload) rather than the SQL itself.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.api.handlers.os_hardware_handlers import handle_fips_compliance_update


def _connection(host_id="conn-host-id"):
    c = MagicMock()
    c.host_id = host_id
    return c


class TestHandleFipsComplianceUpdate:
    @pytest.mark.asyncio
    async def test_no_connection_host_id_errors(self):
        db = MagicMock()
        conn = _connection(host_id=None)
        result = await handle_fips_compliance_update(db, conn, {})
        assert result["error_type"] == "host_not_registered"
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_bad_agent_host_id_errors(self):
        db = MagicMock()
        conn = _connection()
        with patch(
            "backend.utils.host_validation.validate_host_id",
            new=AsyncMock(return_value=False),
        ):
            result = await handle_fips_compliance_update(db, conn, {"host_id": "999"})
        assert result["error_type"] == "host_not_registered"
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_persists_and_strips_prefix(self):
        db = MagicMock()
        conn = _connection()
        message = {
            "status": "enabled",
            "enabled": True,
            "available": True,
            "kernel_enforced": True,
            "vendor": "ubuntu-pro",
            "package_version": "1.2.3",
        }
        result = await handle_fips_compliance_update(db, conn, message)

        assert result["message_type"] == "ack"
        assert result["data"]["success"] is True
        db.execute.assert_called_once()
        db.commit.assert_called_once()

        # Inspect the values() bound to the UPDATE.
        update_stmt = db.execute.call_args.args[0]
        values = dict(update_stmt.compile().params)
        assert values["fips_status"] == "enabled"
        assert values["fips_enabled"] is True
        assert values["fips_vendor"] == "ubuntu-pro"
        assert values["fips_package_version"] == "1.2.3"
        # fips_updated_at is always stamped.
        assert "fips_updated_at" in values

    @pytest.mark.asyncio
    async def test_omitted_fields_are_not_written(self):
        db = MagicMock()
        conn = _connection()
        # Only status supplied; the rest must be left untouched (not written).
        result = await handle_fips_compliance_update(db, conn, {"status": "disabled"})
        assert result["message_type"] == "ack"
        update_stmt = db.execute.call_args.args[0]
        values = dict(update_stmt.compile().params)
        assert values["fips_status"] == "disabled"
        assert "fips_enabled" not in values
        assert "fips_vendor" not in values
