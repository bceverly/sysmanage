"""
Tests for backend/persistence/db.py module.
Tests database connection and session management.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class TestBase:
    """Tests for Base declarative base."""

    def test_base_exists(self):
        """Test Base declarative base exists."""
        from backend.persistence.db import Base

        assert Base is not None

    def test_base_is_declarative(self):
        """Test Base is a declarative base."""
        from backend.persistence.db import Base

        # Declarative bases have a metadata attribute
        assert hasattr(Base, "metadata")


class TestTestMode:
    """Tests for test mode functions."""

    def setup_method(self):
        """Set up test fixtures."""
        from backend.persistence import db

        # Save original state
        self._orig_is_test_mode = db.IS_TEST_MODE
        self._orig_test_engine = db.TEST_ENGINE
        self._orig_test_session_local = db.TEST_SESSION_LOCAL

    def teardown_method(self):
        """Restore original state."""
        from backend.persistence import db

        db.IS_TEST_MODE = self._orig_is_test_mode
        db.TEST_ENGINE = self._orig_test_engine
        db.TEST_SESSION_LOCAL = self._orig_test_session_local

    def test_enter_test_mode_sets_flag(self):
        """Test enter_test_mode sets IS_TEST_MODE flag."""
        from backend.persistence import db

        test_engine = create_engine("sqlite:///:memory:")
        db.enter_test_mode(test_engine)

        assert db.IS_TEST_MODE is True

    def test_enter_test_mode_sets_engine(self):
        """Test enter_test_mode sets TEST_ENGINE."""
        from backend.persistence import db

        test_engine = create_engine("sqlite:///:memory:")
        db.enter_test_mode(test_engine)

        assert db.TEST_ENGINE is test_engine

    def test_enter_test_mode_creates_session_local(self):
        """Test enter_test_mode creates TEST_SESSION_LOCAL."""
        from backend.persistence import db

        test_engine = create_engine("sqlite:///:memory:")
        db.enter_test_mode(test_engine)

        assert db.TEST_SESSION_LOCAL is not None

    def test_exit_test_mode_clears_flag(self):
        """Test exit_test_mode clears IS_TEST_MODE flag."""
        from backend.persistence import db

        test_engine = create_engine("sqlite:///:memory:")
        db.enter_test_mode(test_engine)
        db.exit_test_mode()

        assert db.IS_TEST_MODE is False

    def test_exit_test_mode_clears_engine(self):
        """Test exit_test_mode clears TEST_ENGINE."""
        from backend.persistence import db

        test_engine = create_engine("sqlite:///:memory:")
        db.enter_test_mode(test_engine)
        db.exit_test_mode()

        assert db.TEST_ENGINE is None

    def test_exit_test_mode_clears_session_local(self):
        """Test exit_test_mode clears TEST_SESSION_LOCAL."""
        from backend.persistence import db

        test_engine = create_engine("sqlite:///:memory:")
        db.enter_test_mode(test_engine)
        db.exit_test_mode()

        assert db.TEST_SESSION_LOCAL is None


class TestGetEngine:
    """Tests for get_engine function."""

    def setup_method(self):
        """Set up test fixtures."""
        from backend.persistence import db

        self._orig_is_test_mode = db.IS_TEST_MODE
        self._orig_test_engine = db.TEST_ENGINE
        self._orig_test_session_local = db.TEST_SESSION_LOCAL

    def teardown_method(self):
        """Restore original state."""
        from backend.persistence import db

        db.IS_TEST_MODE = self._orig_is_test_mode
        db.TEST_ENGINE = self._orig_test_engine
        db.TEST_SESSION_LOCAL = self._orig_test_session_local

    def test_get_engine_returns_test_engine_in_test_mode(self):
        """Test get_engine returns test engine in test mode."""
        from backend.persistence import db

        test_engine = create_engine("sqlite:///:memory:")
        db.enter_test_mode(test_engine)

        result = db.get_engine()

        assert result is test_engine

    def test_get_engine_raises_without_test_engine(self):
        """Test get_engine raises RuntimeError if test engine not set."""
        from backend.persistence import db

        db.IS_TEST_MODE = True
        db.TEST_ENGINE = None

        with pytest.raises(RuntimeError) as exc_info:
            db.get_engine()

        assert "no test engine is configured" in str(exc_info.value)


class TestGetDb:
    """Tests for get_db function."""

    def setup_method(self):
        """Set up test fixtures."""
        from backend.persistence import db

        self._orig_is_test_mode = db.IS_TEST_MODE
        self._orig_test_engine = db.TEST_ENGINE
        self._orig_test_session_local = db.TEST_SESSION_LOCAL

    def teardown_method(self):
        """Restore original state."""
        from backend.persistence import db

        db.IS_TEST_MODE = self._orig_is_test_mode
        db.TEST_ENGINE = self._orig_test_engine
        db.TEST_SESSION_LOCAL = self._orig_test_session_local

    def test_get_db_yields_session_in_test_mode(self):
        """Test get_db yields a session in test mode."""
        from backend.persistence import db

        test_engine = create_engine("sqlite:///:memory:")
        db.enter_test_mode(test_engine)

        generator = db.get_db()
        session = next(generator)

        assert session is not None
        # Clean up
        try:
            next(generator)
        except StopIteration:
            pass

    def test_get_db_closes_session(self):
        """Test get_db closes session in finally block."""
        from backend.persistence import db

        test_engine = create_engine("sqlite:///:memory:")
        db.enter_test_mode(test_engine)

        generator = db.get_db()
        session = next(generator)
        original_close = session.close
        close_called = []
        session.close = lambda: (close_called.append(True), original_close())

        # Exhaust the generator
        try:
            next(generator)
        except StopIteration:
            pass

        assert len(close_called) == 1

    def test_get_db_raises_without_test_session(self):
        """Test get_db raises RuntimeError if test session not set."""
        from backend.persistence import db

        db.IS_TEST_MODE = True
        db.TEST_SESSION_LOCAL = None

        generator = db.get_db()
        with pytest.raises(RuntimeError) as exc_info:
            next(generator)

        assert "no test session is configured" in str(exc_info.value)


class TestGetSessionLocal:
    """Tests for get_session_local function."""

    def setup_method(self):
        """Set up test fixtures."""
        from backend.persistence import db

        self._orig_is_test_mode = db.IS_TEST_MODE
        self._orig_test_engine = db.TEST_ENGINE
        self._orig_test_session_local = db.TEST_SESSION_LOCAL

    def teardown_method(self):
        """Restore original state."""
        from backend.persistence import db

        db.IS_TEST_MODE = self._orig_is_test_mode
        db.TEST_ENGINE = self._orig_test_engine
        db.TEST_SESSION_LOCAL = self._orig_test_session_local

    def test_get_session_local_returns_test_session_in_test_mode(self):
        """Test get_session_local returns test session in test mode."""
        from backend.persistence import db

        test_engine = create_engine("sqlite:///:memory:")
        db.enter_test_mode(test_engine)

        result = db.get_session_local()

        assert result is db.TEST_SESSION_LOCAL


class TestGetDatabaseUrl:
    """Tests for get_database_url function."""

    def setup_method(self):
        """Set up test fixtures."""
        from backend.persistence import db

        self._orig_is_test_mode = db.IS_TEST_MODE
        self._orig_test_engine = db.TEST_ENGINE
        self._orig_test_session_local = db.TEST_SESSION_LOCAL

    def teardown_method(self):
        """Restore original state."""
        from backend.persistence import db

        db.IS_TEST_MODE = self._orig_is_test_mode
        db.TEST_ENGINE = self._orig_test_engine
        db.TEST_SESSION_LOCAL = self._orig_test_session_local

    def test_get_database_url_returns_test_url_in_test_mode(self):
        """Test get_database_url returns test engine URL in test mode."""
        from backend.persistence import db

        test_engine = create_engine("sqlite:///:memory:")
        db.enter_test_mode(test_engine)

        result = db.get_database_url()

        assert "memory" in result or "sqlite" in result

    def test_get_database_url_raises_without_test_engine(self):
        """Test get_database_url raises RuntimeError if no test engine."""
        from backend.persistence import db

        db.IS_TEST_MODE = True
        db.TEST_ENGINE = None

        with pytest.raises(RuntimeError) as exc_info:
            db.get_database_url()

        assert "no test engine is configured" in str(exc_info.value)


class TestLegacyFunctions:
    """Tests for legacy backward compatibility functions."""

    def setup_method(self):
        """Set up test fixtures."""
        from backend.persistence import db

        self._orig_is_test_mode = db.IS_TEST_MODE
        self._orig_test_engine = db.TEST_ENGINE
        self._orig_test_session_local = db.TEST_SESSION_LOCAL

    def teardown_method(self):
        """Restore original state."""
        from backend.persistence import db

        db.IS_TEST_MODE = self._orig_is_test_mode
        db.TEST_ENGINE = self._orig_test_engine
        db.TEST_SESSION_LOCAL = self._orig_test_session_local

    def test_set_test_engine_calls_enter_test_mode(self):
        """Test set_test_engine is alias for enter_test_mode."""
        from backend.persistence import db

        test_engine = create_engine("sqlite:///:memory:")
        db.set_test_engine(test_engine)

        assert db.IS_TEST_MODE is True
        assert db.TEST_ENGINE is test_engine

    def test_reset_database_calls_exit_test_mode(self):
        """Test reset_database is alias for exit_test_mode."""
        from backend.persistence import db

        test_engine = create_engine("sqlite:///:memory:")
        db.enter_test_mode(test_engine)
        db.reset_database()

        assert db.IS_TEST_MODE is False
        assert db.TEST_ENGINE is None


class TestModuleLevelAccessors:
    """Tests for module-level accessors."""

    def test_session_local_is_callable(self):
        """Test SessionLocal is callable."""
        from backend.persistence.db import SessionLocal

        assert callable(SessionLocal)

    def test_engine_is_callable(self):
        """Test engine accessor is callable."""
        from backend.persistence.db import engine

        assert callable(engine)


class TestAlembicDatabaseUrl:
    """Tests for _get_alembic_database_url function."""

    @patch.dict("os.environ", {"DATABASE_URL": "postgresql://test:test@localhost/test"})
    def test_uses_environment_variable_when_set(self):
        """Test uses DATABASE_URL environment variable when set."""
        from backend.persistence.db import _get_alembic_database_url

        result = _get_alembic_database_url()

        assert result == "postgresql://test:test@localhost/test"

    @patch.dict("os.environ", {}, clear=True)
    @patch("backend.persistence.db.get_database_url")
    def test_uses_config_when_env_not_set(self, mock_get_url):
        """Test uses config when DATABASE_URL not in environment."""
        import os

        # Ensure DATABASE_URL is not set
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]

        mock_get_url.return_value = "postgresql://config:config@localhost/config"
        from backend.persistence.db import _get_alembic_database_url

        result = _get_alembic_database_url()

        assert result == "postgresql://config:config@localhost/config"

    @patch.dict("os.environ", {}, clear=True)
    @patch("backend.persistence.db.get_database_url")
    def test_fallback_on_exception(self, mock_get_url):
        """Test uses fallback URL when get_database_url raises exception."""
        import os

        # Ensure DATABASE_URL is not set
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]

        mock_get_url.side_effect = Exception("Config not available")
        from backend.persistence.db import _get_alembic_database_url

        result = _get_alembic_database_url()

        assert "postgresql://sysmanage" in result
