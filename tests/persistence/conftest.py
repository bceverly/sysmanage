"""
Pytest configuration for persistence layer tests.

This conftest inherits fixtures from the parent tests/conftest.py.
"""

import pytest
from unittest.mock import MagicMock, patch

# Import fixtures from parent conftest - pytest will auto-discover them
# These fixtures are available: engine, db_session, session, mock_config


@pytest.fixture
def mock_postgres_engine():
    """Mock PostgreSQL engine for testing PostgreSQL-specific functionality."""
    with patch("sqlalchemy.create_engine") as mock:
        mock_engine = MagicMock()
        mock_engine.dialect.name = "postgresql"
        mock.return_value = mock_engine
        yield mock_engine


@pytest.fixture
def test_database_url():
    """Test database URL for persistence tests."""
    return "sqlite:///:memory:"
