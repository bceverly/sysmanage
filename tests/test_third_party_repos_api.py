# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Third-party repository routes.

Four of the five routes repeat the same guard ladder -- role, then host
exists-and-approved, then privileged agent, then a non-empty payload -- and
the ORDER is what these tests pin.  Every guard has to fire before anything
is queued or deleted, because the delete route removes the server-side rows
*and* queues the agent command in one commit: a guard that ran after the
delete would drop the rows for a command that never ships, and the UI would
show the repository gone while it is still configured on the host.

The list route additionally hops a thread pool, and the active-tenant
ContextVar does not cross that boundary -- so the tenant has to be captured
in the async caller or the query silently runs against the bootstrap
database and returns another tenant's (empty) repository list.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.api import third_party_repos as tpr
from backend.security.roles import SecurityRoles

MOD = "backend.api.third_party_repos"
HOST_ID = "host-1"


class _FakeQuery:
    def __init__(self, rows, session=None, model=None):
        self._rows = rows
        self._session = session
        self._model = model

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def delete(self, synchronize_session=False):
        if self._session is not None:
            self._session.deletes.append(self._model)
        return len(self._rows)


class _FakeSession:
    def __init__(self, **by_model):
        self._by_model = {k: list(v) for k, v in by_model.items()}
        self.deletes = []
        self.commits = 0

    def query(self, model):
        name = getattr(model, "__name__", "")
        return _FakeQuery(self._by_model.get(name, []), self, name)

    def commit(self):
        self.commits += 1

    def __call__(self, *_a, **_k):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _host(**overrides):
    host = SimpleNamespace(id=HOST_ID, fqdn="host.invalid", is_agent_privileged=True)
    for key, value in overrides.items():
        setattr(host, key, value)
    return host


def _user(*roles):
    granted = set(roles)
    return SimpleNamespace(
        id="u1", userid="admin@invalid", has_role=lambda role: role in granted
    )


def _repo_row(name="docker", file_path="/etc/apt/sources.list.d/docker.list"):
    return SimpleNamespace(
        name=name,
        type="apt",
        url="https://download.docker.invalid",
        enabled=True,
        file_path=file_path,
    )


class _Env:
    """Patches the outbound queue and the main-engine audit trail."""

    def __init__(self):
        self.queued = []
        self.audits = []

    def _enqueue(self, **kwargs):
        self.queued.append(kwargs)
        return "msg-1"

    def _audit(self, **kwargs):
        self.audits.append(kwargs)

    def __enter__(self):
        self._patches = [
            patch(
                f"{MOD}.server_queue_manager.enqueue_message", side_effect=self._enqueue
            ),
            patch(f"{MOD}.db_module.get_engine"),
            patch(f"{MOD}.sessionmaker", return_value=_FakeSession()),
            patch(f"{MOD}.AuditService.log_create", side_effect=self._audit),
            patch(f"{MOD}.AuditService.log_update", side_effect=self._audit),
            patch(f"{MOD}.AuditService.log_delete", side_effect=self._audit),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *_exc):
        for p in self._patches:
            p.stop()
        return False

    @property
    def command(self):
        return self.queued[0]["message_data"]["data"]["parameters"]["command_type"]


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


class TestListSync:
    def _run(self, session, tenant_id=None):
        env = _Env()
        with env:
            with patch(f"{MOD}.sessionmaker", return_value=session):
                with patch(f"{MOD}.get_request_engine") as engine:
                    out = tpr._list_third_party_repositories_sync(HOST_ID, tenant_id)
        return out, env, engine

    def test_the_stored_repositories_are_returned_and_a_refresh_queued(self):
        session = _FakeSession(Host=[_host()], ThirdPartyRepository=[_repo_row()])
        out, env, _ = self._run(session)
        assert out.count == 1
        assert out.repositories[0].name == "docker"
        # The list is a cache; without the refresh command it never updates.
        assert env.command == "list_third_party_repositories"
        assert session.commits == 1

    def test_a_null_url_is_normalised_to_an_empty_string(self):
        # The response model declares url as a required str; a NULL column
        # would fail validation and 500 the whole list.
        session = _FakeSession(Host=[_host()], ThirdPartyRepository=[_repo_row()])
        session._by_model["ThirdPartyRepository"][0].url = None
        out, _, _ = self._run(session)
        assert out.repositories[0].url == ""

    def test_a_tenant_id_routes_to_that_tenants_engine(self):
        session = _FakeSession(Host=[_host()])
        _, _, engine = self._run(session, tenant_id="tenant-9")
        # The ContextVar is invisible in the thread-pool worker, so the id has
        # to arrive as an argument or the query hits the bootstrap DB.
        engine.assert_called_once_with("tenant-9")

    def test_an_unknown_or_unapproved_host_is_a_404(self):
        with pytest.raises(HTTPException) as exc:
            self._run(_FakeSession())
        assert exc.value.status_code == 404

    def test_an_unprivileged_agent_is_a_403(self):
        session = _FakeSession(Host=[_host(is_agent_privileged=False)])
        with pytest.raises(HTTPException) as exc:
            self._run(session)
        assert exc.value.status_code == 403


