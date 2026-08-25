# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Creating and deleting user accounts and groups on managed hosts.

All four routes queue a command that runs as root on someone else's machine,
so the guard ladder -- role, host exists, host active, agent privileged -- has
to complete before anything reaches the queue.  A guard that moved after the
enqueue would not fail loudly; the command would simply run, and the only
record would be the account that appeared.

The parameter assembly is the other half.  These dicts become the agent's
``useradd`` / ``net user`` arguments, and the optional fields are filtered by
two DIFFERENT rules: booleans and ints go through ``is not None`` (so
``False`` and ``0`` survive), strings go through plain truthiness.  Mixing
those up silently drops ``account_disabled=False`` or ``uid=0`` -- the second
being the root uid, which is exactly the value you least want reinterpreted
as "unset".
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.api import host_account_management as ham
from backend.security.roles import SecurityRoles

MOD = "backend.api.host_account_management"
HOST_ID = "host-1"


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, **by_model):
        self._by_model = {k: list(v) for k, v in by_model.items()}
        self.commits = 0

    def query(self, model):
        return _FakeQuery(self._by_model.get(model.__name__, []))

    def commit(self):
        self.commits += 1

    def __call__(self, *_a, **_k):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _host(**overrides):
    host = SimpleNamespace(
        id=HOST_ID, fqdn="host.invalid", active=True, is_agent_privileged=True
    )
    for key, value in overrides.items():
        setattr(host, key, value)
    return host


def _user(*roles):
    granted = set(roles)
    return SimpleNamespace(
        id="u1", userid="admin@invalid", has_role=lambda role: role in granted
    )


class _Env:
    def __init__(self):
        self.queued = []
        self.audits = []

    def __enter__(self):
        self._patches = [
            patch(
                f"{MOD}.queue_ops.enqueue_message",
                side_effect=lambda **kw: self.queued.append(kw) or "msg-1",
            ),
            patch(f"{MOD}.db_module.get_engine"),
            patch(f"{MOD}.sessionmaker", return_value=_FakeSession()),
            patch(
                "backend.services.audit_service.AuditService.log",
                side_effect=lambda **kw: self.audits.append(kw),
            ),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *_exc):
        for p in self._patches:
            p.stop()
        return False

    @property
    def params(self):
        return self.queued[0]["message_data"]["data"]["parameters"]

    @property
    def command(self):
        return self.queued[0]["message_data"]["data"]["command_type"]


# (route, role, callable building (args, kwargs) for a valid call)
ROUTES = [
    (
        "create_host_user",
        SecurityRoles.ADD_HOST_ACCOUNT,
        "create_host_user",
        lambda: ([HOST_ID, ham.CreateHostUserRequest(username="alice")], {}),
    ),
    (
        "create_host_group",
        SecurityRoles.ADD_HOST_GROUP,
        "create_host_group",
        lambda: ([HOST_ID, ham.CreateHostGroupRequest(group_name="devs")], {}),
    ),
    (
        "delete_host_user",
        SecurityRoles.DELETE_HOST_ACCOUNT,
        "delete_host_user",
        lambda: ([HOST_ID, "alice"], {}),
    ),
    (
        "delete_host_group",
        SecurityRoles.DELETE_HOST_GROUP,
        "delete_host_group",
        lambda: ([HOST_ID, "devs"], {}),
    ),
]


async def _call(route, db, user, args=None, kwargs=None):
    env = _Env()
    with env:
        out = await getattr(ham, route)(
            *(args or []), db=db, current_user=user, **(kwargs or {})
        )
    return out, env


