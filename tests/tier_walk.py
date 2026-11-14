# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Support for the edition route walk (tests/test_tier_gates_walk.py).

Builds the app the way production assembles it -- every OSS router, then
``mount_proplus_routes``, which mounts each engine's router or, with the engine
absent, its stubs -- and calls every route as a user holding every role, with
path, query and body values made up from the route's own OpenAPI schema, so a
gate that sits behind body validation is reached instead of hidden by a 422.

Not a conftest: pytest does not collect tests from conftest files, and the
walk itself lives in a test module (see tests/lucky13/conftest.py).
"""

import os
import re
import socket
import subprocess  # nosec B404  # only patched out here, never run
from contextlib import ExitStack, asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from tests.lucky13.conftest import _flatten

SAMPLE_ID = "00000000-0000-0000-0000-000000000001"

# Routes the walk never calls, each with the reason.  Calling them would act
# on the machine running the tests, not on the test database.
SKIP = {
    ("POST", "/api/v1/openbao/start"): "starts the developer's OpenBAO",
    ("POST", "/api/v1/openbao/stop"): "stops the developer's OpenBAO",
    ("POST", "/api/v1/openbao/seal"): "seals the developer's OpenBAO",
    ("POST", "/api/v1/openbao/unseal"): "unseals the developer's OpenBAO",
}

# Answers that are about the license, whatever their status code.
LICENSE_ERRORS = {"pro_plus_required", "module_not_available"}


def build_app():
    """The app as production assembles it, with NO engine loaded."""
    # pylint: disable=import-outside-toplevel
    from backend.api.proplus_routes import mount_proplus_routes
    from backend.startup.exception_handlers import register_exception_handlers
    from backend.startup.route_registration import (
        register_app_routes,
        register_routes,
    )

    app = FastAPI()
    register_exception_handlers(app, [])
    register_routes(app)
    register_app_routes(app)
    with patch(
        "backend.licensing.module_loader.module_loader.get_module", return_value=None
    ):
        mount_proplus_routes(app)
    return app


def tier_license(tier):
    """A cached license for ``tier`` carrying exactly that tier's features and
    modules, or None for Community."""
    # pylint: disable=import-outside-toplevel
    from backend.licensing.features import TIER_FEATURES, TIER_MODULES, LicenseTier
    from backend.licensing.validator import LicensePayload

    if tier == LicenseTier.COMMUNITY:
        return None
    now = datetime.now(timezone.utc)
    return LicensePayload(
        license_id="tier-walk",
        tier=tier,
        features=sorted(f.value for f in TIER_FEATURES[tier]),
        modules=sorted(m.value for m in TIER_MODULES[tier]),
        expires_at=now + timedelta(days=30),
        issued_at=now,
        offline_days=30,
    )


def _refuse(*_args, **_kwargs):
    raise OSError("the tier walk never starts a process or opens a connection")


def _every_role_cache(_db, user_id):
    # pylint: disable=import-outside-toplevel
    from backend.security.roles import SecurityRoles, UserRoleCache

    return UserRoleCache(user_id, {role.value for role in SecurityRoles})


def no_side_effects(stack: ExitStack):
    """Engines absent, every role granted, no process ever started."""
    stack.enter_context(
        patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=None,
        )
    )
    stack.enter_context(
        patch(
            "backend.licensing.module_loader.module_loader.is_module_loaded",
            return_value=False,
        )
    )
    stack.enter_context(
        patch("backend.security.roles.load_user_roles", _every_role_cache)
    )
    for name in ("run", "Popen", "check_output", "check_call", "call"):
        stack.enter_context(patch.object(subprocess, name, _refuse))
    stack.enter_context(patch.object(os, "kill", _refuse))
    stack.enter_context(patch.object(os, "system", _refuse))
    # No network either: the TestClient needs none (ASGI in process), and a
    # route that reached the developer's OpenBAO, SMTP or a monitoring
    # server would act on it.
    stack.enter_context(patch.object(socket.socket, "connect", _refuse))
    stack.enter_context(patch.object(socket.socket, "connect_ex", _refuse))
    stack.enter_context(patch.object(socket, "create_connection", _refuse))
    _keep_process_state(stack)


def _keep_process_state(stack: ExitStack):
    """Put back what the walk's calls change in this process: the login
    limiter (the walk's failed logins would 429 a later test's login) and
    the in-memory configuration (settings routes write to it)."""
    # pylint: disable=import-outside-toplevel
    import copy
    from collections import defaultdict

    from backend.config import config as config_module
    from backend.security.login_security import login_security

    for name, empty in (
        ("failed_attempts", defaultdict(list)),
        ("successful_logins", defaultdict(list)),
        ("blocked_ips", {}),
    ):
        stack.enter_context(patch.object(login_security, name, empty))
    saved = copy.deepcopy(config_module.config)

    def restore():
        config_module.config.clear()
        config_module.config.update(saved)

    stack.callback(restore)


@asynccontextmanager
async def _no_lifespan(_app):
    yield


def walk_client(app, overrides):
    """A TestClient that reports server errors as responses, not raises."""
    app.dependency_overrides.update(overrides)
    app.router.lifespan_context = _no_lifespan
    return TestClient(app, raise_server_exceptions=False)


# --- values made up from the OpenAPI schema ---------------------------------


def _resolve(schema, components):
    while isinstance(schema, dict) and "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        schema = components.get(name, {})
    return schema if isinstance(schema, dict) else {}


def _first_choice(schema, components):
    for key in ("anyOf", "oneOf"):
        options = [_resolve(option, components) for option in schema.get(key) or []]
        options = [o for o in options if o.get("type") != "null"]
        if options:
            return options[0]
    if schema.get("allOf"):
        merged = {}
        for part in schema["allOf"]:
            merged.update(_resolve(part, components))
        return merged
    return None


_STRING_FORMATS = {
    "uuid": SAMPLE_ID,
    "date-time": "2026-01-01T00:00:00Z",
    "date": "2026-01-01",
    "email": "walk@example.com",
    "uri": "https://example.com/",
    "ipv4": "192.0.2.1",
}


def _sample_string(schema):
    if schema.get("format") in _STRING_FORMATS:
        return _STRING_FORMATS[schema["format"]]
    length = max(int(schema.get("minLength") or 1), 1)
    if schema.get("maxLength") is not None:
        length = min(length, int(schema["maxLength"]))
    return ("walk" * length)[: max(length, 4)][: schema.get("maxLength") or 64]


def _sample_number(schema):
    low = schema.get("minimum", schema.get("exclusiveMinimum", 0))
    value = max(1, int(low) + (1 if "exclusiveMinimum" in schema else 0))
    high = schema.get("maximum")
    return min(value, int(high)) if high is not None else value


def _names_an_id(name, schema):
    kind = schema.get("type")
    if kind == "array":
        kind = _resolve(schema.get("items", {}), {}).get("type")
    return (name == "id" or name.endswith(("_id", "_ids"))) and kind == "string"


def _sample_object(schema, components, depth):
    """Required properties only; anything named like an id gets the seeded
    one, so a body names the host, target or policy the walk created."""
    out = {}
    properties = schema.get("properties") or {}
    for name in schema.get("required") or []:
        prop = _resolve(properties.get(name, {}), components)
        if _names_an_id(name, prop):
            out[name] = [SAMPLE_ID] if prop.get("type") == "array" else SAMPLE_ID
        else:
            out[name] = sample(prop, components, depth + 1)
    return out


def sample(schema, components, depth=0):
    """A value that satisfies ``schema`` well enough to pass validation."""
    schema = _resolve(schema, components)
    if depth > 8:
        return None
    for key in ("default", "const"):
        if key in schema:
            return schema[key]
    if schema.get("enum"):
        return schema["enum"][0]
    choice = _first_choice(schema, components)
    if choice is not None:
        return sample(choice, components, depth + 1)
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        return _sample_object(schema, components, depth)
    if kind == "array":
        count = int(schema.get("minItems") or 0)
        return [sample(schema.get("items", {}), components, depth + 1)] * count
    if kind in ("integer", "number"):
        return _sample_number(schema)
    if kind == "boolean":
        return False
    if kind == "string":
        return _sample_string(schema)
    return None


def build_request(method, path, spec):
    """``(url, kwargs)`` for one route, values made up from its schema."""
    components = spec.get("components", {}).get("schemas", {})
    operation = spec.get("paths", {}).get(path, {}).get(method.lower(), {})
    query = {}
    url = path
    for param in operation.get("parameters", []):
        schema = _resolve(param.get("schema", {}), components)
        value = sample(schema, components)
        if param.get("in") == "path":
            if not isinstance(value, (int, float)) and not schema.get("enum"):
                value = SAMPLE_ID
            url = url.replace("{" + param["name"] + "}", str(value))
        elif param.get("in") == "query" and param.get("required"):
            query[param["name"]] = value
    url = re.sub(r"\{[^}]+\}", SAMPLE_ID, url)  # anything the spec missed
    kwargs = {"params": query}
    body = operation.get("requestBody", {}).get("content", {})
    if "application/json" in body:
        kwargs["json"] = sample(body["application/json"].get("schema", {}), components)
    elif body:
        kwargs["data"] = {}
    elif method in ("POST", "PUT", "PATCH"):
        kwargs["json"] = {}
    return url, kwargs


_ORDER = {"GET": 0, "POST": 1, "PUT": 1, "PATCH": 1, "DELETE": 2}


def http_routes(app):
    """``(method, path)`` for every HTTP route the walk calls: reads first,
    deletes last, so a DELETE of the seeded host cannot blind what follows."""
    found = []
    for route in _flatten(app.routes):
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            if (method, route.path) not in SKIP:
                found.append((method, route.path))
    return sorted(found, key=lambda pair: _ORDER.get(pair[0], 1))


def seed(session):
    """A host, its storage host, a backup target and a policy, all named by
    ``SAMPLE_ID`` where a route takes one, so routes reach past "not found"
    to their license gate."""
    # pylint: disable=import-outside-toplevel
    import json
    import uuid

    from backend.persistence import models

    stamp = datetime(2026, 10, 1)
    caps = json.dumps({"capabilities": ["backup"], "commands": []})
    host = models.Host(
        id=uuid.UUID(SAMPLE_ID), fqdn="walk.example", active=True,
        approval_status="approved", agent_capabilities=caps, platform="Linux",
    )  # fmt: skip
    nas = models.Host(
        id=uuid.uuid4(), fqdn="nas.walk.example", active=True,
        approval_status="approved", agent_capabilities=caps, platform="Linux",
    )  # fmt: skip
    session.add_all([host, nas])
    session.flush()
    target = models.BackupTarget(
        id=uuid.UUID(SAMPLE_ID), name="walk", host_mount_point="/mnt/backups",
        storage_host_id=nas.id, storage_path="/srv/backups/restate",
        max_concurrent=2, seal_mode="none", created_at=stamp, updated_at=stamp,
    )  # fmt: skip
    session.add(target)
    session.flush()
    session.add(
        models.BackupPolicy(
            id=uuid.UUID(SAMPLE_ID), host_id=host.id, target_id=target.id,
            enabled=True, interval_hours=24, keep_last=14,
            check_interval_days=7, quiesce=False, config_version=1,
            host_acked_version=1, storage_acked_version=1,
            created_at=stamp, updated_at=stamp,
        )
    )  # fmt: skip
    session.commit()


def license_error(response):
    """The ``detail`` of a license answer (a dict naming the module or
    feature), or None."""
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        return None
    if isinstance(detail, dict) and detail.get("error") in LICENSE_ERRORS:
        return detail
    return None


def walk(client, app):
    """Call every route once.  Returns ``[(method, path, response)]``."""
    spec = app.openapi()
    answers = []
    for method, path in http_routes(app):
        url, kwargs = build_request(method, path, spec)
        answers.append((method, path, client.request(method, url, **kwargs)))
    return answers
