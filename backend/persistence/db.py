"""
This module manages the "db" object which is the gateway into the SQLAlchemy
ORM used by SysManage.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.config import config

# Database context - determines whether we're in production or test mode
IS_TEST_MODE = False
TEST_ENGINE = None
TEST_SESSION_LOCAL = None

# Production database components
PROD_ENGINE = None
PROD_SESSION_LOCAL = None
PROD_DATABASE_URL = None


def _init_production_database():
    """Initialize production database connection using configuration."""
    global PROD_ENGINE, PROD_SESSION_LOCAL, PROD_DATABASE_URL  # pylint: disable=global-statement

    if PROD_ENGINE is not None:
        return

    # Get the /etc/sysmanage.yaml configuration
    the_config = config.get_config()

    db_user = the_config["database"]["user"]
    db_password = the_config["database"]["password"]
    db_host = the_config["database"]["host"]
    db_port = the_config["database"]["port"]
    db_name = the_config["database"]["name"]

    # Build the connection string based on database type
    if db_user == "sqlite" or not db_host:
        # SQLite configuration
        PROD_DATABASE_URL = f"sqlite:///{db_name}"
    else:
        # PostgreSQL configuration
        PROD_DATABASE_URL = (
            f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        )

    # create the database connection
    PROD_ENGINE = create_engine(PROD_DATABASE_URL, connect_args={}, echo=False)
    PROD_SESSION_LOCAL = sessionmaker(
        autocommit=False, autoflush=False, bind=PROD_ENGINE
    )


# Get the base model class - we can use this to extend any models
Base = declarative_base()


def enter_test_mode(test_engine):
    """
    Enter test mode with the provided test engine.
    This prevents any production database access during tests.
    """
    global IS_TEST_MODE, TEST_ENGINE, TEST_SESSION_LOCAL  # pylint: disable=global-statement
    IS_TEST_MODE = True
    TEST_ENGINE = test_engine
    TEST_SESSION_LOCAL = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine
    )


def exit_test_mode():
    """Exit test mode and return to production database access."""
    global IS_TEST_MODE, TEST_ENGINE, TEST_SESSION_LOCAL  # pylint: disable=global-statement
    IS_TEST_MODE = False
    TEST_ENGINE = None
    TEST_SESSION_LOCAL = None


def get_engine():
    """
    Provide a mechanism to retrieve the engine from within the rest of the application.
    Returns test engine if in test mode, production engine otherwise.
    """
    if IS_TEST_MODE:
        if TEST_ENGINE is None:
            raise RuntimeError("Test mode is active but no test engine is configured")
        return TEST_ENGINE

    _init_production_database()
    return PROD_ENGINE


def get_db():
    """
    Provide a mechanism to retrieve the database from within the rest of the application.
    Returns test session if in test mode, production session otherwise.
    """
    if IS_TEST_MODE:
        if TEST_SESSION_LOCAL is None:
            raise RuntimeError("Test mode is active but no test session is configured")
        db = TEST_SESSION_LOCAL()
    else:
        _init_production_database()
        db = PROD_SESSION_LOCAL()

    try:
        yield db
    finally:
        db.close()


# Legacy functions for backward compatibility - these will be removed in future versions
def set_test_engine(test_engine):
    """DEPRECATED: Use enter_test_mode() instead."""
    enter_test_mode(test_engine)


def reset_database():
    """DEPRECATED: Use exit_test_mode() instead."""
    exit_test_mode()


# Legacy SessionLocal for backward compatibility with existing tests
def get_session_local():
    """Get the appropriate session local based on current mode."""
    if IS_TEST_MODE:
        return TEST_SESSION_LOCAL
    _init_production_database()
    return PROD_SESSION_LOCAL


# Module-level SessionLocal that dynamically returns the correct session maker
SessionLocal = get_session_local

# Module-level engine accessor for backward compatibility
engine = get_engine


# Expose the database URL for alembic migrations
def get_database_url():
    """Get the current database URL for alembic and other external tools."""
    if IS_TEST_MODE:
        if TEST_ENGINE is None:
            raise RuntimeError("Test mode is active but no test engine is configured")
        return str(TEST_ENGINE.url)

    _init_production_database()
    return PROD_DATABASE_URL


# Export for alembic - avoid import-time config loading by checking environment first
def _get_alembic_database_url():
    """Get database URL for alembic, with fallback to environment variable."""
    import os

    # Check for environment variable first (for CI)
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url

    # Otherwise use the normal config-based URL
    try:
        return get_database_url()
    except Exception:
        # Final fallback for CI environments
        return "postgresql://sysmanage:abc123@localhost:5432/sysmanage"


# For alembic compatibility, try to get URL immediately but with environment priority
try:
    import os

    SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL") or get_database_url()
except Exception:
    # Fallback for CI environments where config file doesn't exist
    SQLALCHEMY_DATABASE_URL = "postgresql://sysmanage:abc123@localhost:5432/sysmanage"
