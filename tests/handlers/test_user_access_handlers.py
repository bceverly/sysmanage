"""
Tests for backend.api.handlers.user_access_handlers.

These cover the per-account / per-group construction helpers (Unix UID vs
Windows SID classification) plus the top-level handle_user_access_update
orchestration including the "users"/"groups" key fallbacks and the
exception-rollback path.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.api.handlers.user_access_handlers import (
    _create_user_account_with_security_id,
    _create_user_group_with_security_id,
    handle_user_access_update,
)


def _connection(host_id="conn-host-id"):
    c = MagicMock()
    c.host_id = host_id
    return c


# ---------------------------------------------------------------------------
# _create_user_account_with_security_id
# ---------------------------------------------------------------------------


class TestCreateUserAccount:
    def test_unix_uid_under_500_is_system_user(self):
        from datetime import datetime, timezone

        with patch("backend.api.handlers.user_access_handlers.UserAccount") as cls:
            _create_user_account_with_security_id(
                _connection(),
                {"uid": 0, "username": "root"},
                datetime.now(timezone.utc),
            )
        kwargs = cls.call_args.kwargs
        assert kwargs["uid"] == 0
        assert kwargs["security_id"] is None
        assert kwargs["is_system_user"] is True

    def test_unix_uid_at_or_above_500_is_regular_user_unless_known_name(self):
        from datetime import datetime, timezone

        with patch("backend.api.handlers.user_access_handlers.UserAccount") as cls:
            _create_user_account_with_security_id(
                _connection(),
                {"uid": 1000, "username": "alice"},
                datetime.now(timezone.utc),
            )
        kwargs = cls.call_args.kwargs
        assert kwargs["is_system_user"] is False

    def test_known_system_username_overrides_high_uid(self):
        from datetime import datetime, timezone

        with patch("backend.api.handlers.user_access_handlers.UserAccount") as cls:
            _create_user_account_with_security_id(
                _connection(),
                {"uid": 65534, "username": "nobody"},
                datetime.now(timezone.utc),
            )
        # 'nobody' is in SYSTEM_USERNAMES even though uid is high.
        assert cls.call_args.kwargs["is_system_user"] is True

    def test_windows_sid_low_rid_is_system_user(self):
        from datetime import datetime, timezone

        with patch("backend.api.handlers.user_access_handlers.UserAccount") as cls:
            _create_user_account_with_security_id(
                _connection(),
                {"uid": "S-1-5-18", "username": "system"},
                datetime.now(timezone.utc),
            )
        kwargs = cls.call_args.kwargs
        assert kwargs["uid"] is None
        assert kwargs["security_id"] == "S-1-5-18"
        assert kwargs["is_system_user"] is True

    def test_windows_sid_high_rid_is_regular_user(self):
        from datetime import datetime, timezone

        with patch("backend.api.handlers.user_access_handlers.UserAccount") as cls:
            _create_user_account_with_security_id(
                _connection(),
                {"uid": "S-1-5-21-1000-2000-3000-1500", "username": "alice"},
                datetime.now(timezone.utc),
            )
        kwargs = cls.call_args.kwargs
        assert kwargs["security_id"].startswith("S-1-5-21-")
        # RID 1500 → not a system user.
        assert kwargs["is_system_user"] is False

    def test_windows_sid_with_unparsable_rid_is_not_system_user(self):
        from datetime import datetime, timezone

        with patch("backend.api.handlers.user_access_handlers.UserAccount") as cls:
            _create_user_account_with_security_id(
                _connection(),
                {"uid": "S-1-5-not-a-number", "username": "alice"},
                datetime.now(timezone.utc),
            )
        # ValueError swallowed → falls through.
        assert cls.call_args.kwargs["is_system_user"] is False

    def test_empty_uid_treated_as_no_uid(self):
        from datetime import datetime, timezone

        with patch("backend.api.handlers.user_access_handlers.UserAccount") as cls:
            _create_user_account_with_security_id(
                _connection(),
                {"uid": "", "username": "alice"},
                datetime.now(timezone.utc),
            )
        kwargs = cls.call_args.kwargs
        assert kwargs["uid"] is None
        assert kwargs["security_id"] is None


# ---------------------------------------------------------------------------
# _create_user_group_with_security_id
# ---------------------------------------------------------------------------


class TestCreateUserGroup:
    def test_unix_gid(self):
        from datetime import datetime, timezone

        with patch("backend.api.handlers.user_access_handlers.UserGroup") as cls:
            _create_user_group_with_security_id(
                _connection(),
                {"gid": 1001, "group_name": "users"},
                datetime.now(timezone.utc),
            )
        kwargs = cls.call_args.kwargs
        assert kwargs["gid"] == 1001
        assert kwargs["security_id"] is None

    def test_windows_sid_group(self):
        from datetime import datetime, timezone

        with patch("backend.api.handlers.user_access_handlers.UserGroup") as cls:
            _create_user_group_with_security_id(
                _connection(),
                {"gid": "S-1-5-32-544", "group_name": "Administrators"},
                datetime.now(timezone.utc),
            )
        kwargs = cls.call_args.kwargs
        assert kwargs["gid"] is None
        assert kwargs["security_id"] == "S-1-5-32-544"

    def test_unrecognised_string_gid_is_dropped(self):
        from datetime import datetime, timezone

        with patch("backend.api.handlers.user_access_handlers.UserGroup") as cls:
            _create_user_group_with_security_id(
                _connection(),
                {"gid": "not-a-sid", "group_name": "weird"},
                datetime.now(timezone.utc),
            )
        kwargs = cls.call_args.kwargs
        # Doesn't parse as int and doesn't start with S-1- → both drop to None.
        assert kwargs["gid"] is None
        assert kwargs["security_id"] is None

    def test_missing_gid_yields_none(self):
        from datetime import datetime, timezone

        with patch("backend.api.handlers.user_access_handlers.UserGroup") as cls:
            _create_user_group_with_security_id(
                _connection(),
                {"group_name": "g", "is_system_group": True},
                datetime.now(timezone.utc),
            )
        kwargs = cls.call_args.kwargs
        assert kwargs["gid"] is None
        assert kwargs["security_id"] is None
        # is_system_group flag is honoured directly.
        assert kwargs["is_system_group"] is True


# ---------------------------------------------------------------------------
# handle_user_access_update orchestration
# ---------------------------------------------------------------------------


class TestHandleUserAccessUpdate:
    @pytest.mark.asyncio
    async def test_validate_host_id_failure(self):
        with patch(
            "backend.utils.host_validation.validate_host_id",
            new=AsyncMock(return_value=False),
        ):
            result = await handle_user_access_update(
                MagicMock(),
                _connection(),
                {"host_id": "bogus"},
            )
        assert result["error_type"] == "host_not_registered"

    @pytest.mark.asyncio
    async def test_connection_without_host_id_returns_error(self):
        connection = MagicMock()
        connection.host_id = None
        # No "host_id" in message_data → skip validation; then connection
        # check fails.
        result = await handle_user_access_update(MagicMock(), connection, {})
        assert result["error_type"] == "host_not_registered"

    @pytest.mark.asyncio
    async def test_connection_without_host_id_attribute(self):
        # spec=[] forces hasattr to return False.
        connection = MagicMock(spec=[])
        result = await handle_user_access_update(MagicMock(), connection, {})
        assert result["error_type"] == "host_not_registered"

    @pytest.mark.asyncio
    async def test_falls_back_to_users_key_when_user_accounts_missing(self):
        db = MagicMock()
        result = await handle_user_access_update(
            db,
            _connection(),
            {
                # legacy key name
                "users": [{"uid": 0, "username": "root"}],
            },
        )
        assert result["result"] == "user_access_updated"
        # delete + add + commit happened.
        db.execute.assert_called_once()
        db.add.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_groups_key(self):
        db = MagicMock()
        result = await handle_user_access_update(
            db,
            _connection(),
            {"groups": [{"gid": 0, "group_name": "root"}]},
        )
        assert result["result"] == "user_access_updated"
        # exactly one delete (groups) and one add.
        assert db.execute.call_count == 1
        assert db.add.call_count == 1

    @pytest.mark.asyncio
    async def test_processes_both_accounts_and_groups(self):
        db = MagicMock()
        result = await handle_user_access_update(
            db,
            _connection(),
            {
                "user_accounts": [
                    {"uid": 1000, "username": "alice"},
                    {"uid": 1001, "username": "bob"},
                ],
                "user_groups": [{"gid": 1000, "group_name": "alice"}],
            },
        )
        assert result["result"] == "user_access_updated"
        # Two deletes (one for accounts, one for groups).
        assert db.execute.call_count == 2
        # Three adds (2 users + 1 group).
        assert db.add.call_count == 3

    @pytest.mark.asyncio
    async def test_exception_rolls_back(self):
        db = MagicMock()
        db.execute.side_effect = RuntimeError("db down")
        result = await handle_user_access_update(
            db,
            _connection(),
            {"user_accounts": [{"uid": 0, "username": "root"}]},
        )
        assert result["error_type"] == "operation_failed"
        db.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_message_still_succeeds(self):
        db = MagicMock()
        result = await handle_user_access_update(db, _connection(), {})
        assert result["result"] == "user_access_updated"
        # No deletions or adds when nothing to process.
        db.execute.assert_not_called()
        db.add.assert_not_called()
        db.commit.assert_called_once()
