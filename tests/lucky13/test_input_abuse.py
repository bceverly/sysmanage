# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Lucky 13 #1 buffer overflow (CWE-120), #3 directory traversal (CWE-23),
#5 SQL injection (CWE-89) and #13 integer overflow (CWE-190).

The paper's attacks, verbatim: ``AAA...AAA`` in the username and password,
``../..`` or ``/full/path`` in a file parameter, ``' OR 1=1`` in the login
and in a numeric id, and ``0xffffffff`` as a length.  Python does not overrun
buffers, but the same inputs crash parsers, overflow 32-bit database columns
and reach the SQL layer -- so every one must be refused cleanly (4xx), never
crash the server (5xx) and never let anyone in.
"""

import re
from typing import Optional

from tests.lucky13.conftest import app_routes
from tests.lucky13.public_routes import PUBLIC_ROUTES

LONG = "A" * 100_000
PATH_PAYLOADS = {
    "#1 long string": "A" * 8_000,
    "#3 traversal": "..%2F..%2F..%2F..%2Fetc%2Fpasswd",
    "#3 full path": "%2Fetc%2Fpasswd",
    "#5 SQL injection": "1' OR '1'='1",
    "#13 0xffffffff": "4294967295",
    "#13 past int64": "9223372036854775808",
    "#13 negative": "-2147483649",
}
SQLI_PASSWORDS = ("' OR '1'='1", "' OR 1=1 --", "admin'--", '" OR ""="')


def _fill(path: str, value: str) -> str:
    return re.sub(r"\{[^}]+\}", value, path)


def test_1_3_5_13_every_path_parameter_refuses_hostile_values(client):
    """Every GET route with a path parameter, logged in, fed each payload."""
    crashes = []
    for method, path, _route in app_routes():
        if method != "GET" or "{" not in path or (method, path) in PUBLIC_ROUTES:
            continue
        for label, payload in PATH_PAYLOADS.items():
            status = client.get(_fill(path, payload)).status_code
            if status >= 500:
                crashes.append(f"{label}: GET {path} -> {status}")
    assert not crashes, "Hostile path values crashed the server:\n  " + "\n  ".join(
        crashes
    )


def test_1_3_5_13_public_path_parameters_refuse_hostile_values(anon_client):
    """The same payloads on the routes an attacker reaches without a login."""
    crashes = []
    for method, path in PUBLIC_ROUTES:
        if method != "GET" or "{" not in path:
            continue
        for label, payload in PATH_PAYLOADS.items():
            response = anon_client.get(_fill(path, payload))
            if response.status_code >= 500:
                crashes.append(f"{label}: GET {path} -> {response.status_code}")
    assert not crashes, "\n".join(crashes)


def test_1_long_credentials_are_refused(anon_client):
    for userid, password in (
        (f"{LONG}@example.com", "x"),
        ("someone@example.com", LONG),
        (LONG, LONG),
    ):
        status = anon_client.post(
            "/api/v1/login", json={"userid": userid, "password": password}
        ).status_code
        assert 400 <= status < 500, f"login with a 100 KB field -> {status}"


def test_1_long_fields_on_the_public_forms_are_refused(anon_client):
    probes = [
        ("/api/v1/forgot-password", {"email": f"{LONG}@example.com"}),
        ("/api/v1/reset-password", {"token": LONG, "password": LONG,
                                    "confirm_password": LONG}),  # fmt: skip
        ("/api/v1/invitations/accept", {"token": LONG, "password": LONG}),
        ("/api/auth/mfa/verify", {"challenge": LONG, "code": LONG}),
        ("/api/auth/sso/session", {}),
        ("/api/host/register", {"hostname": LONG, "fqdn": LONG, "ipv4": LONG,
                                "platform": LONG}),  # fmt: skip
    ]
    crashes = []
    for url, body in probes:
        status = anon_client.post(url, json=body).status_code
        if status >= 500:
            crashes.append(f"POST {url} -> {status}")
    assert not crashes, "\n".join(crashes)


def test_5_sql_injection_does_not_log_anyone_in(anon_client):
    for password in SQLI_PASSWORDS:
        response = anon_client.post(
            "/api/v1/login",
            json={"userid": "test_user@example.com", "password": password},
        )
        assert response.status_code in (401, 403, 422), (password, response.status_code)
        assert "access_token" not in response.text


def test_13_huge_numbers_in_query_parameters_are_refused(client):
    """Pagination and size knobs are where 0xffffffff goes."""
    crashes = []
    for method, path, route in app_routes():
        if method != "GET" or (method, path) in PUBLIC_ROUTES:
            continue
        numeric = [
            param.name
            for param in route.dependant.query_params
            if param.field_info.annotation in (int, Optional[int])
        ]
        if not numeric:
            continue
        for value in ("4294967295", "9223372036854775808", "-1"):
            query = "&".join(f"{name}={value}" for name in numeric)
            url = _fill(path, "00000000-0000-0000-0000-000000000001")
            status = client.get(f"{url}?{query}").status_code
            if status >= 500:
                crashes.append(f"GET {path}?{query} -> {status}")
    assert not crashes, "Huge integers crashed the server:\n  " + "\n  ".join(crashes)
