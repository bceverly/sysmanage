# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""MITRE's "Lucky 13" unforgivable vulnerabilities, checked on every push.

Steve Christey (MITRE), "Unforgivable Vulnerabilities", Black Hat USA 2007:
thirteen weakness classes so well documented, so obvious and so cheap to find
("found in five minutes") that shipping one is unforgivable.  Each test in
this package names its number and CWE.  CI runs the package as its own step
(``pytest -m lucky13``) so a regression is named, not buried in the suite.

    1 buffer overflow (CWE-120)     8 auth bypass: authenticated=1 (CWE-472)
    2 XSS (CWE-79)                  9 grow-your-own crypto (CWE-327)
    3 directory traversal (CWE-23) 10 privilege escalation via Help (CWE-271)
    4 remote file inclusion (CWE-98) 11 symlink following (CWE-61)
    5 SQL injection (CWE-89)       12 hard-coded / default password (CWE-259)
    6 world-writable files (CWE-276) 13 integer overflow (CWE-190)
    7 direct request (CWE-425)
"""

from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi.routing import APIRoute, APIWebSocketRoute
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]


def pytest_collection_modifyitems(items):
    for item in items:
        if "lucky13" in item.nodeid.split("::")[0]:
            item.add_marker(pytest.mark.lucky13)


def dependency_names(dependant, out=None):
    """Names of every dependency a route resolves, transitively."""
    out = set() if out is None else out
    for sub in dependant.dependencies:
        call = sub.call
        out.add(getattr(call, "__name__", None) or type(call).__name__)
        dependency_names(sub, out)
    return out


def _flatten(routes):
    """Every route, including those inside included routers.  FastAPI 0.139+
    wraps an included router in ``_IncludedRouter``; walking only
    ``app.routes`` for APIRoute would see a handful of routes and pass blind."""
    for route in routes:
        contexts = getattr(route, "effective_route_contexts", None)
        if callable(contexts):
            yield from _flatten(contexts())
        elif isinstance(route, (APIRoute, APIWebSocketRoute)):
            yield route


def app_routes():
    """``(method, path, route)`` for every HTTP and WebSocket route."""
    from backend.main import app  # pylint: disable=import-outside-toplevel

    found = []
    for route in _flatten(app.routes):
        if isinstance(route, APIRoute):
            found.extend(
                (method, route.path, route) for method in sorted(route.methods)
            )
        else:
            found.append(("WS", route.path, route))
    return found


@pytest.fixture
def anon_client(db_session):
    """The real app with NO authentication override: what an attacker gets."""
    from backend.main import app  # pylint: disable=import-outside-toplevel
    from backend.persistence.db import get_db  # pylint: disable=import-outside-toplevel

    @asynccontextmanager
    async def no_lifespan(_app):
        yield

    original = app.router.lifespan_context
    app.router.lifespan_context = no_lifespan
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.router.lifespan_context = original
