"""
Tests for backend/api/packages_helpers.py module.
Tests package management helper functions.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


class TestGetPackagesSummarySync:
    """Tests for get_packages_summary_sync function."""

    @patch("backend.api.packages_helpers.db_module")
    @patch("backend.api.packages_helpers.sessionmaker")
    def test_get_packages_summary_success(self, mock_sessionmaker, mock_db_module):
        """Test successful package summary retrieval."""
        from backend.api.packages_helpers import get_packages_summary_sync

        mock_engine = MagicMock()
        mock_db_module.get_engine.return_value = mock_engine

        # Mock query results
        mock_result1 = MagicMock()
        mock_result1.os_name = "Ubuntu"
        mock_result1.os_version = "22.04"
        mock_result1.package_manager = "apt"
        mock_result1.package_count = 100

        mock_result2 = MagicMock()
        mock_result2.os_name = "Ubuntu"
        mock_result2.os_version = "22.04"
        mock_result2.package_manager = "snap"
        mock_result2.package_count = 50

        mock_session = MagicMock()
        mock_session.query.return_value.group_by.return_value.all.return_value = [
            mock_result1,
            mock_result2,
        ]
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        result = get_packages_summary_sync()

        assert len(result) == 1
        assert result[0]["os_name"] == "Ubuntu"
        assert result[0]["os_version"] == "22.04"
        assert result[0]["total_packages"] == 150
        assert len(result[0]["package_managers"]) == 2

    @patch("backend.api.packages_helpers.db_module")
    @patch("backend.api.packages_helpers.sessionmaker")
    def test_get_packages_summary_multiple_os(self, mock_sessionmaker, mock_db_module):
        """Test package summary with multiple OS versions."""
        from backend.api.packages_helpers import get_packages_summary_sync

        mock_engine = MagicMock()
        mock_db_module.get_engine.return_value = mock_engine

        mock_result1 = MagicMock()
        mock_result1.os_name = "Ubuntu"
        mock_result1.os_version = "22.04"
        mock_result1.package_manager = "apt"
        mock_result1.package_count = 100

        mock_result2 = MagicMock()
        mock_result2.os_name = "Debian"
        mock_result2.os_version = "12"
        mock_result2.package_manager = "apt"
        mock_result2.package_count = 80

        mock_session = MagicMock()
        mock_session.query.return_value.group_by.return_value.all.return_value = [
            mock_result1,
            mock_result2,
        ]
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        result = get_packages_summary_sync()

        assert len(result) == 2
        # Should be sorted alphabetically by OS name
        assert result[0]["os_name"] == "Debian"
        assert result[1]["os_name"] == "Ubuntu"

    @patch("backend.api.packages_helpers.db_module")
    @patch("backend.api.packages_helpers.sessionmaker")
    def test_get_packages_summary_empty(self, mock_sessionmaker, mock_db_module):
        """Test package summary with no packages."""
        from backend.api.packages_helpers import get_packages_summary_sync

        mock_engine = MagicMock()
        mock_db_module.get_engine.return_value = mock_engine

        mock_session = MagicMock()
        mock_session.query.return_value.group_by.return_value.all.return_value = []
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        result = get_packages_summary_sync()

        assert result == []

    @patch("backend.api.packages_helpers.db_module")
    @patch("backend.api.packages_helpers.sessionmaker")
    def test_get_packages_summary_exception(self, mock_sessionmaker, mock_db_module):
        """Test package summary handles exceptions."""
        from backend.api.packages_helpers import get_packages_summary_sync

        mock_engine = MagicMock()
        mock_db_module.get_engine.return_value = mock_engine

        mock_session = MagicMock()
        mock_session.query.side_effect = Exception("Database error")
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        with pytest.raises(HTTPException) as exc_info:
            get_packages_summary_sync()

        assert exc_info.value.status_code == 500
        assert "Database error" in exc_info.value.detail


class TestSearchPackagesCountSync:
    """Tests for search_packages_count_sync function."""

    @patch("backend.api.packages_helpers.db_module")
    @patch("backend.api.packages_helpers.sessionmaker")
    def test_search_count_basic(self, mock_sessionmaker, mock_db_module):
        """Test basic package count search."""
        from backend.api.packages_helpers import search_packages_count_sync

        mock_engine = MagicMock()
        mock_db_module.get_engine.return_value = mock_engine

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.count.return_value = 42
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        result = search_packages_count_sync(
            query="python", os_name=None, os_version=None, package_manager=None
        )

        assert result == {"total_count": 42}

    @patch("backend.api.packages_helpers.db_module")
    @patch("backend.api.packages_helpers.sessionmaker")
    def test_search_count_with_os_name(self, mock_sessionmaker, mock_db_module):
        """Test package count search with OS name filter."""
        from backend.api.packages_helpers import search_packages_count_sync

        mock_engine = MagicMock()
        mock_db_module.get_engine.return_value = mock_engine

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 25
        mock_session.query.return_value = mock_query
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        result = search_packages_count_sync(
            query="python", os_name="Ubuntu", os_version=None, package_manager=None
        )

        assert result == {"total_count": 25}

    @patch("backend.api.packages_helpers.db_module")
    @patch("backend.api.packages_helpers.sessionmaker")
    def test_search_count_with_all_filters(self, mock_sessionmaker, mock_db_module):
        """Test package count search with all filters."""
        from backend.api.packages_helpers import search_packages_count_sync

        mock_engine = MagicMock()
        mock_db_module.get_engine.return_value = mock_engine

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 10
        mock_session.query.return_value = mock_query
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        result = search_packages_count_sync(
            query="python", os_name="Ubuntu", os_version="22.04", package_manager="apt"
        )

        assert result == {"total_count": 10}

    @patch("backend.api.packages_helpers.db_module")
    @patch("backend.api.packages_helpers.sessionmaker")
    def test_search_count_exception(self, mock_sessionmaker, mock_db_module):
        """Test package count search handles exceptions."""
        from backend.api.packages_helpers import search_packages_count_sync

        mock_engine = MagicMock()
        mock_db_module.get_engine.return_value = mock_engine

        mock_session = MagicMock()
        mock_session.query.side_effect = Exception("Count error")
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        with pytest.raises(HTTPException) as exc_info:
            search_packages_count_sync(
                query="python", os_name=None, os_version=None, package_manager=None
            )

        assert exc_info.value.status_code == 500
        assert "Count error" in exc_info.value.detail


class TestSearchPackagesSync:
    """Tests for search_packages_sync function."""

    @patch("backend.api.packages_helpers.db_module")
    @patch("backend.api.packages_helpers.sessionmaker")
    def test_search_packages_basic(self, mock_sessionmaker, mock_db_module):
        """Test basic package search."""
        from backend.api.packages_helpers import search_packages_sync

        mock_engine = MagicMock()
        mock_db_module.get_engine.return_value = mock_engine

        mock_pkg = MagicMock()
        mock_pkg.package_name = "python3"
        mock_pkg.package_version = "3.10.0"
        mock_pkg.package_description = "Python 3 interpreter"
        mock_pkg.package_manager = "apt"

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_pkg]
        mock_session.query.return_value = mock_query
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        result = search_packages_sync(
            query="python",
            os_name=None,
            os_version=None,
            package_manager=None,
            limit=10,
            offset=0,
        )

        assert len(result) == 1
        assert result[0]["name"] == "python3"
        assert result[0]["version"] == "3.10.0"
        assert result[0]["description"] == "Python 3 interpreter"
        assert result[0]["package_manager"] == "apt"

    @patch("backend.api.packages_helpers.db_module")
    @patch("backend.api.packages_helpers.sessionmaker")
    def test_search_packages_with_filters(self, mock_sessionmaker, mock_db_module):
        """Test package search with filters."""
        from backend.api.packages_helpers import search_packages_sync

        mock_engine = MagicMock()
        mock_db_module.get_engine.return_value = mock_engine

        mock_pkg = MagicMock()
        mock_pkg.package_name = "python3-pip"
        mock_pkg.package_version = "22.0.0"
        mock_pkg.package_description = "Python package installer"
        mock_pkg.package_manager = "apt"

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_pkg]
        mock_session.query.return_value = mock_query
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        result = search_packages_sync(
            query="python",
            os_name="Ubuntu",
            os_version="22.04",
            package_manager="apt",
            limit=20,
            offset=0,
        )

        assert len(result) == 1
        assert result[0]["name"] == "python3-pip"

    @patch("backend.api.packages_helpers.db_module")
    @patch("backend.api.packages_helpers.sessionmaker")
    def test_search_packages_empty_result(self, mock_sessionmaker, mock_db_module):
        """Test package search with no results."""
        from backend.api.packages_helpers import search_packages_sync

        mock_engine = MagicMock()
        mock_db_module.get_engine.return_value = mock_engine

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_session.query.return_value = mock_query
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        result = search_packages_sync(
            query="nonexistent",
            os_name=None,
            os_version=None,
            package_manager=None,
            limit=10,
            offset=0,
        )

        assert result == []

    @patch("backend.api.packages_helpers.db_module")
    @patch("backend.api.packages_helpers.sessionmaker")
    def test_search_packages_exception(self, mock_sessionmaker, mock_db_module):
        """Test package search handles exceptions."""
        from backend.api.packages_helpers import search_packages_sync

        mock_engine = MagicMock()
        mock_db_module.get_engine.return_value = mock_engine

        mock_session = MagicMock()
        mock_session.query.side_effect = Exception("Search error")
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        with pytest.raises(HTTPException) as exc_info:
            search_packages_sync(
                query="python",
                os_name=None,
                os_version=None,
                package_manager=None,
                limit=10,
                offset=0,
            )

        assert exc_info.value.status_code == 500
        assert "Search error" in exc_info.value.detail

    @patch("backend.api.packages_helpers.db_module")
    @patch("backend.api.packages_helpers.sessionmaker")
    def test_search_packages_pagination(self, mock_sessionmaker, mock_db_module):
        """Test package search with pagination."""
        from backend.api.packages_helpers import search_packages_sync

        mock_engine = MagicMock()
        mock_db_module.get_engine.return_value = mock_engine

        mock_pkg1 = MagicMock()
        mock_pkg1.package_name = "python3-dev"
        mock_pkg1.package_version = "3.10.0"
        mock_pkg1.package_description = "Python 3 development files"
        mock_pkg1.package_manager = "apt"

        mock_pkg2 = MagicMock()
        mock_pkg2.package_name = "python3-doc"
        mock_pkg2.package_version = "3.10.0"
        mock_pkg2.package_description = "Python 3 documentation"
        mock_pkg2.package_manager = "apt"

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_pkg1, mock_pkg2]
        mock_session.query.return_value = mock_query
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        result = search_packages_sync(
            query="python",
            os_name=None,
            os_version=None,
            package_manager=None,
            limit=2,
            offset=5,
        )

        assert len(result) == 2
        mock_query.offset.assert_called_with(5)
        mock_query.limit.assert_called_with(2)
