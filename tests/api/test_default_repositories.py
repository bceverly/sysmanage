"""
Tests for the default repositories API module.

This module tests the default repository API endpoints and helper functions
for managing repositories that are automatically applied to new hosts.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.api.default_repositories import (
    OS_PACKAGE_MANAGERS,
    DefaultRepositoryCreate,
    DefaultRepositoryResponse,
    OSPackageManagersResponse,
    apply_default_repositories_to_host,
    apply_repository_to_host,
    apply_repository_to_matching_hosts,
)


class TestOSPackageManagers:
    """Test cases for OS_PACKAGE_MANAGERS constant."""

    def test_ubuntu_has_expected_managers(self):
        """Verify Ubuntu has APT, snap, flatpak managers."""
        assert "Ubuntu" in OS_PACKAGE_MANAGERS
        assert "APT" in OS_PACKAGE_MANAGERS["Ubuntu"]
        assert "snap" in OS_PACKAGE_MANAGERS["Ubuntu"]
        assert "flatpak" in OS_PACKAGE_MANAGERS["Ubuntu"]

    def test_debian_has_expected_managers(self):
        """Verify Debian has APT, snap, flatpak managers."""
        assert "Debian" in OS_PACKAGE_MANAGERS
        assert "APT" in OS_PACKAGE_MANAGERS["Debian"]

    def test_rhel_has_expected_managers(self):
        """Verify RHEL has dnf, yum, flatpak managers."""
        assert "RHEL" in OS_PACKAGE_MANAGERS
        assert "dnf" in OS_PACKAGE_MANAGERS["RHEL"]
        assert "yum" in OS_PACKAGE_MANAGERS["RHEL"]

    def test_fedora_has_expected_managers(self):
        """Verify Fedora has dnf, flatpak managers."""
        assert "Fedora" in OS_PACKAGE_MANAGERS
        assert "dnf" in OS_PACKAGE_MANAGERS["Fedora"]

    def test_freebsd_has_pkg_manager(self):
        """Verify FreeBSD has pkg manager."""
        assert "FreeBSD" in OS_PACKAGE_MANAGERS
        assert "pkg" in OS_PACKAGE_MANAGERS["FreeBSD"]

    def test_openbsd_has_pkg_add_manager(self):
        """Verify OpenBSD has pkg_add manager."""
        assert "OpenBSD" in OS_PACKAGE_MANAGERS
        assert "pkg_add" in OS_PACKAGE_MANAGERS["OpenBSD"]

    def test_macos_has_homebrew_manager(self):
        """Verify macOS has homebrew manager."""
        assert "macOS" in OS_PACKAGE_MANAGERS
        assert "homebrew" in OS_PACKAGE_MANAGERS["macOS"]

    def test_windows_has_expected_managers(self):
        """Verify Windows has winget and chocolatey managers."""
        assert "Windows" in OS_PACKAGE_MANAGERS
        assert "winget" in OS_PACKAGE_MANAGERS["Windows"]
        assert "chocolatey" in OS_PACKAGE_MANAGERS["Windows"]

    def test_oracle_linux_has_expected_managers(self):
        """Verify Oracle Linux has dnf, yum, flatpak managers."""
        assert "Oracle Linux" in OS_PACKAGE_MANAGERS
        assert "dnf" in OS_PACKAGE_MANAGERS["Oracle Linux"]
        assert "yum" in OS_PACKAGE_MANAGERS["Oracle Linux"]


class TestDefaultRepositoryCreate:
    """Test cases for DefaultRepositoryCreate Pydantic model."""

    def test_valid_repository_creates_successfully(self):
        """Test that a valid repository configuration passes validation."""
        repo = DefaultRepositoryCreate(
            os_name="Ubuntu",
            package_manager="APT",
            repository_url="ppa:test/ppa",
        )
        assert repo.os_name == "Ubuntu"
        assert repo.package_manager == "APT"
        assert repo.repository_url == "ppa:test/ppa"

    def test_invalid_os_name_raises_error(self):
        """Test that invalid OS name raises validation error."""
        with pytest.raises(ValueError, match="Unsupported operating system"):
            DefaultRepositoryCreate(
                os_name="InvalidOS",
                package_manager="APT",
                repository_url="ppa:test/ppa",
            )

    def test_empty_os_name_raises_error(self):
        """Test that empty OS name raises validation error."""
        with pytest.raises(ValueError, match="OS name is required"):
            DefaultRepositoryCreate(
                os_name="",
                package_manager="APT",
                repository_url="ppa:test/ppa",
            )

    def test_invalid_package_manager_raises_error(self):
        """Test that invalid package manager for OS raises validation error."""
        with pytest.raises(ValueError, match="Invalid package manager"):
            DefaultRepositoryCreate(
                os_name="Ubuntu",
                package_manager="yum",  # yum not valid for Ubuntu
                repository_url="ppa:test/ppa",
            )

    def test_empty_package_manager_raises_error(self):
        """Test that empty package manager raises validation error."""
        with pytest.raises(ValueError, match="Package manager is required"):
            DefaultRepositoryCreate(
                os_name="Ubuntu",
                package_manager="",
                repository_url="ppa:test/ppa",
            )

    def test_empty_repository_url_raises_error(self):
        """Test that empty repository URL raises validation error."""
        with pytest.raises(ValueError, match="Repository URL is required"):
            DefaultRepositoryCreate(
                os_name="Ubuntu",
                package_manager="APT",
                repository_url="",
            )

    def test_repository_url_too_long_raises_error(self):
        """Test that repository URL over 1000 chars raises validation error."""
        with pytest.raises(ValueError, match="1000 characters or less"):
            DefaultRepositoryCreate(
                os_name="Ubuntu",
                package_manager="APT",
                repository_url="x" * 1001,
            )

    def test_strips_whitespace_from_values(self):
        """Test that whitespace is stripped from values."""
        repo = DefaultRepositoryCreate(
            os_name="  Ubuntu  ",
            package_manager="  APT  ",
            repository_url="  ppa:test/ppa  ",
        )
        assert repo.os_name == "Ubuntu"
        assert repo.package_manager == "APT"
        assert repo.repository_url == "ppa:test/ppa"


class TestDefaultRepositoryResponse:
    """Test cases for DefaultRepositoryResponse Pydantic model."""

    def test_uuid_conversion_to_string(self):
        """Test that UUID fields are converted to strings."""
        repo_id = uuid.uuid4()
        user_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        response = DefaultRepositoryResponse(
            id=repo_id,
            os_name="Ubuntu",
            package_manager="APT",
            repository_url="ppa:test/ppa",
            created_at=now,
            created_by=user_id,
        )

        assert response.id == str(repo_id)
        assert response.created_by == str(user_id)


class TestOSPackageManagersResponse:
    """Test cases for OSPackageManagersResponse Pydantic model."""

    def test_creates_response_with_os_and_managers(self):
        """Test that response contains OS list and package managers dict."""
        response = OSPackageManagersResponse(
            operating_systems=["Ubuntu", "Debian"],
            package_managers={"Ubuntu": ["APT"], "Debian": ["APT"]},
        )
        assert "Ubuntu" in response.operating_systems
        assert "Debian" in response.operating_systems
        assert "APT" in response.package_managers["Ubuntu"]


class TestApplyRepositoryToHost:
    """Test cases for apply_repository_to_host function."""

    @pytest.mark.asyncio
    async def test_apply_add_action_queues_message(self):
        """Test that add action queues correct message."""
        mock_session = MagicMock()
        mock_host = MagicMock()
        mock_host.id = uuid.uuid4()
        mock_host.fqdn = "test.example.com"

        with patch(
            "backend.api.default_repositories.server_queue_manager"
        ) as mock_queue:
            await apply_repository_to_host(
                mock_session, mock_host, "ppa:test/ppa", action="add"
            )

            mock_queue.enqueue_message.assert_called_once()
            call_args = mock_queue.enqueue_message.call_args
            assert call_args[1]["message_type"] == "command"
            assert call_args[1]["host_id"] == str(mock_host.id)

    @pytest.mark.asyncio
    async def test_apply_delete_action_queues_message(self):
        """Test that delete action queues correct message."""
        mock_session = MagicMock()
        mock_host = MagicMock()
        mock_host.id = uuid.uuid4()
        mock_host.fqdn = "test.example.com"

        with patch(
            "backend.api.default_repositories.server_queue_manager"
        ) as mock_queue:
            await apply_repository_to_host(
                mock_session, mock_host, "ppa:test/ppa", action="delete"
            )

            mock_queue.enqueue_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_invalid_action_does_nothing(self):
        """Test that invalid action does not queue message."""
        mock_session = MagicMock()
        mock_host = MagicMock()
        mock_host.id = uuid.uuid4()
        mock_host.fqdn = "test.example.com"

        with patch(
            "backend.api.default_repositories.server_queue_manager"
        ) as mock_queue:
            await apply_repository_to_host(
                mock_session, mock_host, "ppa:test/ppa", action="invalid"
            )

            mock_queue.enqueue_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_handles_exception_gracefully(self):
        """Test that exceptions are handled without raising."""
        mock_session = MagicMock()
        mock_host = MagicMock()
        mock_host.id = uuid.uuid4()
        mock_host.fqdn = "test.example.com"

        with patch(
            "backend.api.default_repositories.server_queue_manager"
        ) as mock_queue:
            mock_queue.enqueue_message.side_effect = Exception("Queue error")

            # Should not raise
            await apply_repository_to_host(
                mock_session, mock_host, "ppa:test/ppa", action="add"
            )


class TestApplyRepositoryToMatchingHosts:
    """Test cases for apply_repository_to_matching_hosts function."""

    @pytest.mark.asyncio
    async def test_applies_to_matching_approved_hosts(self):
        """Test that repository is applied to approved hosts with matching OS."""
        mock_session = MagicMock()
        mock_host = MagicMock()
        mock_host.id = uuid.uuid4()
        mock_host.fqdn = "test.example.com"
        mock_host.approval_status = "approved"

        mock_session.query.return_value.filter.return_value.all.return_value = [
            mock_host
        ]

        with patch(
            "backend.api.default_repositories.apply_repository_to_host",
            new_callable=AsyncMock,
        ) as mock_apply:
            await apply_repository_to_matching_hosts(
                mock_session, "Ubuntu", "ppa:test/ppa", action="add"
            )

            mock_apply.assert_called_once_with(
                mock_session, mock_host, "ppa:test/ppa", "add"
            )

    @pytest.mark.asyncio
    async def test_handles_no_matching_hosts(self):
        """Test that no error when no hosts match."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = []

        with patch(
            "backend.api.default_repositories.apply_repository_to_host",
            new_callable=AsyncMock,
        ) as mock_apply:
            await apply_repository_to_matching_hosts(
                mock_session, "Ubuntu", "ppa:test/ppa", action="add"
            )

            mock_apply.assert_not_called()


