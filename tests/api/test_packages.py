"""Unit tests for package management API endpoints.
Tests all package-related endpoints using database fixtures.
"""

import pytest
from datetime import datetime, timezone
from backend.persistence.models import AvailablePackage


class TestPackagesAPI:
    """Test cases for package management API endpoints."""

    @pytest.fixture
    def sample_packages(self, session):
        """Create sample packages in the database."""
        now = datetime.now(timezone.utc)
        packages = [
            AvailablePackage(
                package_name="nginx",
                package_version="1.18.0",
                package_description="High performance web server",
                package_manager="apt",
                os_name="Ubuntu",
                os_version="22.04",
                last_updated=now,
                created_at=now,
            ),
            AvailablePackage(
                package_name="python3",
                package_version="3.10.12",
                package_description="Python 3 programming language",
                package_manager="apt",
                os_name="Ubuntu",
                os_version="22.04",
                last_updated=now,
                created_at=now,
            ),
            AvailablePackage(
                package_name="docker",
                package_version="24.0.5",
                package_description="Container platform",
                package_manager="snap",
                os_name="Ubuntu",
                os_version="22.04",
                last_updated=now,
                created_at=now,
            ),
            AvailablePackage(
                package_name="httpd",
                package_version="2.4.37",
                package_description="Apache HTTP Server",
                package_manager="yum",
                os_name="CentOS",
                os_version="8",
                last_updated=now,
                created_at=now,
            ),
        ]

        for package in packages:
            session.add(package)
        session.commit()
        return packages

    def test_get_packages_summary_success(self, client, auth_headers, sample_packages):
        """Test successful retrieval of package summary."""
        response = client.get("/api/packages/summary", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert len(data) == 2  # Ubuntu and CentOS

        # Check Ubuntu summary
        ubuntu_summary = next(item for item in data if item["os_name"] == "Ubuntu")
        assert ubuntu_summary["os_version"] == "22.04"
        assert ubuntu_summary["total_packages"] == 3
        assert len(ubuntu_summary["package_managers"]) == 2  # apt and snap

        # Check CentOS summary
        centos_summary = next(item for item in data if item["os_name"] == "CentOS")
        assert centos_summary["os_version"] == "8"
        assert centos_summary["total_packages"] == 1
        assert len(centos_summary["package_managers"]) == 1  # yum

    def test_get_packages_summary_empty(self, client, auth_headers):
        """Test package summary with no packages."""
        response = client.get("/api/packages/summary", headers=auth_headers)

        if response.status_code != 200:
            print(f"Status Code: {response.status_code}")
            print(f"Response Text: {response.text}")
            try:
                print(f"Response JSON: {response.json()}")
            except:
                pass

        assert response.status_code == 200
        data = response.json()
        assert data == []

    def test_get_package_managers_success(self, client, auth_headers, sample_packages):
        """Test successful retrieval of package managers."""
        response = client.get("/api/packages/managers", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert len(data) == 3
        assert "apt" in data
        assert "yum" in data
        assert "snap" in data
        assert data == sorted(data)  # Should be sorted

    def test_get_package_managers_with_os_filter(
        self, client, auth_headers, sample_packages
    ):
        """Test package managers filtered by OS."""
        response = client.get(
            "/api/packages/managers?os_name=Ubuntu", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data) == 2
        assert "apt" in data
        assert "snap" in data
        assert "yum" not in data

    def test_get_package_managers_with_version_filter(
        self, client, auth_headers, sample_packages
    ):
        """Test package managers filtered by OS version."""
        response = client.get(
            "/api/packages/managers?os_name=Ubuntu&os_version=22.04",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data) == 2
        assert "apt" in data
        assert "snap" in data

    def test_search_packages_success(self, client, auth_headers, sample_packages):
        """Test successful package search."""
        response = client.get("/api/packages/search?query=nginx", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert len(data) == 1
        package = data[0]
        assert package["name"] == "nginx"
        assert package["version"] == "1.18.0"
        assert package["package_manager"] == "apt"
        assert "web server" in package["description"]

    def test_search_packages_multiple_results(
        self, client, auth_headers, sample_packages
    ):
        """Test package search with multiple results."""
        response = client.get("/api/packages/search?query=python", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert len(data) == 1
        assert data[0]["name"] == "python3"

    def test_search_packages_with_os_filter(
        self, client, auth_headers, sample_packages
    ):
        """Test package search filtered by OS."""
        response = client.get(
            "/api/packages/search?query=http&os_name=CentOS", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data) == 1
        assert data[0]["name"] == "httpd"
        assert data[0]["package_manager"] == "yum"

    def test_search_packages_with_manager_filter(
        self, client, auth_headers, sample_packages
    ):
        """Test package search filtered by package manager."""
        response = client.get(
            "/api/packages/search?query=docker&package_manager=snap",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data) == 1
        assert data[0]["name"] == "docker"
        assert data[0]["package_manager"] == "snap"

    def test_search_packages_with_pagination(
        self, client, auth_headers, sample_packages
    ):
        """Test package search with pagination."""
        response = client.get(
            "/api/packages/search?query=p&limit=2&offset=0", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Should return exactly 2 packages
        assert len(data) == 2

    def test_search_packages_no_results(self, client, auth_headers, sample_packages):
        """Test package search with no results."""
        response = client.get(
            "/api/packages/search?query=nonexistent", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0

    def test_search_packages_missing_query(self, client, auth_headers):
        """Test package search without query parameter."""
        response = client.get("/api/packages/search", headers=auth_headers)
        assert response.status_code == 422  # Validation error

    def test_get_os_versions_success(self, client, auth_headers, sample_packages):
        """Test successful retrieval of OS versions."""
        response = client.get("/api/packages/os-versions", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert len(data) == 2

        os_versions_list = [(item["os_name"], item["os_version"]) for item in data]
        assert ("Ubuntu", "22.04") in os_versions_list
        assert ("CentOS", "8") in os_versions_list

    def test_get_packages_by_manager_success(
        self, client, auth_headers, sample_packages
    ):
        """Test successful retrieval of packages by manager."""
        response = client.get("/api/packages/by-manager/apt", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert len(data) == 2
        package_names = [pkg["name"] for pkg in data]
        assert "nginx" in package_names
        assert "python3" in package_names

        for package in data:
            assert package["package_manager"] == "apt"

    def test_get_packages_by_manager_with_os_filter(
        self, client, auth_headers, sample_packages
    ):
        """Test packages by manager filtered by OS."""
        response = client.get(
            "/api/packages/by-manager/apt?os_name=Ubuntu&os_version=22.04",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data) == 2
        for package in data:
            assert package["package_manager"] == "apt"

    def test_get_packages_by_manager_nonexistent(
        self, client, auth_headers, sample_packages
    ):
        """Test packages by non-existent manager."""
        response = client.get(
            "/api/packages/by-manager/nonexistent", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0

    def test_get_packages_by_manager_with_pagination(
        self, client, auth_headers, sample_packages
    ):
        """Test packages by manager with pagination."""
        response = client.get(
            "/api/packages/by-manager/apt?limit=1&offset=0", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

    # NOTE: test_database_error_handling was removed as it was only a placeholder
    # If database error handling tests are needed in the future, they should be
    # implemented with proper database failure simulation

    def test_search_packages_invalid_pagination(self, client, auth_headers):
        """Test package search with invalid pagination parameters."""
        # Test negative offset
        response = client.get(
            "/api/packages/search?query=nginx&offset=-1", headers=auth_headers
        )
        assert response.status_code == 422

        # Test zero limit
        response = client.get(
            "/api/packages/search?query=nginx&limit=0", headers=auth_headers
        )
        assert response.status_code == 422

        # Test limit too high
        response = client.get(
            "/api/packages/search?query=nginx&limit=1001", headers=auth_headers
        )
        assert response.status_code == 422

    def test_search_packages_case_insensitive(
        self, client, auth_headers, sample_packages
    ):
        """Test that package search is case insensitive."""
        response = client.get("/api/packages/search?query=NGINX", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "nginx"

    def test_packages_api_comprehensive_workflow(
        self, client, auth_headers, sample_packages
    ):
        """Test a comprehensive workflow using multiple endpoints."""
        # 1. Get summary
        summary_response = client.get("/api/packages/summary", headers=auth_headers)
        assert summary_response.status_code == 200

        # 2. Get available managers
        managers_response = client.get("/api/packages/managers", headers=auth_headers)
        assert managers_response.status_code == 200
        managers = managers_response.json()
        assert "apt" in managers

        # 3. Search for packages
        search_response = client.get(
            "/api/packages/search?query=nginx", headers=auth_headers
        )
        assert search_response.status_code == 200

        # 4. Get packages by manager
        by_manager_response = client.get(
            "/api/packages/by-manager/apt", headers=auth_headers
        )
        assert by_manager_response.status_code == 200

        # 5. Get OS versions
        os_versions_response = client.get(
            "/api/packages/os-versions", headers=auth_headers
        )
        assert os_versions_response.status_code == 200

    def test_unauthorized_requests_fail_properly(self):
        """Test that requests fail properly when not using authentication."""
        # This test deliberately doesn't use authentication to test auth failure
        from fastapi.testclient import TestClient
        from backend.main import app
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_lifespan(app):
            yield

        # Create a client without JWT mocking
        original_lifespan = app.router.lifespan_context
        app.router.lifespan_context = mock_lifespan

        try:
            with TestClient(app) as test_client:
                response = test_client.get("/api/packages/summary")
                # Should fail authentication (either 401 or 403)
                assert response.status_code in [401, 403]
        finally:
            app.router.lifespan_context = original_lifespan
