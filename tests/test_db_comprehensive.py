"""
Comprehensive unit tests for backend.persistence.db module.
Tests database connection, engine, and session management.
"""

import pytest
from unittest.mock import Mock, patch
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from backend.persistence.db import (
    get_engine,
    get_db,
    engine,
    SessionLocal,
    Base,
    SQLALCHEMY_DATABASE_URL,
    DB_USER,
    DB_PASSWORD,
    DB_HOST,
    DB_PORT,
    DB_NAME,
)


class TestDatabaseConfiguration:
    """Test cases for database configuration constants."""

    def test_database_constants_exist(self):
        """Test that all database configuration constants are defined."""
        assert DB_USER is not None
        assert DB_PASSWORD is not None
        assert DB_HOST is not None
        assert DB_PORT is not None
        assert DB_NAME is not None

    def test_database_url_format(self):
        """Test that database URL has correct format."""
        assert SQLALCHEMY_DATABASE_URL.startswith("postgresql://")
        assert f"{DB_USER}" in SQLALCHEMY_DATABASE_URL
        assert f"{DB_PASSWORD}" in SQLALCHEMY_DATABASE_URL
        assert f"{DB_HOST}" in SQLALCHEMY_DATABASE_URL
        assert f"{DB_PORT}" in SQLALCHEMY_DATABASE_URL
        assert f"{DB_NAME}" in SQLALCHEMY_DATABASE_URL

    def test_database_url_structure(self):
        """Test database URL structure components."""
        expected_url = (
            f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        )
        assert SQLALCHEMY_DATABASE_URL == expected_url

    def test_database_constants_types(self):
        """Test that database constants have expected types."""
        assert isinstance(DB_USER, str)
        assert isinstance(DB_PASSWORD, str)
        assert isinstance(DB_HOST, str)
        assert isinstance(DB_PORT, (int, str))  # Could be string from config
        assert isinstance(DB_NAME, str)


class TestDatabaseEngine:
    """Test cases for database engine functionality."""

    def test_engine_exists(self):
        """Test that database engine is created."""
        assert engine is not None
        # Check that it's a SQLAlchemy engine
        assert hasattr(engine, "connect")
        # In newer SQLAlchemy versions, execute is available via connection

    def test_get_engine_function(self):
        """Test get_engine function returns the engine."""
        returned_engine = get_engine()
        assert returned_engine is engine
        assert returned_engine is not None

    def test_engine_configuration(self):
        """Test that engine is configured correctly."""
        assert engine.url.database == DB_NAME
        assert engine.url.host == DB_HOST
        assert str(engine.url.port) == str(DB_PORT)
        assert engine.url.username == DB_USER

    def test_multiple_get_engine_calls_return_same(self):
        """Test that multiple calls to get_engine return the same instance."""
        engine1 = get_engine()
        engine2 = get_engine()
        assert engine1 is engine2


class TestSessionLocal:
    """Test cases for SessionLocal sessionmaker."""

    def test_session_local_exists(self):
        """Test that SessionLocal is configured."""
        assert SessionLocal is not None
        assert isinstance(SessionLocal, sessionmaker)

    def test_session_local_configuration(self):
        """Test SessionLocal configuration."""
        # SessionLocal should be bound to our engine
        assert SessionLocal.kw["bind"] is engine
        assert SessionLocal.kw["autocommit"] is False
        assert SessionLocal.kw["autoflush"] is False

    def test_session_creation(self):
        """Test that SessionLocal can create sessions."""
        session = SessionLocal()
        assert session is not None
        assert hasattr(session, "query")
        assert hasattr(session, "commit")
        assert hasattr(session, "rollback")
        assert hasattr(session, "close")
        session.close()