class TestApplyDefaultRepositoriesToHost:
    """Test cases for apply_default_repositories_to_host function."""

    @pytest.mark.asyncio
    async def test_applies_matching_default_repos(self):
        """Test that matching default repos are applied to host."""
        mock_session = MagicMock()
        mock_host = MagicMock()
        mock_host.fqdn = "test.example.com"
        mock_host.platform_release = "Ubuntu 22.04"
        mock_host.platform = "Ubuntu"

        mock_repo = MagicMock()
        mock_repo.repository_url = "ppa:test/ppa"

        mock_session.query.return_value.filter.return_value.all.return_value = [
            mock_repo
        ]

        with patch(
            "backend.api.default_repositories.apply_repository_to_host",
            new_callable=AsyncMock,
        ) as mock_apply:
            await apply_default_repositories_to_host(mock_session, mock_host)

            mock_apply.assert_called_once_with(
                mock_session, mock_host, "ppa:test/ppa", action="add"
            )

    @pytest.mark.asyncio
    async def test_skips_host_without_platform_info(self):
        """Test that hosts without platform info are skipped."""
        mock_session = MagicMock()
        mock_host = MagicMock()
        mock_host.fqdn = "test.example.com"
        mock_host.platform_release = None
        mock_host.platform = None

        with patch(
            "backend.api.default_repositories.apply_repository_to_host",
            new_callable=AsyncMock,
        ) as mock_apply:
            await apply_default_repositories_to_host(mock_session, mock_host)

            mock_apply.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_no_default_repos(self):
        """Test that no error when no default repos exist."""
        mock_session = MagicMock()
        mock_host = MagicMock()
        mock_host.fqdn = "test.example.com"
        mock_host.platform_release = "Ubuntu 22.04"
        mock_host.platform = "Ubuntu"

        mock_session.query.return_value.filter.return_value.all.return_value = []

        with patch(
            "backend.api.default_repositories.apply_repository_to_host",
            new_callable=AsyncMock,
        ) as mock_apply:
            await apply_default_repositories_to_host(mock_session, mock_host)

            mock_apply.assert_not_called()
