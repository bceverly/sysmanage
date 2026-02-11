"""
Tests for backend/websocket/data_processors.py module.
Tests data processing utilities for WebSocket agent communication.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest


class TestProcessUserAccounts:
    """Tests for process_user_accounts function."""

    @patch("backend.websocket.data_processors.UserAccount")
    def test_process_user_accounts_single_user(self, mock_user_account):
        """Test processing a single user account."""
        from backend.websocket.data_processors import process_user_accounts

        mock_db = MagicMock()
        host_id = "test-host-id"
        users_data = [
            {
                "username": "testuser",
                "uid": 1000,
                "home_directory": "/home/testuser",
                "shell": "/bin/bash",
                "is_system_user": False,
            }
        ]

        process_user_accounts(mock_db, host_id, users_data)

        mock_user_account.assert_called_once()
        mock_db.add.assert_called_once()

    @patch("backend.websocket.data_processors.UserAccount")
    def test_process_user_accounts_multiple_users(self, mock_user_account):
        """Test processing multiple user accounts."""
        from backend.websocket.data_processors import process_user_accounts

        mock_db = MagicMock()
        host_id = "test-host-id"
        users_data = [
            {"username": "user1", "uid": 1000},
            {"username": "user2", "uid": 1001},
            {"username": "user3", "uid": 1002},
        ]

        process_user_accounts(mock_db, host_id, users_data)

        assert mock_user_account.call_count == 3
        assert mock_db.add.call_count == 3

    @patch("backend.websocket.data_processors.UserAccount")
    def test_process_user_accounts_skip_error_entries(self, mock_user_account):
        """Test that entries with errors are skipped."""
        from backend.websocket.data_processors import process_user_accounts

        mock_db = MagicMock()
        host_id = "test-host-id"
        users_data = [
            {"username": "validuser", "uid": 1000},
            {"error": "Failed to get user data"},
            {"username": "anotheruser", "uid": 1001},
        ]

        process_user_accounts(mock_db, host_id, users_data)

        assert mock_user_account.call_count == 2
        assert mock_db.add.call_count == 2

    @patch("backend.websocket.data_processors.UserAccount")
    def test_process_user_accounts_empty_list(self, mock_user_account):
        """Test processing an empty user list."""
        from backend.websocket.data_processors import process_user_accounts

        mock_db = MagicMock()
        host_id = "test-host-id"
        users_data = []

        process_user_accounts(mock_db, host_id, users_data)

        mock_user_account.assert_not_called()
        mock_db.add.assert_not_called()

    @patch("backend.websocket.data_processors.UserAccount")
    def test_process_user_accounts_system_user(self, mock_user_account):
        """Test processing a system user."""
        from backend.websocket.data_processors import process_user_accounts

        mock_db = MagicMock()
        host_id = "test-host-id"
        users_data = [
            {
                "username": "root",
                "uid": 0,
                "is_system_user": True,
            }
        ]

        process_user_accounts(mock_db, host_id, users_data)

        mock_user_account.assert_called_once()
        # Check that is_system_user was passed correctly
        call_kwargs = mock_user_account.call_args[1]
        assert call_kwargs["is_system_user"] is True


class TestProcessUserGroups:
    """Tests for process_user_groups function."""

    @patch("backend.websocket.data_processors.UserGroup")
    def test_process_user_groups_single_group(self, mock_user_group):
        """Test processing a single user group."""
        from backend.websocket.data_processors import process_user_groups

        mock_db = MagicMock()
        host_id = "test-host-id"
        groups_data = [
            {
                "group_name": "testgroup",
                "gid": 1000,
                "is_system_group": False,
            }
        ]

        process_user_groups(mock_db, host_id, groups_data)

        mock_user_group.assert_called_once()
        mock_db.add.assert_called_once()

    @patch("backend.websocket.data_processors.UserGroup")
    def test_process_user_groups_multiple_groups(self, mock_user_group):
        """Test processing multiple user groups."""
        from backend.websocket.data_processors import process_user_groups

        mock_db = MagicMock()
        host_id = "test-host-id"
        groups_data = [
            {"group_name": "group1", "gid": 1000},
            {"group_name": "group2", "gid": 1001},
        ]

        process_user_groups(mock_db, host_id, groups_data)

        assert mock_user_group.call_count == 2
        assert mock_db.add.call_count == 2

    @patch("backend.websocket.data_processors.UserGroup")
    def test_process_user_groups_skip_error_entries(self, mock_user_group):
        """Test that entries with errors are skipped."""
        from backend.websocket.data_processors import process_user_groups

        mock_db = MagicMock()
        host_id = "test-host-id"
        groups_data = [
            {"group_name": "validgroup", "gid": 1000},
            {"error": "Failed to get group data"},
        ]

        process_user_groups(mock_db, host_id, groups_data)

        assert mock_user_group.call_count == 1
        assert mock_db.add.call_count == 1

    @patch("backend.websocket.data_processors.UserGroup")
    def test_process_user_groups_empty_list(self, mock_user_group):
        """Test processing an empty group list."""
        from backend.websocket.data_processors import process_user_groups

        mock_db = MagicMock()
        host_id = "test-host-id"
        groups_data = []

        process_user_groups(mock_db, host_id, groups_data)

        mock_user_group.assert_not_called()
        mock_db.add.assert_not_called()


class TestProcessUserGroupMemberships:
    """Tests for process_user_group_memberships function."""

    @patch("backend.websocket.data_processors.UserGroupMembership")
    def test_process_memberships_success(self, mock_membership):
        """Test processing user-group memberships successfully."""
        from backend.websocket.data_processors import process_user_group_memberships

        mock_db = MagicMock()
        host_id = "test-host-id"
        users_data = [
            {"username": "user1", "groups": ["group1", "group2"]},
        ]
        user_id_map = {"user1": "user-uuid-1"}
        group_id_map = {"group1": "group-uuid-1", "group2": "group-uuid-2"}

        process_user_group_memberships(
            mock_db, host_id, users_data, user_id_map, group_id_map
        )

        assert mock_membership.call_count == 2
        assert mock_db.merge.call_count == 2

    @patch("backend.websocket.data_processors.UserGroupMembership")
    def test_process_memberships_user_not_in_map(self, mock_membership):
        """Test when user is not in user_id_map."""
        from backend.websocket.data_processors import process_user_group_memberships

        mock_db = MagicMock()
        host_id = "test-host-id"
        users_data = [
            {"username": "unknownuser", "groups": ["group1"]},
        ]
        user_id_map = {"user1": "user-uuid-1"}
        group_id_map = {"group1": "group-uuid-1"}

        process_user_group_memberships(
            mock_db, host_id, users_data, user_id_map, group_id_map
        )

        mock_membership.assert_not_called()
        mock_db.merge.assert_not_called()

    @patch("backend.websocket.data_processors.UserGroupMembership")
    def test_process_memberships_group_not_in_map(self, mock_membership):
        """Test when group is not in group_id_map."""
        from backend.websocket.data_processors import process_user_group_memberships

        mock_db = MagicMock()
        host_id = "test-host-id"
        users_data = [
            {"username": "user1", "groups": ["unknowngroup"]},
        ]
        user_id_map = {"user1": "user-uuid-1"}
        group_id_map = {"group1": "group-uuid-1"}

        process_user_group_memberships(
            mock_db, host_id, users_data, user_id_map, group_id_map
        )

        mock_membership.assert_not_called()
        mock_db.merge.assert_not_called()

    @patch("backend.websocket.data_processors.UserGroupMembership")
    def test_process_memberships_skip_error_entries(self, mock_membership):
        """Test that entries with errors are skipped."""
        from backend.websocket.data_processors import process_user_group_memberships

        mock_db = MagicMock()
        host_id = "test-host-id"
        users_data = [
            {"username": "user1", "groups": ["group1"], "error": "some error"},
        ]
        user_id_map = {"user1": "user-uuid-1"}
        group_id_map = {"group1": "group-uuid-1"}

        process_user_group_memberships(
            mock_db, host_id, users_data, user_id_map, group_id_map
        )

        mock_membership.assert_not_called()
        mock_db.merge.assert_not_called()

    @patch("backend.websocket.data_processors.UserGroupMembership")
    def test_process_memberships_no_groups_field(self, mock_membership):
        """Test when user has no groups field."""
        from backend.websocket.data_processors import process_user_group_memberships

        mock_db = MagicMock()
        host_id = "test-host-id"
        users_data = [
            {"username": "user1"},  # No groups field
        ]
        user_id_map = {"user1": "user-uuid-1"}
        group_id_map = {"group1": "group-uuid-1"}

        process_user_group_memberships(
            mock_db, host_id, users_data, user_id_map, group_id_map
        )

        mock_membership.assert_not_called()
        mock_db.merge.assert_not_called()

    @patch("backend.websocket.data_processors.UserGroupMembership")
    def test_process_memberships_empty_groups(self, mock_membership):
        """Test when user has empty groups list."""
        from backend.websocket.data_processors import process_user_group_memberships

        mock_db = MagicMock()
        host_id = "test-host-id"
        users_data = [
            {"username": "user1", "groups": []},
        ]
        user_id_map = {"user1": "user-uuid-1"}
        group_id_map = {"group1": "group-uuid-1"}

        process_user_group_memberships(
            mock_db, host_id, users_data, user_id_map, group_id_map
        )

        mock_membership.assert_not_called()


class TestProcessSoftwarePackages:
    """Tests for process_software_packages function."""

    @patch("backend.websocket.data_processors.SoftwarePackage")
    def test_process_software_packages_single(self, mock_package):
        """Test processing a single software package."""
        from backend.websocket.data_processors import process_software_packages

        mock_db = MagicMock()
        host_id = "test-host-id"
        packages_data = [
            {
                "package_name": "vim",
                "version": "8.2",
                "description": "Vi IMproved",
                "package_manager": "apt",
                "architecture": "amd64",
            }
        ]

        process_software_packages(mock_db, host_id, packages_data)

        mock_package.assert_called_once()
        mock_db.add.assert_called_once()

    @patch("backend.websocket.data_processors.SoftwarePackage")
    def test_process_software_packages_multiple(self, mock_package):
        """Test processing multiple software packages."""
        from backend.websocket.data_processors import process_software_packages

        mock_db = MagicMock()
        host_id = "test-host-id"
        packages_data = [
            {"package_name": "pkg1", "version": "1.0"},
            {"package_name": "pkg2", "version": "2.0"},
            {"package_name": "pkg3", "version": "3.0"},
        ]

        process_software_packages(mock_db, host_id, packages_data)

        assert mock_package.call_count == 3
        assert mock_db.add.call_count == 3

    @patch("backend.websocket.data_processors.SoftwarePackage")
    def test_process_software_packages_skip_error(self, mock_package):
        """Test that packages with errors are skipped."""
        from backend.websocket.data_processors import process_software_packages

        mock_db = MagicMock()
        host_id = "test-host-id"
        packages_data = [
            {"package_name": "valid", "version": "1.0"},
            {"package_name": "errorpkg", "error": "Failed to get package info"},
        ]

        process_software_packages(mock_db, host_id, packages_data)

        assert mock_package.call_count == 1
        assert mock_db.add.call_count == 1

    @patch("backend.websocket.data_processors.SoftwarePackage")
    def test_process_software_packages_empty_list(self, mock_package):
        """Test processing an empty packages list."""
        from backend.websocket.data_processors import process_software_packages

        mock_db = MagicMock()
        host_id = "test-host-id"
        packages_data = []

        process_software_packages(mock_db, host_id, packages_data)

        mock_package.assert_not_called()
        mock_db.add.assert_not_called()

    @patch("backend.websocket.data_processors.SoftwarePackage")
    def test_process_software_packages_missing_version(self, mock_package):
        """Test processing package with missing version defaults to 'unknown'."""
        from backend.websocket.data_processors import process_software_packages

        mock_db = MagicMock()
        host_id = "test-host-id"
        packages_data = [
            {"package_name": "noversionpkg"},  # No version field
        ]

        process_software_packages(mock_db, host_id, packages_data)

        mock_package.assert_called_once()
        call_kwargs = mock_package.call_args[1]
        assert call_kwargs["package_version"] == "unknown"

    @patch("backend.websocket.data_processors.SoftwarePackage")
    def test_process_software_packages_all_fields(self, mock_package):
        """Test processing package with all fields."""
        from backend.websocket.data_processors import process_software_packages

        mock_db = MagicMock()
        host_id = "test-host-id"
        packages_data = [
            {
                "package_name": "fullpkg",
                "version": "1.0.0",
                "description": "Full package",
                "package_manager": "apt",
                "architecture": "amd64",
                "size_bytes": 12345,
                "install_date": "2024-01-01",
                "vendor": "Test Vendor",
                "category": "utilities",
                "license_type": "MIT",
                "installation_path": "/usr/bin/fullpkg",
                "is_system_package": True,
            }
        ]

        process_software_packages(mock_db, host_id, packages_data)

        mock_package.assert_called_once()
        call_kwargs = mock_package.call_args[1]
        assert call_kwargs["package_name"] == "fullpkg"
        assert call_kwargs["package_version"] == "1.0.0"
        assert call_kwargs["is_system_package"] is True