class TestGuardLadder:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("route,role,command,build", ROUTES)
    async def test_a_valid_call_queues_its_own_command(
        self, route, role, command, build
    ):
        args, kwargs = build()
        db = _FakeSession(Host=[_host()])
        out, env = await _call(route, db, _user(role), args, kwargs)
        assert out["result"] is True
        assert env.command == command
        assert env.queued[0]["host_id"] == HOST_ID
        assert db.commits == 1
        assert env.audits

    @pytest.mark.asyncio
    @pytest.mark.parametrize("route,role,_c,build", ROUTES)
    async def test_each_route_requires_its_own_role(self, route, role, _c, build):
        # Distinct roles per verb: being allowed to CREATE an account must not
        # imply being allowed to delete one.
        other = next(r for _, r, _, _ in ROUTES if r != role)
        args, kwargs = build()
        env = _Env()
        with env:
            with pytest.raises(HTTPException) as exc:
                await getattr(ham, route)(
                    *args, db=_FakeSession(), current_user=_user(other), **kwargs
                )
        assert exc.value.status_code == 403
        assert env.queued == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("route,role,_c,build", ROUTES)
    async def test_an_unknown_host_is_a_404(self, route, role, _c, build):
        args, kwargs = build()
        env = _Env()
        with env:
            with pytest.raises(HTTPException) as exc:
                await getattr(ham, route)(
                    *args, db=_FakeSession(), current_user=_user(role), **kwargs
                )
        assert exc.value.status_code == 404
        assert env.queued == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("route,role,_c,build", ROUTES)
    async def test_an_inactive_host_is_a_400(self, route, role, _c, build):
        args, kwargs = build()
        db = _FakeSession(Host=[_host(active=False)])
        env = _Env()
        with env:
            with pytest.raises(HTTPException) as exc:
                await getattr(ham, route)(
                    *args, db=db, current_user=_user(role), **kwargs
                )
        assert exc.value.status_code == 400
        # Queuing for a decommissioned host leaves a command that fires if the
        # host is ever reactivated.
        assert env.queued == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("route,role,_c,build", ROUTES)
    async def test_an_unprivileged_agent_is_a_400(self, route, role, _c, build):
        args, kwargs = build()
        db = _FakeSession(Host=[_host(is_agent_privileged=False)])
        env = _Env()
        with env:
            with pytest.raises(HTTPException) as exc:
                await getattr(ham, route)(
                    *args, db=db, current_user=_user(role), **kwargs
                )
        assert exc.value.status_code == 400
        assert env.queued == []
        assert db.commits == 0


class TestCreateUserParameters:
    async def _params(self, **fields):
        db = _FakeSession(Host=[_host()])
        request = ham.CreateHostUserRequest(username="alice", **fields)
        _, env = await _call(
            "create_host_user",
            db,
            _user(SecurityRoles.ADD_HOST_ACCOUNT),
            [HOST_ID, request],
        )
        return env.params

    @pytest.mark.asyncio
    async def test_a_bare_request_sends_the_username_and_the_boolean_defaults(self):
        params = await self._params()
        assert params["username"] == "alice"
        # The three tri-state booleans always travel, because their defaults
        # are meaningful policy, not "unset".
        assert params["create_home_dir"] is True
        assert params["user_must_change_password"] is True
        assert params["account_disabled"] is False
        assert params["password_never_expires"] is False

    @pytest.mark.asyncio
    async def test_unset_string_fields_are_omitted(self):
        params = await self._params()
        for field in (
            "full_name",
            "home_directory",
            "shell",
            "primary_group",
            "password",
        ):
            assert field not in params

    @pytest.mark.asyncio
    async def test_the_unix_fields_are_forwarded(self):
        params = await self._params(
            full_name="Alice A",
            home_directory="/home/alice",
            shell="/bin/zsh",
            primary_group="staff",
        )
        assert params["full_name"] == "Alice A"
        assert params["home_directory"] == "/home/alice"
        assert params["shell"] == "/bin/zsh"
        assert params["primary_group"] == "staff"

    @pytest.mark.asyncio
    async def test_a_zero_uid_survives_the_optional_filter(self):
        # uid uses ``is not None`` rather than truthiness precisely so uid 0
        # is not silently dropped and the account created with a random uid.
        params = await self._params(uid=0)
        assert params["uid"] == 0

    @pytest.mark.asyncio
    async def test_an_explicit_uid_is_forwarded(self):
        assert (await self._params(uid=1500))["uid"] == 1500

    @pytest.mark.asyncio
    async def test_no_uid_means_the_host_picks_one(self):
        assert "uid" not in await self._params()

    @pytest.mark.asyncio
    async def test_explicit_false_booleans_are_not_dropped(self):
        # ``create_home_dir=False`` under a truthiness filter would vanish and
        # the agent would fall back to its default of creating one.
        params = await self._params(
            create_home_dir=False, user_must_change_password=False
        )
        assert params["create_home_dir"] is False
        assert params["user_must_change_password"] is False

    @pytest.mark.asyncio
    async def test_a_windows_password_is_forwarded(self):
        params = await self._params(password="P@ssw0rd", account_disabled=True)
        assert params["password"] == "P@ssw0rd"
        assert params["account_disabled"] is True

    @pytest.mark.asyncio
    async def test_the_audit_entry_names_the_account_and_the_host(self):
        db = _FakeSession(Host=[_host()])
        _, env = await _call(
            "create_host_user",
            db,
            _user(SecurityRoles.ADD_HOST_ACCOUNT),
            [HOST_ID, ham.CreateHostUserRequest(username="alice")],
        )
        description = env.audits[0]["description"]
        assert "alice" in description
        assert "host.invalid" in description