class TestListRoute:
    @pytest.mark.asyncio
    async def test_the_active_tenant_is_captured_before_the_thread_hop(self):
        with patch(
            "backend.persistence.tenant_context.get_active_tenant",
            return_value="tenant-9",
        ):
            with patch(f"{MOD}._list_third_party_repositories_sync") as sync:
                sync.return_value = tpr.RepositoryListResponse(
                    success=True, repositories=[], count=0
                )
                await tpr.list_third_party_repositories(HOST_ID, current_user="u")
        assert sync.call_args[0] == (HOST_ID, "tenant-9")

    @pytest.mark.asyncio
    async def test_a_guard_failure_keeps_its_own_status_code(self):
        with patch(
            "backend.persistence.tenant_context.get_active_tenant", return_value=None
        ):
            with patch(
                f"{MOD}._list_third_party_repositories_sync",
                side_effect=HTTPException(status_code=403, detail="nope"),
            ):
                with pytest.raises(HTTPException) as exc:
                    await tpr.list_third_party_repositories(HOST_ID, current_user="u")
        # Wrapping this in a 500 would make a permissions problem look like a
        # server fault.
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_an_unexpected_failure_becomes_a_500(self):
        with patch(
            "backend.persistence.tenant_context.get_active_tenant", return_value=None
        ):
            with patch(
                f"{MOD}._list_third_party_repositories_sync",
                side_effect=RuntimeError("db gone"),
            ):
                with pytest.raises(HTTPException) as exc:
                    await tpr.list_third_party_repositories(HOST_ID, current_user="u")
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# Mutating routes
# ---------------------------------------------------------------------------

# (route, required role, agent command, request builder)
MUTATIONS = [
    (
        "add_third_party_repository",
        SecurityRoles.ADD_THIRD_PARTY_REPOSITORY,
        "add_third_party_repository",
        lambda: tpr.AddRepositoryRequest(repository="docker", url="https://d.invalid"),
    ),
    (
        "delete_third_party_repositories",
        SecurityRoles.DELETE_THIRD_PARTY_REPOSITORY,
        "delete_third_party_repositories",
        lambda: tpr.DeleteRepositoriesRequest(
            repositories=[{"name": "docker", "file_path": "/etc/apt/x.list"}]
        ),
    ),
    (
        "enable_third_party_repositories",
        SecurityRoles.ENABLE_THIRD_PARTY_REPOSITORY,
        "enable_third_party_repositories",
        lambda: tpr.EnableDisableRepositoriesRequest(repositories=[{"name": "docker"}]),
    ),
    (
        "disable_third_party_repositories",
        SecurityRoles.DISABLE_THIRD_PARTY_REPOSITORY,
        "disable_third_party_repositories",
        lambda: tpr.EnableDisableRepositoriesRequest(repositories=[{"name": "docker"}]),
    ),
]

EMPTY_REQUESTS = {
    "add_third_party_repository": lambda: tpr.AddRepositoryRequest(repository=""),
    "delete_third_party_repositories": lambda: tpr.DeleteRepositoriesRequest(
        repositories=[]
    ),
    "enable_third_party_repositories": lambda: tpr.EnableDisableRepositoriesRequest(
        repositories=[]
    ),
    "disable_third_party_repositories": lambda: tpr.EnableDisableRepositoriesRequest(
        repositories=[]
    ),
}


async def _call(route, request, db, user):
    env = _Env()
    with env:
        out = await getattr(tpr, route)(HOST_ID, request, db=db, current_user=user)
    return out, env


