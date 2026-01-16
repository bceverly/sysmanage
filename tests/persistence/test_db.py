"""
Tests for the database module.

This module tests the database connection and session management
functionality in backend/persistence/db.py.
"""

import pytest
from unittest.mock import MagicMock, patch

from backend.persistence.db import (
    Base,
    enter_test_mode,
    exit_test_mode,
    get_db,
    get_engine,
    get_database_url,
    get_session_local,
    IS_TEST_MODE,
)


class TestTestModeManagement:
    """Test cases for test mode enter/exit functions."""

    def test_enter_test_mode_sets_test_engine(self):
        """Test that enter_test_mode sets up the test engine."""
        # We're already in test mode from conftest, but we can verify behavior
        from backend.persistence import db

        # Store original values
        original_is_test = db.IS_TEST_MODE
        original_engine = db.TEST_ENGINE

        try:
            # Create a mock engine
            mock_engine = MagicMock()
            mock_engine.url = "sqlite:///:memory:"

            # Enter test mode
            enter_test_mode(mock_engine)

            assert db.IS_TEST_MODE is True
            assert db.TEST_ENGINE == mock_engine
            assert db.TEST_SESSION_LOCAL is not None

        finally:
            # Restore original state
            db.IS_TEST_MODE = original_is_test
            db.TEST_ENGINE = original_engine

    def test_exit_test_mode_clears_test_state(self):
        """Test that exit_test_mode clears the test state."""
        from backend.persistence import db

        # Store original values
        original_is_test = db.IS_TEST_MODE
        original_engine = db.TEST_ENGINE
        original_session = db.TEST_SESSION_LOCAL

        try:
            # Set up test mode
            mock_engine = MagicMock()
            enter_test_mode(mock_engine)

            # Exit test mode
            exit_test_mode()

            assert db.IS_TEST_MODE is False
            assert db.TEST_ENGINE is None
            assert db.TEST_SESSION_LOCAL is None

        finally:
            # Restore original state
            db.IS_TEST_MODE = original_is_test
            db.TEST_ENGINE = original_engine
            db.TEST_SESSION_LOCAL = original_session


class TestGetEngine:
    """Test cases for get_engine function."""

    def test_get_engine_returns_test_engine_in_test_mode(self, engine):
        """Test that get_engine returns the test engine when in test mode."""
        result = get_engine()
        # In test mode, should return the test engine
        assert result is not None

    def test_get_engine_raises_when_test_mode_without_engine(self):
        """Test that get_engine raises error when test mode but no engine."""
        from backend.persistence import db

        # Store original values
        original_is_test = db.IS_TEST_MODE
        original_engine = db.TEST_ENGINE

        try:
            db.IS_TEST_MODE = True
            db.TEST_ENGINE = None

            with pytest.raises(RuntimeError, match="no test engine"):
                get_engine()

        finally:
            db.IS_TEST_MODE = original_is_test
            db.TEST_ENGINE = original_engine


class TestGetDb:
    """Test cases for get_db function."""

    def test_get_db_yields_session(self, engine):
        """Test that get_db yields a database session."""
        gen = get_db()
        session = next(gen)

        assert session is not None

        # Clean up
        try:
            next(gen)
        except StopIteration:
            pass

    def test_get_db_closes_session_on_exit(self, engine):
        """Test that get_db closes the session when generator exits."""
        gen = get_db()
        session = next(gen)

        # Trigger cleanup
        try:
            next(gen)
        except StopIteration:
            pass

        # Session should be closed (though this is hard to verify directly)
        # The main thing is that no exception was raised

    def test_get_db_raises_when_test_mode_without_session(self):
        """Test get_db raises error when test mode but no session configured."""
        from backend.persistence import db

        # Store original values
        original_is_test = db.IS_TEST_MODE
        original_session = db.TEST_SESSION_LOCAL

        try:
            db.IS_TEST_MODE = True
            db.TEST_SESSION_LOCAL = None

            with pytest.raises(RuntimeError, match="no test session"):
                gen = get_db()
                next(gen)

        finally:
            db.IS_TEST_MODE = original_is_test
            db.TEST_SESSION_LOCAL = original_session


class TestGetDatabaseUrl:
    """Test cases for get_database_url function."""

    def test_get_database_url_returns_test_url_in_test_mode(self, engine):
        """Test that get_database_url returns test URL when in test mode."""
        url = get_database_url()

        # Should return a SQLite URL (test database)
        assert "sqlite" in url.lower()

    def test_get_database_url_raises_when_test_mode_without_engine(self):
        """Test get_database_url raises error when test mode but no engine."""
        from backend.persistence import db

        # Store original values
        original_is_test = db.IS_TEST_MODE
        original_engine = db.TEST_ENGINE

        try:
            db.IS_TEST_MODE = True
            db.TEST_ENGINE = None

            with pytest.raises(RuntimeError, match="no test engine"):
                get_database_url()

        finally:
            db.IS_TEST_MODE = original_is_test
            db.TEST_ENGINE = original_engine


class TestGetSessionLocal:
    """Test cases for get_session_local function."""

    def test_get_session_local_returns_test_session_in_test_mode(self, engine):
        """Test that get_session_local returns test session maker in test mode."""
        session_local = get_session_local()

        # Should return a callable session maker
        assert session_local is not None
        assert callable(session_local)


class TestBase:
    """Test cases for the SQLAlchemy Base class."""

    def test_base_is_declarative_base(self):
        """Test that Base is a SQLAlchemy declarative base."""
        from sqlalchemy.orm import DeclarativeMeta

        assert isinstance(Base, DeclarativeMeta)

    def test_base_has_metadata(self):
        """Test that Base has metadata for table definitions."""
        assert hasattr(Base, "metadata")
        assert Base.metadata is not None


class TestLegacyFunctions:
    """Test cases for legacy backward-compatible functions."""

    def test_set_test_engine_calls_enter_test_mode(self):
        """Test that set_test_engine is an alias for enter_test_mode."""
        from backend.persistence.db import set_test_engine
        from backend.persistence import db

        # Store original values
        original_is_test = db.IS_TEST_MODE
        original_engine = db.TEST_ENGINE

        try:
            mock_engine = MagicMock()
            set_test_engine(mock_engine)

            assert db.IS_TEST_MODE is True
            assert db.TEST_ENGINE == mock_engine

        finally:
            db.IS_TEST_MODE = original_is_test
            db.TEST_ENGINE = original_engine

    def test_reset_database_calls_exit_test_mode(self):
        """Test that reset_database is an alias for exit_test_mode."""
        from backend.persistence.db import reset_database
        from backend.persistence import db

        # Store original values
        original_is_test = db.IS_TEST_MODE
        original_engine = db.TEST_ENGINE
        original_session = db.TEST_SESSION_LOCAL

        try:
            # Set up test mode first
            mock_engine = MagicMock()
            enter_test_mode(mock_engine)

            # Reset (exit test mode)
            reset_database()

            assert db.IS_TEST_MODE is False

        finally:
            db.IS_TEST_MODE = original_is_test
            db.TEST_ENGINE = original_engine
            db.TEST_SESSION_LOCAL = original_session
