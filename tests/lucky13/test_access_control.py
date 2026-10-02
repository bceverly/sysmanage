# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Lucky 13 #7 direct request (CWE-425) and #8 authenticated=1 (CWE-472).

The paper's examples: ``http://example/admin/script.cgi`` answering anyone
who asks, and an application that believes a cookie or form field saying
``authenticated=1``.  Here: every route either requires a login or is on the
reviewed public list, and no forged cookie, header or field opens a protected
route.
"""

import re

from tests.lucky13.conftest import app_routes, dependency_names
from tests.lucky13.public_routes import AUTH_DEPENDENCIES, PUBLIC_ROUTES

# What a forger would try, in every place the paper names.
FORGED_COOKIES = {"authenticated": "1", "admin": "true", "is_admin": "1",
                  "role": "admin", "user": "admin", "logged_in": "yes"}  # fmt: skip
FORGED_HEADERS = {"X-Authenticated": "1", "X-User": "admin", "X-Remote-User": "admin",
                  "X-Forwarded-User": "admin", "X-Admin": "true",
                  "Authorization": "Bearer authenticated=1"}  # fmt: skip
FORGED_QUERY = "authenticated=1&admin=true&is_admin=1"


def _sample_path(path: str) -> str:
    """Fill path parameters with harmless values."""
    return re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-000000000001", path)


def test_the_route_walk_is_not_blind():
    """Guard for the guards: if FastAPI changes shape again, every sweep in
    this package would silently check nothing and pass."""
    paths = {path for _method, path, _route in app_routes()}
    assert (
        len(paths) > 300
    ), f"only {len(paths)} routes found -- the route walk is blind"
    assert "/api/v1/login" in paths and "/api/agent/connect" in paths


def test_7_every_route_requires_login_or_is_reviewed_public():
    unreviewed = sorted(
        f"{method} {path}"
        for method, path, route in app_routes()
        if not dependency_names(route.dependant) & AUTH_DEPENDENCIES
        and (method, path) not in PUBLIC_ROUTES
    )
    assert not unreviewed, (
        "Routes reachable without a login and not on the reviewed list "
        "(tests/lucky13/public_routes.py) -- add authentication, or add them "
        "there with the reason they are safe:\n  " + "\n  ".join(unreviewed)
    )


def test_7_the_public_list_has_no_stale_entries():
    live = {(method, path) for method, path, _route in app_routes()}
    stale = sorted(f"{m} {p}" for m, p in PUBLIC_ROUTES if (m, p) not in live)
    assert (
        not stale
    ), "public_routes.py lists routes that no longer exist: " + ", ".join(stale)


def test_7_8_protected_routes_refuse_anonymous_and_forged_callers(anon_client):
    """Called with no login -- and with every forged "I am authenticated"
    marker -- no protected route may succeed or crash."""
    for name, value in FORGED_COOKIES.items():
        anon_client.cookies.set(name, value)
    failures = []
    for method, path, _route in app_routes():
        if method in ("WS", "HEAD", "OPTIONS") or (method, path) in PUBLIC_ROUTES:
            continue
        url = f"{_sample_path(path)}?{FORGED_QUERY}"
        kwargs = {"headers": FORGED_HEADERS}
        if method in ("POST", "PUT", "PATCH"):
            kwargs["data"] = {"authenticated": "1", "admin": "true"}
        status = anon_client.request(method, url, **kwargs).status_code
        if status < 400 or status >= 500:
            failures.append(f"{method} {path} -> {status}")
    assert not failures, (
        "Protected routes answered an unauthenticated, forged request:\n  "
        + "\n  ".join(failures)
    )