class TestMutatingRoutes:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("route,role,command,build", MUTATIONS)
    async def test_each_route_queues_its_own_agent_command(
        self, route, role, command, build
    ):
        db = _FakeSession(Host=[_host()], ThirdPartyRepository=[_repo_row()])
        out, env = await _call(route, build(), db, _user(role))
        assert out.success is True
        assert env.command == command
        assert env.queued[0]["host_id"] == HOST_ID
        assert db.commits == 1
        assert env.audits

    @pytest.mark.asyncio
    @pytest.mark.parametrize("route,role,_c,build", MUTATIONS)
    async def test_each_route_requires_its_own_role(self, route, role, _c, build):
        other = next(r for _, r, _, _ in MUTATIONS if r != role)
        _, env = None, _Env()
        with env:
            with pytest.raises(HTTPException) as exc:
                await getattr(tpr, route)(
                    HOST_ID, build(), db=_FakeSession(), current_user=_user(other)
                )
        assert exc.value.status_code == 403
        # Nothing queued: authorization is the first gate, before the host
        # lookup can even leak whether the host exists.
        assert env.queued == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("route,role,_c,build", MUTATIONS)
    async def test_an_unknown_or_unapproved_host_is_a_404(self, route, role, _c, build):
        env = _Env()
        with env:
            with pytest.raises(HTTPException) as exc:
                await getattr(tpr, route)(
                    HOST_ID, build(), db=_FakeSession(), current_user=_user(role)
                )
        assert exc.value.status_code == 404
        assert env.queued == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("route,role,_c,build", MUTATIONS)
    async def test_an_unprivileged_agent_is_a_403(self, route, role, _c, build):
        db = _FakeSession(Host=[_host(is_agent_privileged=False)])
        env = _Env()
        with env:
            with pytest.raises(HTTPException) as exc:
                await getattr(tpr, route)(
                    HOST_ID, build(), db=db, current_user=_user(role)
                )
        assert exc.value.status_code == 403
        assert env.queued == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("route,role,_c,_b", MUTATIONS)
    async def test_an_empty_payload_is_a_400_before_anything_is_queued(
        self, route, role, _c, _b
    ):
        db = _FakeSession(Host=[_host()])
        env = _Env()
        with env:
            with pytest.raises(HTTPException) as exc:
                await getattr(tpr, route)(
                    HOST_ID, EMPTY_REQUESTS[route](), db=db, current_user=_user(role)
                )
        assert exc.value.status_code == 400
        assert env.queued == []
        assert db.commits == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("route,role,_c,build", MUTATIONS)
    async def test_an_unexpected_failure_becomes_a_500(self, route, role, _c, build):
        db = _FakeSession(Host=[_host()], ThirdPartyRepository=[_repo_row()])
        env = _Env()
        with env:
            with patch(
                f"{MOD}.server_queue_manager.enqueue_message",
                side_effect=RuntimeError("queue down"),
            ):
                with pytest.raises(HTTPException) as exc:
                    await getattr(tpr, route)(
                        HOST_ID, build(), db=db, current_user=_user(role)
                    )
        assert exc.value.status_code == 500


class TestDeleteDiscriminators:
    async def _delete(self, repositories):
        db = _FakeSession(Host=[_host()], ThirdPartyRepository=[_repo_row()])
        out, env = await _call(
            "delete_third_party_repositories",
            tpr.DeleteRepositoriesRequest(repositories=repositories),
            db,
            _user(SecurityRoles.DELETE_THIRD_PARTY_REPOSITORY),
        )
        return db, env

    @pytest.mark.asyncio
    async def test_a_repository_with_a_file_path_is_deleted_by_path(self):
        db, _ = await self._delete([{"name": "docker", "file_path": "/etc/x.list"}])
        assert len(db.deletes) == 1

    @pytest.mark.asyncio
    async def test_a_repository_with_only_a_name_is_deleted_by_name(self):
        db, _ = await self._delete([{"name": "docker"}])
        assert len(db.deletes) == 1

    @pytest.mark.asyncio
    async def test_a_mixed_batch_issues_one_delete_per_discriminator(self):
        # Two bulk deletes, not one per repository -- the Phase 6 N+1 fix.
        db, _ = await self._delete(
            [{"name": "a", "file_path": "/etc/a.list"}, {"name": "b"}]
        )
        assert len(db.deletes) == 2

    @pytest.mark.asyncio
    async def test_every_repository_in_the_batch_is_audited(self):
        _, env = await self._delete([{"name": "a"}, {"name": "b"}])
        assert len(env.audits) == 2
        assert [a["entity_name"] for a in env.audits] == ["a", "b"]

    @pytest.mark.asyncio
    async def test_an_entry_with_neither_key_deletes_nothing_but_still_ships(self):
        # The server has nothing to match on, but the agent may still know the
        # repository by whatever else the entry carries.
        db, env = await self._delete([{"url": "https://x.invalid"}])
        assert db.deletes == []
        assert env.command == "delete_third_party_repositories"
        assert env.audits[0]["entity_name"] == "Unknown"
