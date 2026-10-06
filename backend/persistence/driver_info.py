# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Which PostgreSQL driver implementation this server runs (Phase 22).

psycopg has three implementations: ``c`` (psycopg-c, built for the machine),
``binary`` (the psycopg[binary] wheel -- Linux, macOS, Windows x64) and
``python`` (pure Python, calling libpq through ctypes).  The last is the
fallback wherever neither of the others exists -- the BSDs, Windows ARM64 --
and it is several times slower under load: on OpenBSD (t480) a 5,000-agent
storm drained ~1,900 messages in 20 minutes with it and ~11,000 with
psycopg-c.  It used to be chosen silently; the startup log now says which.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def psycopg_implementation() -> Optional[str]:
    """``"c"``, ``"binary"``, ``"python"``, or None when psycopg is absent."""
    try:
        import psycopg  # pylint: disable=import-outside-toplevel
    except ImportError:
        return None
    return getattr(psycopg.pq, "__impl__", None)


def log_postgres_driver(engine) -> Optional[str]:
    """Log the driver behind ``engine``; a warning for the slow one.  Returns
    the implementation (None for a database that is not PostgreSQL)."""
    if getattr(getattr(engine, "dialect", None), "name", None) != "postgresql":
        return None
    impl = psycopg_implementation()
    if impl == "python":
        logger.warning(
            "PostgreSQL driver: pure-Python psycopg (libpq through ctypes), "
            "several times slower under load. Install the compiled driver: "
            "psycopg-c (the platform's package, or `make install-psycopg-c`)."
        )
    else:
        logger.info("PostgreSQL driver: psycopg, %s implementation", impl)
    return impl
