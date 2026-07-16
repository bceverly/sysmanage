# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
This module manages the "db" object which is the gateway into the SQLAlchemy
ORM used by SysManage.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.config import config


def _psycopg_url(url: str) -> str:
    """Route a PostgreSQL SQLAlchemy URL through psycopg (psycopg3).

    Converts ``postgresql://`` to ``postgresql+psycopg://`` so SQLAlchemy uses
    the psycopg3 driver, and forces ``client_encoding=utf8`` on the connection.
    Leaves SQLite / other schemes untouched. Apply ONLY to URLs handed to
    SQLAlchemy's create_engine/engine_from_config — never to a raw libpq /
    psycopg.connect() conninfo (libpq does not understand the ``+psycopg`` tag).

    The UTF-8 client encoding matters on clusters initialised with SQL_ASCII
    encoding — the ``initdb`` default under a C/POSIX locale, as on NetBSD.
    Against a SQL_ASCII connection, psycopg3 hands back text query results as
    ``bytes`` rather than ``str``, which breaks SQLAlchemy's PostgreSQL dialect
    start-up (it runs ``re.match`` on the server-version string) and any code
    expecting ``str``. Requesting UTF-8 makes psycopg decode text to ``str``
    everywhere; it is a no-op on the UTF-8 clusters Linux/macOS build by default.
    """
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgresql+psycopg://") and "client_encoding=" not in url:
        url += ("&" if "?" in url else "?") + "client_encoding=utf8"
    return url


def _apply_db_options(url: str, options) -> str:
    """Append optional libpq connection parameters to a PostgreSQL URL.

    ``options`` is a raw query-parameter fragment from ``database.options`` in
    sysmanage.yaml (e.g. ``target_session_attrs=read-write``).  Returns ``url``
    unchanged when empty.  Uses ``?`` or ``&`` depending on whether the URL
    already carries a query string.
    """
    if not options:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{options}"


# PostgreSQL High-Availability (Phase 15.1).  After a primary failover the
# pooled connections are dead sockets; ``pool_pre_ping`` issues a cheap liveness
# check on checkout and transparently discards+reconnects (to the new primary
# via the proxy/VIP or libpq multi-host DSN) instead of handing a stale socket
# to the next request.  ``pool_recycle`` caps connection age below typical
# proxy/server idle timeouts so long-lived connections don't accumulate.  These
# are the single most important HA change and MUST be applied uniformly to every
# engine: this module's bootstrap engine (which also backs the registry/shared
# partitions in collapsed mode — see backend.persistence.partitions), and the
# per-tenant engines built in the licensed multitenancy engine (which already
# sets the same, keyed to its OpenBAO lease duration).  Harmless on SQLite.
HA_ENGINE_KWARGS = {"pool_pre_ping": True, "pool_recycle": 1800}


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
    db_options = the_config["database"].get("options")

    # Build the connection string based on database type
    if db_user == "sqlite" or not db_host:
        # SQLite configuration
        PROD_DATABASE_URL = f"sqlite:///{db_name}"
    else:
        # PostgreSQL configuration
        PROD_DATABASE_URL = (
            f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        )
        # Optional extra libpq connection parameters (Phase 15.1 HA).  The
        # canonical case is ``options: "target_session_attrs=read-write"`` so a
        # multi-host ``host`` list (``h1,h2``) connects only to the writable
        # primary and re-resolves it after a failover.  Appended verbatim as URL
        # query parameters (``_psycopg_url`` then adds client_encoding with the
        # right separator).
        PROD_DATABASE_URL = _apply_db_options(PROD_DATABASE_URL, db_options)

    # create the database connection
    PROD_ENGINE = create_engine(
        _psycopg_url(PROD_DATABASE_URL),
        connect_args={},
        echo=False,
        **HA_ENGINE_KWARGS,
    )
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
