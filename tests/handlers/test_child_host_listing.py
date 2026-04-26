"""
Tests for backend.api.handlers.child_host.listing.

Exercises both _try_link_child_to_approved_host (the late-link helper) and
the top-level handle_child_hosts_list_update orchestration: success ack,
host-not-found, validation failure, no host_id, and the stale-uninstall
cleanup sweep.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.api.handlers.child_host.listing import (
    _try_link_child_to_approved_host,
    handle_child_hosts_list_update,
)


def _connection(host_id="parent-host-id"):
    c = MagicMock()
    c.host_id = host_id
    return c


# ---------------------------------------------------------------------------
# _try_link_child_to_approved_host
# ---------------------------------------------------------------------------


class TestTryLinkChildToApprovedHost:
    def test_no_hostname_skip(self):
        db = MagicMock()
        child = MagicMock(hostname=None)
        assert (
            _try_link_child_to_approved_host(db, child, datetime.now(timezone.utc))
            is None
        )
        db.query.assert_not_called()

    def test_already_linked_skip(self):
        db = MagicMock()
        child = MagicMock(hostname="x.example", child_host_id="something")
        assert (
            _try_link_child_to_approved_host(db, child, datetime.now(timezone.utc))
            is None
        )
        db.query.assert_not_called()

    def test_not_running_skip(self):
        db = MagicMock()
        child = MagicMock(hostname="x.example", child_host_id=None, status="creating")
        assert (
            _try_link_child_to_approved_host(db, child, datetime.now(timezone.utc))
            is None
        )
        db.query.assert_not_called()

    def test_exact_fqdn_match_links(self):
        db = MagicMock()
        host = MagicMock(id="approved-host-id", fqdn="x.example")
        # First filter().first() yields the host.
        db.query.return_value.filter.return_value.first.return_value = host

        child = MagicMock(
            hostname="x.example",
            child_host_id=None,
            status="running",
            parent_host_id="parent",
        )
        now = datetime.now(timezone.utc)
        result = _try_link_child_to_approved_host(db, child, now)
        assert result is host
        assert child.child_host_id == "approved-host-id"
        assert child.installed_at == now
        # parent_host_id is propagated to the host record.
        assert host.parent_host_id == "parent"

    def test_short_hostname_match_when_exact_fails(self):
        db = MagicMock()
        host = MagicMock(id="approved-host-id", fqdn="x.example")
        # First call returns None (exact match), second returns host.
        db.query.return_value.filter.return_value.first.side_effect = [None, host]
        child = MagicMock(
            hostname="x.example",
            child_host_id=None,
            status="running",
            parent_host_id="parent",
        )
        result = _try_link_child_to_approved_host(db, child, datetime.now(timezone.utc))
        assert result is host

    def test_no_match_returns_none(self):
        db = MagicMock()
        # All three lookup attempts come back empty.
        db.query.return_value.filter.return_value.first.return_value = None
        child = MagicMock(
            hostname="missing",
            child_host_id=None,
            status="running",
            parent_host_id="p",
        )
        assert (
            _try_link_child_to_approved_host(db, child, datetime.now(timezone.utc))
            is None
        )


# ---------------------------------------------------------------------------
# handle_child_hosts_list_update
# ---------------------------------------------------------------------------


class TestHandleChildHostsListUpdate:
    @pytest.mark.asyncio
    async def test_no_host_id_returns_error(self):
        connection = MagicMock(spec=[])
        result = await handle_child_hosts_list_update(MagicMock(), connection, {})
        assert result["error_type"] == "no_host_id"

    @pytest.mark.asyncio
    async def test_failure_envelope_returns_error(self):
        result = await handle_child_hosts_list_update(
            MagicMock(),
            _connection(),
            {"success": False, "error": "agent crash"},
        )
        assert result["error_type"] == "operation_failed"
        assert result["message"] == "agent crash"

    @pytest.mark.asyncio
    async def test_host_not_found(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = await handle_child_hosts_list_update(
            db,
            _connection(),
            {
                "success": True,
                "result": {"child_hosts": [], "count": 0},
            },
        )
        assert result["error_type"] == "host_not_found"

    @pytest.mark.asyncio
    async def test_creates_new_child_record(self):
        db = MagicMock()
        host = MagicMock(id="parent-host-id", fqdn="parent.example")

        # First .first() returns host (Host lookup); subsequent .first() in
        # _try_link_child_to_approved_host return None. .all() returns [].
        first_results = [host]

        def query_side(model):
            class _Chain:
                def filter(self_inner, *a, **kw):
                    return self_inner

                def first(self_inner):
                    return first_results.pop(0) if first_results else None

                def all(self_inner):
                    return []

            return _Chain()

        db.query.side_effect = query_side

        with patch("backend.api.handlers.child_host.listing.AuditService"), patch(
            "backend.api.handlers.child_host.listing._try_link_child_to_approved_host",
            return_value=None,
        ):
            result = await handle_child_hosts_list_update(
                db,
                _connection(),
                {
                    "success": True,
                    "result": {
                        "child_hosts": [
                            {
                                "child_name": "ubuntu",
                                "child_type": "lxd",
                                "status": "running",
                                "hostname": "ubuntu.example",
                            }
                        ],
                        "count": 1,
                    },
                },
            )

        assert result["new_count"] == 1
        assert result["status"] == "updated"
        # add() called for the new HostChild row.
        assert db.add.called
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_entries_missing_name_or_type(self):
        db = MagicMock()
        host = MagicMock(id="parent-host-id", fqdn="parent.example")

        # First call host lookup. Then HostChild list (empty). Subsequent calls
        # return empty since we don't add/link anything.
        first_calls = [host]
        all_calls = [[]]

        def query_side(model):
            class _Chain:
                def filter(self_inner, *a, **kw):
                    return self_inner

                def first(self_inner):
                    return first_calls.pop(0) if first_calls else None

                def all(self_inner):
                    return all_calls.pop(0) if all_calls else []

            return _Chain()

        db.query.side_effect = query_side

        with patch("backend.api.handlers.child_host.listing.AuditService"):
            result = await handle_child_hosts_list_update(
                db,
                _connection(),
                {
                    "success": True,
                    "result": {
                        "child_hosts": [
                            # missing child_type
                            {"child_name": "x"},
                            # missing child_name
                            {"child_type": "lxd"},
                        ],
                        "count": 2,
                    },
                },
            )
        # No new children created.
        assert result["new_count"] == 0
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_updates_existing_child(self):
        db = MagicMock()
        host = MagicMock(id="parent-host-id", fqdn="parent.example")
        existing = MagicMock(
            child_name="ubuntu",
            child_type="lxd",
            status="stopped",
            child_host_id=None,
            hostname=None,
            wsl_guid=None,
        )

        first_calls = [host]
        all_calls = [[existing]]

        def query_side(model):
            class _Chain:
                def filter(self_inner, *a, **kw):
                    return self_inner

                def first(self_inner):
                    return first_calls.pop(0) if first_calls else None

                def all(self_inner):
                    return all_calls.pop(0) if all_calls else []

            return _Chain()

        db.query.side_effect = query_side

        with patch("backend.api.handlers.child_host.listing.AuditService"), patch(
            "backend.api.handlers.child_host.listing._try_link_child_to_approved_host",
            return_value=None,
        ):
            result = await handle_child_hosts_list_update(
                db,
                _connection(),
                {
                    "success": True,
                    "result": {
                        "child_hosts": [
                            {
                                "child_name": "ubuntu",
                                "child_type": "lxd",
                                "status": "running",
                                "hostname": "ubuntu.example",
                                "distribution": {
                                    "distribution_name": "Ubuntu",
                                    "distribution_version": "24.04",
                                },
                            }
                        ],
                        "count": 1,
                    },
                },
            )

        assert result["updated_count"] == 1
        assert existing.status == "running"
        assert existing.hostname == "ubuntu.example"
        assert existing.distribution == "Ubuntu"
        assert existing.distribution_version == "24.04"

    @pytest.mark.asyncio
    async def test_uninstalling_existing_child_status_not_overwritten(self):
        db = MagicMock()
        host = MagicMock(id="parent-host-id", fqdn="parent.example")
        existing = MagicMock(
            child_name="ubuntu",
            child_type="lxd",
            status="uninstalling",  # protected
            child_host_id=None,
            hostname=None,
            wsl_guid=None,
        )
        first_calls = [host]
        all_calls = [[existing]]

        def query_side(model):
            class _Chain:
                def filter(self_inner, *a, **kw):
                    return self_inner

                def first(self_inner):
                    return first_calls.pop(0) if first_calls else None

                def all(self_inner):
                    return all_calls.pop(0) if all_calls else []

            return _Chain()

        db.query.side_effect = query_side

        with patch("backend.api.handlers.child_host.listing.AuditService"), patch(
            "backend.api.handlers.child_host.listing._try_link_child_to_approved_host",
            return_value=None,
        ):
            await handle_child_hosts_list_update(
                db,
                _connection(),
                {
                    "success": True,
                    "result": {
                        "child_hosts": [
                            {
                                "child_name": "ubuntu",
                                "child_type": "lxd",
                                "status": "running",
                            }
                        ],
                        "count": 1,
                    },
                },
            )
        # The 'uninstalling' status should NOT be overwritten.
        assert existing.status == "uninstalling"

    @pytest.mark.asyncio
    async def test_stale_creating_child_is_preserved(self):
        db = MagicMock()
        host = MagicMock(id="parent-host-id", fqdn="parent.example")
        # Existing child in 'creating' status that the agent did NOT report.
        existing = MagicMock(
            child_name="ghost",
            child_type="lxd",
            status="creating",
            child_host_id=None,
            hostname=None,
        )
        first_calls = [host]
        all_calls = [[existing]]

        def query_side(model):
            class _Chain:
                def filter(self_inner, *a, **kw):
                    return self_inner

                def first(self_inner):
                    return first_calls.pop(0) if first_calls else None

                def all(self_inner):
                    return all_calls.pop(0) if all_calls else []

            return _Chain()

        db.query.side_effect = query_side

        with patch("backend.api.handlers.child_host.listing.AuditService"):
            await handle_child_hosts_list_update(
                db,
                _connection(),
                {
                    "success": True,
                    "result": {"child_hosts": [], "count": 0},
                },
            )
        # 'creating' children must NOT be deleted even when missing from the list.
        db.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_exception_rolls_back(self):
        db = MagicMock()
        db.query.side_effect = RuntimeError("db down")
        result = await handle_child_hosts_list_update(
            db,
            _connection(),
            {"success": True, "result": {"child_hosts": [], "count": 0}},
        )
        assert result["error_type"] == "operation_failed"
        db.rollback.assert_called_once()