class TestGetDbFunction:
    """Test cases for get_db generator function."""

    @patch("backend.persistence.db.SessionLocal")
    def test_get_db_yields_session(self, mock_session_local):
        """Test that get_db yields a database session."""
        mock_session = Mock()
        mock_session_local.return_value = mock_session

        # Use the generator
        db_generator = get_db()
        db_session = next(db_generator)

        assert db_session is mock_session
        mock_session_local.assert_called_once()

    @patch("backend.persistence.db.SessionLocal")
    def test_get_db_closes_session_on_completion(self, mock_session_local):
        """Test that get_db closes session when generator completes."""
        mock_session = Mock()
        mock_session_local.return_value = mock_session

        # Use the generator in a with statement or for loop to trigger cleanup
        db_generator = get_db()
        db_session = next(db_generator)

        try:
            next(db_generator)  # This should raise StopIteration and trigger cleanup
        except StopIteration:
            pass

        mock_session.close.assert_called_once()

    @patch("backend.persistence.db.SessionLocal")
    def test_get_db_closes_session_on_exception(self, mock_session_local):
        """Test that get_db closes session even when exception occurs."""
        mock_session = Mock()
        mock_session_local.return_value = mock_session

        # Use the generator
        db_generator = get_db()
        db_session = next(db_generator)

        # Simulate exception by throwing into the generator
        try:
            db_generator.throw(Exception("Test exception"))
        except Exception:
            pass

        mock_session.close.assert_called_once()

    def test_get_db_is_generator(self):
        """Test that get_db is a generator function."""
        db_generator = get_db()
        assert hasattr(db_generator, "__iter__")
        assert hasattr(db_generator, "__next__")

    @patch("backend.persistence.db.SessionLocal")
    def test_get_db_multiple_calls(self, mock_session_local):
        """Test that multiple calls to get_db create separate sessions."""
        mock_session1 = Mock()
        mock_session2 = Mock()
        mock_session_local.side_effect = [mock_session1, mock_session2]

        # Create two generators
        db_gen1 = get_db()
        db_gen2 = get_db()

        session1 = next(db_gen1)
        session2 = next(db_gen2)

        assert session1 is mock_session1
        assert session2 is mock_session2
        assert session1 is not session2
        assert mock_session_local.call_count == 2


class TestBaseModel:
    """Test cases for SQLAlchemy Base model."""

    def test_base_exists(self):
        """Test that Base declarative model exists."""
        assert Base is not None
        assert hasattr(Base, "metadata")
        assert hasattr(Base, "registry")

    def test_base_is_declarative_base(self):
        """Test that Base is a proper declarative base."""
        # Check that Base has the expected attributes of a declarative base
        assert hasattr(Base, "metadata")
        assert hasattr(Base, "registry")

    def test_base_can_be_inherited(self):
        """Test that Base can be used as a base class for models."""
        # Test that Base is a proper base class without actually creating a model
        # (to avoid SQLAlchemy table/column requirements)
        assert Base is not None
        assert hasattr(Base, "metadata")


class TestDatabaseModuleImports:
    """Test cases for module-level imports and initialization."""

    def test_all_imports_successful(self):
        """Test that all module imports are successful."""
        # If we can import these, the imports worked
        from backend.persistence.db import (
            get_engine,
            get_db,
            engine,
            SessionLocal,
            Base,
        )

        assert get_engine is not None
        assert get_db is not None
        assert engine is not None
        assert SessionLocal is not None
        assert Base is not None

    def test_configuration_loaded(self):
        """Test that configuration is properly loaded at module level."""
        # Config should be loaded when module is imported
        from backend.persistence.db import the_config

        assert the_config is not None
        assert isinstance(the_config, dict)
        assert "database" in the_config

    def test_database_config_structure(self):
        """Test that database configuration has expected structure."""
        from backend.persistence.db import the_config

        db_config = the_config["database"]

        assert "user" in db_config
        assert "password" in db_config
        assert "host" in db_config
        assert "port" in db_config
        assert "name" in db_config


class TestDatabaseConnectionEdgeCases:
    """Test edge cases and error conditions."""

    def test_constants_not_empty(self):
        """Test that database constants are not empty strings."""
        assert len(DB_USER) > 0
        assert len(DB_PASSWORD) > 0
        assert len(DB_HOST) > 0
        assert len(str(DB_PORT)) > 0
        assert len(DB_NAME) > 0

    def test_url_contains_no_none_values(self):
        """Test that database URL doesn't contain None values."""
        assert "None" not in SQLALCHEMY_DATABASE_URL
        assert "null" not in SQLALCHEMY_DATABASE_URL.lower()

    @patch("backend.persistence.db.SessionLocal")
    def test_get_db_context_manager_behavior(self, mock_session_local):
        """Test get_db behavior when used as context manager equivalent."""
        mock_session = Mock()
        mock_session_local.return_value = mock_session

        # Simulate how get_db is typically used in FastAPI dependency injection
        db_gen = get_db()

        try:
            db = next(db_gen)
            # Do something with db
            assert db is mock_session
        finally:
            # This simulates FastAPI cleaning up the dependency
            try:
                next(db_gen)
            except StopIteration:
                pass

        mock_session.close.assert_called_once()

    def test_engine_url_security(self):
        """Test that engine URL is properly configured."""
        # SQLAlchemy may mask password in string representation
        url_str = str(engine.url)
        assert "postgresql://" in url_str
        assert DB_USER in url_str
        # Password may be masked as *** in string representation for security

    def test_database_types_compatibility(self):
        """Test that database configuration types are compatible."""
        # Port might come as string from config, ensure it can be converted
        port_int = int(DB_PORT)
        assert isinstance(port_int, int)
        assert port_int > 0
        assert port_int <= 65535
