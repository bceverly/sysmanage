"""
Comprehensive unit tests for websocket data processors.
Tests data processing utilities for WebSocket agent communication.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from backend.websocket.data_processors import (
    process_user_accounts,
    process_user_groups,
    process_user_group_memberships,
    process_software_packages,
)
from backend.persistence.models import (
    SoftwarePackage,
    UserAccount,
    UserGroup,
    UserGroupMembership,
)


class TestProcessUserAccounts:
    """Test cases for user account processing."""

    def test_process_user_accounts_success(self):
        """Test successful processing of user accounts."""
        mock_db = Mock()
        host_id = 123
        users_data = [
            {
                "username": "alice",
                "uid": 1001,
                "home_directory": "/home/alice",
                "shell": "/bin/bash",
                "is_system_user": False,
            },
            {
                "username": "bob",
                "uid": 1002,
                "home_directory": "/home/bob",
                "shell": "/bin/zsh",
                "is_system_user": False,
            },
            {
                "username": "root",
                "uid": 0,
                "home_directory": "/root",
                "shell": "/bin/bash",
                "is_system_user": True,
            },
        ]

        with patch("backend.websocket.data_processors.datetime") as mock_datetime:
            mock_now = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            mock_datetime.now.return_value = mock_now
            mock_datetime.timezone = timezone

            process_user_accounts(mock_db, host_id, users_data)

            # Verify correct number of add calls
            assert mock_db.add.call_count == 3

            # Check first user account
            first_call = mock_db.add.call_args_list[0][0][0]
            assert isinstance(first_call, UserAccount)
            assert first_call.host_id == 123
            assert first_call.username == "alice"
            assert first_call.uid == 1001
            assert first_call.home_directory == "/home/alice"
            assert first_call.shell == "/bin/bash"
            assert first_call.is_system_user is False
            assert first_call.created_at == mock_now
            assert first_call.updated_at == mock_now

    def test_process_user_accounts_with_errors(self):
        """Test processing user accounts with error entries."""
        mock_db = Mock()
        host_id = 123
        users_data = [
            {
                "username": "alice",
                "uid": 1001,
                "home_directory": "/home/alice",
                "shell": "/bin/bash",
                "is_system_user": False,
            },
            {
                "error": "Permission denied",
                "username": "invalid_user",
            },
            {
                "username": "bob",
                "uid": 1002,
                "home_directory": "/home/bob",
                "shell": "/bin/zsh",
                "is_system_user": False,
            },
        ]

        process_user_accounts(mock_db, host_id, users_data)

        # Should only add 2 users (skip the error entry)
        assert mock_db.add.call_count == 2

        # Verify first user
        first_call = mock_db.add.call_args_list[0][0][0]
        assert first_call.username == "alice"

        # Verify second user
        second_call = mock_db.add.call_args_list[1][0][0]
        assert second_call.username == "bob"

    def test_process_user_accounts_empty_list(self):
        """Test processing empty user accounts list."""
        mock_db = Mock()
        host_id = 123
        users_data = []

        process_user_accounts(mock_db, host_id, users_data)

        # Should not add any users
        mock_db.add.assert_not_called()

    def test_process_user_accounts_missing_fields(self):
        """Test processing user accounts with missing fields."""
        mock_db = Mock()
        host_id = 123
        users_data = [
            {
                "username": "minimal_user",
                # Missing uid, home_directory, shell
            },
        ]

        process_user_accounts(mock_db, host_id, users_data)

        # Should still add the user with None values for missing fields
        assert mock_db.add.call_count == 1
        user_account = mock_db.add.call_args_list[0][0][0]
        assert user_account.username == "minimal_user"
        assert user_account.uid is None
        assert user_account.home_directory is None
        assert user_account.shell is None
        assert user_account.is_system_user is False  # Default value


class TestProcessUserGroups:
    """Test cases for user group processing."""

    def test_process_user_groups_success(self):
        """Test successful processing of user groups."""
        mock_db = Mock()
        host_id = 456
        groups_data = [
            {
                "group_name": "admin",
                "gid": 1000,
                "is_system_group": False,
            },
            {
                "group_name": "users",
                "gid": 1001,
                "is_system_group": False,
            },
            {
                "group_name": "wheel",
                "gid": 0,
                "is_system_group": True,
            },
        ]

        with patch("backend.websocket.data_processors.datetime") as mock_datetime:
            mock_now = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            mock_datetime.now.return_value = mock_now
            mock_datetime.timezone = timezone

            process_user_groups(mock_db, host_id, groups_data)

            # Verify correct number of add calls
            assert mock_db.add.call_count == 3

            # Check first group
            first_call = mock_db.add.call_args_list[0][0][0]
            assert isinstance(first_call, UserGroup)
            assert first_call.host_id == 456
            assert first_call.group_name == "admin"
            assert first_call.gid == 1000
            assert first_call.is_system_group is False
            assert first_call.created_at == mock_now
            assert first_call.updated_at == mock_now

    def test_process_user_groups_with_errors(self):
        """Test processing user groups with error entries."""
        mock_db = Mock()
        host_id = 456
        groups_data = [
            {
                "group_name": "admin",
                "gid": 1000,
                "is_system_group": False,
            },
            {
                "error": "Access denied",
                "group_name": "invalid_group",
            },
            {
                "group_name": "users",
                "gid": 1001,
                "is_system_group": False,
            },
        ]

        process_user_groups(mock_db, host_id, groups_data)

        # Should only add 2 groups (skip the error entry)
        assert mock_db.add.call_count == 2

        # Verify groups were added correctly
        first_call = mock_db.add.call_args_list[0][0][0]
        assert first_call.group_name == "admin"

        second_call = mock_db.add.call_args_list[1][0][0]
        assert second_call.group_name == "users"

    def test_process_user_groups_empty_list(self):
        """Test processing empty user groups list."""
        mock_db = Mock()
        host_id = 456
        groups_data = []

        process_user_groups(mock_db, host_id, groups_data)

        # Should not add any groups
        mock_db.add.assert_not_called()

    def test_process_user_groups_missing_fields(self):
        """Test processing user groups with missing fields."""
        mock_db = Mock()
        host_id = 456
        groups_data = [
            {
                "group_name": "minimal_group",
                # Missing gid
            },
        ]

        process_user_groups(mock_db, host_id, groups_data)

        # Should still add the group with None values for missing fields
        assert mock_db.add.call_count == 1
        user_group = mock_db.add.call_args_list[0][0][0]
        assert user_group.group_name == "minimal_group"
        assert user_group.gid is None
        assert user_group.is_system_group is False  # Default value


class TestProcessUserGroupMemberships:
    """Test cases for user-group membership processing."""

    @patch("backend.websocket.data_processors.debug_logger")
    def test_process_user_group_memberships_success(self, mock_logger):
        """Test successful processing of user-group memberships."""
        mock_db = Mock()
        host_id = 789
        users_data = [
            {
                "username": "alice",
                "groups": ["admin", "users"],
            },
            {
                "username": "bob",
                "groups": ["users", "developers"],
            },
        ]
        user_id_map = {"alice": 1, "bob": 2}
        group_id_map = {"admin": 10, "users": 11, "developers": 12}

        with patch("backend.websocket.data_processors.datetime") as mock_datetime:
            mock_now = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            mock_datetime.now.return_value = mock_now
            mock_datetime.timezone = timezone

            process_user_group_memberships(
                mock_db, host_id, users_data, user_id_map, group_id_map
            )

            # Should create 4 memberships (alice: 2, bob: 2)
            assert mock_db.merge.call_count == 4

            # Verify logging calls
            mock_logger.info.assert_any_call("Processing memberships for %d users", 2)
            mock_logger.info.assert_any_call(
                "Available users: %d, Available groups: %d", 2, 3
            )
            mock_logger.info.assert_any_call("Added %d memberships to database", 4)

            # Check first membership
            first_call = mock_db.merge.call_args_list[0][0][0]
            assert isinstance(first_call, UserGroupMembership)
            assert first_call.host_id == 789
            assert first_call.user_account_id == 1  # alice
            assert first_call.user_group_id == 10  # admin
            assert first_call.created_at == mock_now
            assert first_call.updated_at == mock_now

    @patch("backend.websocket.data_processors.debug_logger")
    def test_process_user_group_memberships_with_errors(self, mock_logger):
        """Test processing memberships with error entries."""
        mock_db = Mock()
        host_id = 789
        users_data = [
            {
                "username": "alice",
                "groups": ["admin", "users"],
            },
            {
                "error": "Access denied",
                "username": "invalid_user",
                "groups": ["admin"],
            },
            {
                "username": "bob",
                "groups": ["users"],
            },
        ]
        user_id_map = {"alice": 1, "bob": 2}
        group_id_map = {"admin": 10, "users": 11}

        process_user_group_memberships(
            mock_db, host_id, users_data, user_id_map, group_id_map
        )

        # Should create 3 memberships (alice: 2, bob: 1, skip error entry)
        assert mock_db.merge.call_count == 3

        # Verify error was logged
        mock_logger.debug.assert_any_call(
            "Skipping user with error: %s", "invalid_user"
        )

    @patch("backend.websocket.data_processors.debug_logger")
    def test_process_user_group_memberships_missing_user(self, mock_logger):
        """Test processing memberships with missing user in map."""
        mock_db = Mock()
        host_id = 789
        users_data = [
            {
                "username": "alice",
                "groups": ["admin"],
            },
            {
                "username": "unknown_user",
                "groups": ["users"],
            },
        ]
        user_id_map = {"alice": 1}  # missing unknown_user
        group_id_map = {"admin": 10, "users": 11}

        process_user_group_memberships(
            mock_db, host_id, users_data, user_id_map, group_id_map
        )

        # Should only create 1 membership (alice)
        assert mock_db.merge.call_count == 1

        # Verify warning was logged
        mock_logger.debug.assert_any_call(
            "User '%s' not found in user_id_map", "unknown_user"
        )

    @patch("backend.websocket.data_processors.debug_logger")
    def test_process_user_group_memberships_missing_group(self, mock_logger):
        """Test processing memberships with missing group in map."""
        mock_db = Mock()
        host_id = 789
        users_data = [
            {
                "username": "alice",
                "groups": ["admin", "unknown_group"],
            },
        ]
        user_id_map = {"alice": 1}
        group_id_map = {"admin": 10}  # missing unknown_group

        process_user_group_memberships(
            mock_db, host_id, users_data, user_id_map, group_id_map
        )

        # Should only create 1 membership (admin)
        assert mock_db.merge.call_count == 1

        # Verify warning was logged
        mock_logger.debug.assert_any_call(
            "Group '%s' not found in group_id_map for user %s", "unknown_group", "alice"
        )

    @patch("backend.websocket.data_processors.debug_logger")
    def test_process_user_group_memberships_no_groups_field(self, mock_logger):
        """Test processing memberships with missing groups field."""
        mock_db = Mock()
        host_id = 789
        users_data = [
            {
                "username": "alice",
                # Missing groups field
            },
        ]
        user_id_map = {"alice": 1}
        group_id_map = {"admin": 10}

        process_user_group_memberships(
            mock_db, host_id, users_data, user_id_map, group_id_map
        )

        # Should not create any memberships
        assert mock_db.merge.call_count == 0

        # Verify warning was logged
        mock_logger.debug.assert_any_call("User %s has no groups field", "alice")

    @patch("backend.websocket.data_processors.debug_logger")
    def test_process_user_group_memberships_empty_lists(self, mock_logger):
        """Test processing with empty lists and maps."""
        mock_db = Mock()
        host_id = 789
        users_data = []
        user_id_map = {}
        group_id_map = {}

        process_user_group_memberships(
            mock_db, host_id, users_data, user_id_map, group_id_map
        )

        # Should not create any memberships
        assert mock_db.merge.call_count == 0

        # Verify logging
        mock_logger.info.assert_any_call("Processing memberships for %d users", 0)
        mock_logger.info.assert_any_call("Added %d memberships to database", 0)


class TestProcessSoftwarePackages:
    """Test cases for software package processing."""

    @patch("backend.websocket.data_processors.debug_logger")
    def test_process_software_packages_success(self, mock_logger):
        """Test successful processing of software packages."""
        mock_db = Mock()
        host_id = 999
        packages_data = [
            {
                "package_name": "vim",
                "version": "8.2.1234",
                "description": "Vi IMproved text editor",
                "package_manager": "apt",
                "source": "ubuntu",
                "architecture": "amd64",
                "size_bytes": 1234567,
                "install_date": "2023-01-01",
                "vendor": "Ubuntu",
                "category": "editors",
                "license_type": "GPL",
                "bundle_id": None,
                "app_store_id": None,
                "installation_path": "/usr/bin/vim",
                "is_system_package": True,
                "is_user_installed": False,
            },
            {
                "package_name": "firefox",
                "version": "110.0",
                "description": "Mozilla Firefox web browser",
                "package_manager": "snap",
                "source": "snapcraft",
                "architecture": "amd64",
                "size_bytes": 87654321,
                "install_date": "2023-01-15",
                "vendor": "Mozilla",
                "category": "web",
                "license_type": "MPL-2.0",
                "bundle_id": None,
                "app_store_id": None,
                "installation_path": "/snap/firefox",
                "is_system_package": False,
                "is_user_installed": True,
            },
        ]

        with patch("backend.websocket.data_processors.datetime") as mock_datetime:
            mock_now = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            mock_datetime.now.return_value = mock_now
            mock_datetime.timezone = timezone

            process_software_packages(mock_db, host_id, packages_data)

            # Should add 2 packages
            assert mock_db.add.call_count == 2

            # Verify logging
            mock_logger.info.assert_called_with(
                "Added %d software packages to database", 2
            )

            # Check first package
            first_call = mock_db.add.call_args_list[0][0][0]
            assert isinstance(first_call, SoftwarePackage)
            assert first_call.host_id == 999
            assert first_call.package_name == "vim"
            assert first_call.version == "8.2.1234"
            assert first_call.description == "Vi IMproved text editor"
            assert first_call.package_manager == "apt"
            assert first_call.source == "ubuntu"
            assert first_call.architecture == "amd64"
            assert first_call.size_bytes == 1234567
            assert first_call.install_date == "2023-01-01"
            assert first_call.vendor == "Ubuntu"
            assert first_call.category == "editors"
            assert first_call.license_type == "GPL"
            assert first_call.bundle_id is None
            assert first_call.app_store_id is None
            assert first_call.installation_path == "/usr/bin/vim"
            assert first_call.is_system_package is True
            assert first_call.is_user_installed is False
            assert first_call.created_at == mock_now
            assert first_call.updated_at == mock_now
            assert first_call.software_updated_at == mock_now

    @patch("backend.websocket.data_processors.debug_logger")
    def test_process_software_packages_with_errors(self, mock_logger):
        """Test processing software packages with error entries."""
        mock_db = Mock()
        host_id = 999
        packages_data = [
            {
                "package_name": "vim",
                "version": "8.2.1234",
                "description": "Vi IMproved text editor",
                "package_manager": "apt",
            },
            {
                "error": "Permission denied",
                "package_name": "restricted_package",
            },
            {
                "package_name": "firefox",
                "version": "110.0",
                "description": "Mozilla Firefox web browser",
                "package_manager": "snap",
            },
        ]

        process_software_packages(mock_db, host_id, packages_data)

        # Should only add 2 packages (skip the error entry)
        assert mock_db.add.call_count == 2

        # Verify error was logged
        mock_logger.debug.assert_any_call(
            "Skipping package with error: %s", "restricted_package"
        )

        # Verify success was logged
        mock_logger.info.assert_called_with("Added %d software packages to database", 2)

    @patch("backend.websocket.data_processors.debug_logger")
    def test_process_software_packages_minimal_data(self, mock_logger):
        """Test processing software packages with minimal data."""
        mock_db = Mock()
        host_id = 999
        packages_data = [
            {
                "package_name": "minimal_package",
                # Only required field provided
            },
        ]

        process_software_packages(mock_db, host_id, packages_data)

        # Should add the package with default values
        assert mock_db.add.call_count == 1

        package = mock_db.add.call_args_list[0][0][0]
        assert package.package_name == "minimal_package"
        assert package.version is None
        assert package.description is None
        assert package.package_manager is None
        assert package.is_system_package is False  # Default
        assert package.is_user_installed is True  # Default

        # Verify logging
        mock_logger.info.assert_called_with("Added %d software packages to database", 1)

    @patch("backend.websocket.data_processors.debug_logger")
    def test_process_software_packages_empty_list(self, mock_logger):
        """Test processing empty software packages list."""
        mock_db = Mock()
        host_id = 999
        packages_data = []

        process_software_packages(mock_db, host_id, packages_data)

        # Should not add any packages
        mock_db.add.assert_not_called()

        # Verify logging
        mock_logger.info.assert_called_with("Added %d software packages to database", 0)

    @patch("backend.websocket.data_processors.debug_logger")
    def test_process_software_packages_error_without_name(self, mock_logger):
        """Test processing software packages with error and no name."""
        mock_db = Mock()
        host_id = 999
        packages_data = [
            {
                "error": "Unknown error",
                # No package_name field
            },
        ]

        process_software_packages(mock_db, host_id, packages_data)

        # Should not add any packages
        mock_db.add.assert_not_called()

        # Verify error was logged with 'unknown' as fallback
        mock_logger.debug.assert_any_call("Skipping package with error: %s", "unknown")

        # Verify final count logging
        mock_logger.info.assert_called_with("Added %d software packages to database", 0)
