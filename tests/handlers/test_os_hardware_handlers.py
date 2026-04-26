"""
Tests for backend.api.handlers.os_hardware_handlers.

Covers the OS-version, hardware-update, and Ubuntu-Pro-update handlers.
The DB is fully mocked via MagicMock so the test exercises the orchestration
logic rather than the SQL itself.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.api.handlers.os_hardware_handlers import (
    handle_hardware_update,
    handle_os_version_update,
    is_new_os_version_combination,
)


def _connection(host_id="conn-host-id", hostname="h.example", ipv4="10.0.0.1"):
    c = MagicMock()
    c.host_id = host_id
    c.hostname = hostname
    c.ipv4 = ipv4
    c.send_message = AsyncMock()
    # No websocket attribute by default — tests that need it set it explicitly.
    return c


# ---------------------------------------------------------------------------
# is_new_os_version_combination
# ---------------------------------------------------------------------------


class TestIsNewOsVersionCombination:
    @pytest.mark.asyncio
    async def test_returns_false_when_either_is_blank(self):
        db = MagicMock()
        assert await is_new_os_version_combination(db, "", "1") is False
        assert await is_new_os_version_combination(db, "Ubuntu", "") is False
        assert await is_new_os_version_combination(db, None, None) is False
        # Should not even hit the DB.
        db.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_true_when_no_existing_packages(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        assert await is_new_os_version_combination(db, "Ubuntu", "24.04") is True

    @pytest.mark.asyncio
    async def test_returns_false_when_packages_exist(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = MagicMock()
        assert await is_new_os_version_combination(db, "Ubuntu", "24.04") is False


# ---------------------------------------------------------------------------
# handle_os_version_update
# ---------------------------------------------------------------------------


class TestHandleOsVersionUpdate:
    @pytest.mark.asyncio
    async def test_validate_host_id_failure(self):
        with patch(
            "backend.utils.host_validation.validate_host_id",
            new=AsyncMock(return_value=False),
        ):
            result = await handle_os_version_update(
                MagicMock(), _connection(), {"host_id": "bogus"}
            )
        assert result["error_type"] == "host_not_registered"

    @pytest.mark.asyncio
    async def test_no_identification_at_all_returns_error(self):
        # spec=[] makes hasattr() return False for everything.
        connection = MagicMock(spec=[])
        result = await handle_os_version_update(MagicMock(), connection, {})
        assert result["error_type"] == "no_host_identification"

    @pytest.mark.asyncio
    async def test_resolves_host_id_via_hostname_lookup(self):
        db = MagicMock()
        # Make connection have hostname but no host_id.
        connection = _connection(host_id=None)
        host = MagicMock(
            id="h-1",
            fqdn="h.example",
            platform="Linux",
            platform_release="Ubuntu 24.04",
        )
        # First query: lookup by hostname → returns host. Subsequent: lookup
        # by id → returns the same host. Subsequent: AvailablePackage check.
        responses = [host, host, MagicMock()]  # last triggers "not new"

        def query_side(model):
            class _Chain:
                def filter(self_inner, *a, **kw):
                    return self_inner

                def first(self_inner):
                    return responses.pop(0) if responses else None

            return _Chain()

        db.query.side_effect = query_side
        result = await handle_os_version_update(
            db,
            connection,
            {"platform": "Linux", "platform_release": "Ubuntu 24.04"},
        )
        assert result["message_type"] == "success"
        assert connection.host_id == "h-1"
        # send_message ack went to the agent.
        connection.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_resolves_host_id_via_websocket_client_ip(self):
        db = MagicMock()
        # No host_id, no hostname; only websocket.client.host present.
        # spec=[] would block too much; use specific spec list.
        connection = MagicMock(spec=["websocket", "host_id", "send_message"])
        connection.host_id = None
        connection.send_message = AsyncMock()
        connection.websocket = MagicMock()
        connection.websocket.client = MagicMock(host="10.0.0.5")

        host = MagicMock(
            id="h-2",
            fqdn="found.example",
            platform="Linux",
            platform_release="Ubuntu 24.04",
        )
        # Query sequence:
        #  1. by ipv4 → host (resolves connection.host_id)
        #  2. by id   → host
        #  3. AvailablePackage → existing
        responses = [host, host, MagicMock()]

        def query_side(model):
            class _Chain:
                def filter(self_inner, *a, **kw):
                    return self_inner

                def first(self_inner):
                    return responses.pop(0) if responses else None

            return _Chain()

        db.query.side_effect = query_side
        result = await handle_os_version_update(
            db,
            connection,
            {"platform": "Linux", "platform_release": "Ubuntu 24.04"},
        )
        assert result["message_type"] == "success"
        assert connection.host_id == "h-2"
        assert connection.hostname == "found.example"

    @pytest.mark.asyncio
    async def test_no_os_info_in_message_returns_error(self):
        db = MagicMock()
        host = MagicMock(id="h-1", platform=None, platform_release=None)
        db.query.return_value.filter.return_value.first.return_value = host
        # Empty message_data (after host_id check) means no os_info to apply.
        result = await handle_os_version_update(db, _connection(), {})
        assert result["error_type"] == "no_os_info"

    @pytest.mark.asyncio
    async def test_new_os_combination_triggers_collection_command(self):
        db = MagicMock()
        host = MagicMock(
            id="h-1",
            fqdn="h.example",
            platform="Linux",
            platform_release="Ubuntu 24.04",
        )
        # Query sequence:
        #  1. Host by id → host
        #  2. AvailablePackage check (is_new_os_version_combination) → None (new)
        responses = [host, None]

        def query_side(model):
            class _Chain:
                def filter(self_inner, *a, **kw):
                    return self_inner

                def first(self_inner):
                    return responses.pop(0) if responses else None

            return _Chain()

        db.query.side_effect = query_side

        with patch(
            "backend.api.handlers.os_hardware_handlers.queue_ops"
        ) as qops, patch(
            "backend.api.handlers.os_hardware_handlers.handle_ubuntu_pro_update",
            new=AsyncMock(),
        ):
            result = await handle_os_version_update(
                db,
                _connection(),
                {
                    "platform": "Linux",
                    "platform_release": "Ubuntu 24.04",
                    "os_info": {"distribution": "Ubuntu"},
                },
            )

        assert result["message_type"] == "success"
        # New combo → queue_ops.enqueue_message was called for collection.
        qops.enqueue_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_queue_failure_does_not_abort_update(self):
        """If the auto-collect queue command throws, the OS update itself must
        still be reported as successful — that error is best-effort."""
        db = MagicMock()
        host = MagicMock(
            id="h-1",
            fqdn="h.example",
            platform="Linux",
            platform_release="Ubuntu 24.04",
        )
        responses = [host, None]  # host, "no available packages yet"

        def query_side(model):
            class _Chain:
                def filter(self_inner, *a, **kw):
                    return self_inner

                def first(self_inner):
                    return responses.pop(0) if responses else None

            return _Chain()

        db.query.side_effect = query_side

        with patch(
            "backend.api.handlers.os_hardware_handlers.queue_ops"
        ) as qops, patch(
            "backend.api.handlers.os_hardware_handlers.handle_ubuntu_pro_update",
            new=AsyncMock(),
        ):
            qops.enqueue_message.side_effect = RuntimeError("queue down")
            result = await handle_os_version_update(
                db,
                _connection(),
                {"platform": "Linux", "platform_release": "Ubuntu 24.04"},
            )
        assert result["message_type"] == "success"

    @pytest.mark.asyncio
    async def test_exception_rolls_back_and_returns_failure(self):
        db = MagicMock()
        # Make Host lookup blow up.
        db.query.side_effect = RuntimeError("db down")
        result = await handle_os_version_update(
            db, _connection(), {"platform": "Linux"}
        )
        assert result["error_type"] == "os_update_failed"
        db.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# handle_hardware_update
# ---------------------------------------------------------------------------


class TestHandleHardwareUpdate:
    @pytest.mark.asyncio
    async def test_validate_host_id_failure(self):
        with patch(
            "backend.utils.host_validation.validate_host_id",
            new=AsyncMock(return_value=False),
        ):
            result = await handle_hardware_update(
                MagicMock(), _connection(), {"host_id": "bogus"}
            )
        assert result["error_type"] == "host_not_registered"

    @pytest.mark.asyncio
    async def test_connection_without_host_id_errors(self):
        connection = MagicMock(spec=["host_id"])
        connection.host_id = None
        result = await handle_hardware_update(MagicMock(), connection, {})
        assert result["error_type"] == "host_not_registered"

    @pytest.mark.asyncio
    async def test_writes_cpu_and_memory_fields(self):
        db = MagicMock()
        result = await handle_hardware_update(
            db,
            _connection(),
            {
                "cpu_vendor": "Intel",
                "cpu_model": "Core i7",
                "cpu_cores": 8,
                "cpu_threads": 16,
                "cpu_frequency_mhz": 3200,
                "memory_total_mb": 32768,
            },
        )
        assert result["message_type"] == "success"
        # Two commits in the orchestration: hardware_updates commit + final commit.
        assert db.commit.call_count >= 1

    @pytest.mark.asyncio
    async def test_serializes_hardware_details_dict_as_json(self):
        db = MagicMock()
        await handle_hardware_update(
            db,
            _connection(),
            {"hardware_details": {"chassis": "VM"}},
        )
        # Inspect the update statement values via execute call.
        # The first execute is the Host update.
        first_execute = db.execute.call_args_list[0]
        stmt = first_execute.args[0]
        # SQLAlchemy update with .values() — extract the bound values.
        values = stmt.compile().params
        assert json.loads(values["hardware_details"]) == {"chassis": "VM"}

    @pytest.mark.asyncio
    async def test_string_hardware_details_passed_through_unchanged(self):
        db = MagicMock()
        await handle_hardware_update(
            db,
            _connection(),
            {"storage_details": '{"already": "json"}'},
        )
        first_execute = db.execute.call_args_list[0]
        values = first_execute.args[0].compile().params
        # Already-a-string detail field is passed through verbatim.
        assert values["storage_details"] == '{"already": "json"}'

    @pytest.mark.asyncio
    async def test_inserts_network_interfaces_with_split_ip_addresses(self):
        db = MagicMock()
        await handle_hardware_update(
            db,
            _connection(),
            {
                "network_interfaces": [
                    {
                        "name": "eth0",
                        "ip_addresses": ["10.0.0.5", "fe80::1"],
                        "mac_address": "00:11:22:33:44:55",
                        "is_active": True,
                    }
                ],
            },
        )
        # The handler should have added one NetworkInterface row.
        added = [c.args[0] for c in db.add.call_args_list]
        from backend.persistence.models import NetworkInterface

        net_rows = [a for a in added if isinstance(a, NetworkInterface)]
        assert len(net_rows) == 1
        ni = net_rows[0]
        assert ni.ipv4_address == "10.0.0.5"
        assert ni.ipv6_address == "fe80::1"
        assert ni.is_up is True

    @pytest.mark.asyncio
    async def test_inserts_storage_devices(self):
        db = MagicMock()
        await handle_hardware_update(
            db,
            _connection(),
            {
                "storage_devices": [
                    {
                        "name": "/dev/sda",
                        "device_type": "disk",
                        "capacity_bytes": 1_000_000,
                        "used_bytes": 500_000,
                    }
                ],
            },
        )
        added = [c.args[0] for c in db.add.call_args_list]
        from backend.persistence.models import StorageDevice

        rows = [a for a in added if isinstance(a, StorageDevice)]
        assert len(rows) == 1
        # The handler prefers total_size, then falls back to capacity_bytes.
        assert rows[0].total_size_bytes == 1_000_000

    @pytest.mark.asyncio
    async def test_exception_rolls_back(self):
        db = MagicMock()
        db.execute.side_effect = RuntimeError("db down")
        result = await handle_hardware_update(
            db, _connection(), {"cpu_vendor": "Intel"}
        )
        assert result["error_type"] == "hardware_update_failed"
        db.rollback.assert_called_once()