class TestCreateGroupParameters:
    async def _params(self, **fields):
        db = _FakeSession(Host=[_host()])
        request = ham.CreateHostGroupRequest(group_name="devs", **fields)
        _, env = await _call(
            "create_host_group",
            db,
            _user(SecurityRoles.ADD_HOST_GROUP),
            [HOST_ID, request],
        )
        return env.params

    @pytest.mark.asyncio
    async def test_a_bare_request_sends_only_the_group_name(self):
        assert await self._params() == {"group_name": "devs"}

    @pytest.mark.asyncio
    async def test_a_zero_gid_survives_the_optional_filter(self):
        assert (await self._params(gid=0))["gid"] == 0

    @pytest.mark.asyncio
    async def test_the_gid_and_description_are_forwarded(self):
        params = await self._params(gid=3000, description="Developers")
        assert params["gid"] == 3000
        assert params["description"] == "Developers"

    @pytest.mark.asyncio
    async def test_an_empty_description_is_omitted(self):
        assert "description" not in await self._params(description="")


class TestDeleteParameters:
    @pytest.mark.asyncio
    async def test_deleting_a_user_defaults_to_removing_the_default_group(self):
        db = _FakeSession(Host=[_host()])
        _, env = await _call(
            "delete_host_user",
            db,
            _user(SecurityRoles.DELETE_HOST_ACCOUNT),
            [HOST_ID, "alice"],
        )
        assert env.params == {"username": "alice", "delete_default_group": True}

    @pytest.mark.asyncio
    async def test_the_default_group_removal_can_be_declined(self):
        # Shared-group setups reuse a per-user group across accounts; removing
        # it with the user would strip access from everyone else on it.
        db = _FakeSession(Host=[_host()])
        _, env = await _call(
            "delete_host_user",
            db,
            _user(SecurityRoles.DELETE_HOST_ACCOUNT),
            [HOST_ID, "alice"],
            {"delete_default_group": False},
        )
        assert env.params["delete_default_group"] is False

    @pytest.mark.asyncio
    async def test_deleting_a_group_sends_only_its_name(self):
        db = _FakeSession(Host=[_host()])
        _, env = await _call(
            "delete_host_group",
            db,
            _user(SecurityRoles.DELETE_HOST_GROUP),
            [HOST_ID, "devs"],
        )
        assert env.params == {"group_name": "devs"}

    @pytest.mark.asyncio
    async def test_the_delete_audit_names_the_target(self):
        db = _FakeSession(Host=[_host()])
        _, env = await _call(
            "delete_host_user",
            db,
            _user(SecurityRoles.DELETE_HOST_ACCOUNT),
            [HOST_ID, "alice"],
        )
        assert "alice" in env.audits[0]["description"]
