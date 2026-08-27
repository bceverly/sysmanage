# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Config-management prerequisite status + install routes (Phase 20.1).

Two things here are easy to get wrong and expensive to notice later.

The first is the SQL PREFILTER in ``_candidate_packages``.  It exists so a
desktop's several-thousand-row software inventory does not get pulled into
memory to find one package, but it must never be the thing that DECIDES the
match -- ``py3*-ansible-core`` is a glob and SQL LIKE is not.  A prefilter that
is narrower than the pattern silently reports a satisfied host as missing.

The second is the 400 on install: Windows and an unknown Linux both produce no
plan, and both must refuse rather than queueing something the agent cannot run.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.api import config_mgmt_prereq as api
from backend.security.roles import SecurityRoles

MOD = "backend.api.config_mgmt_prereq"
HOST_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows
        self.filters = []

    def filter(self, *args, **_kwargs):
        self.filters.extend(args)
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, **by_key):
        self._by_key = {k: list(v) for k, v in by_key.items()}
        self.commits = 0
        self.queries = []

    def query(self, *entities):
        query = _FakeQuery(self._by_key.get(entities[0].__name__, []))
        self.queries.append(query)
        return query

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
        id=HOST_ID,
        fqdn="host.invalid",
        platform="Linux",
        platform_release="Ubuntu 24.04",
        platform_version="24.04",
    )
    for key, value in overrides.items():
        setattr(host, key, value)
    return host


def _pkg(name, version, manager="apt"):
    return SimpleNamespace(
        package_name=name, package_version=version, package_manager=manager
    )


def _user(*roles):
    granted = set(roles)
    return SimpleNamespace(
        id="u1", userid="admin@invalid", has_role=lambda role: role in granted
    )


class _Env:
    """Patches the queue, the audit trail and the audit engine."""

    def __init__(self):
        self.enqueued = []
        self.audits = []

    def _enqueue(self, **kwargs):
        self.enqueued.append(kwargs)
        return "msg-1"

    def __enter__(self):
        self._patches = [
            patch(f"{MOD}.queue_ops.enqueue_message", side_effect=self._enqueue),
            patch(f"{MOD}.persistence_db.get_engine"),
            patch(f"{MOD}.sessionmaker", return_value=_FakeSession()),
            patch(
                f"{MOD}.AuditService.log",
                side_effect=lambda **kw: self.audits.append(kw),
            ),
        ]
        for patcher in self._patches:
            patcher.start()
        return self

    def __exit__(self, *_exc):
        for patcher in self._patches:
            patcher.stop()
        return False


class TestHostLookup:
    @pytest.mark.asyncio
    async def test_malformed_host_id_is_a_400_not_a_500(self):
        with pytest.raises(HTTPException) as exc:
            await api.get_config_mgmt_prerequisite("not-a-uuid", _FakeSession())
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_unknown_host_is_a_404(self):
        with pytest.raises(HTTPException) as exc:
            await api.get_config_mgmt_prerequisite(str(HOST_ID), _FakeSession(Host=[]))
        assert exc.value.status_code == 404


class TestPrefilter:
    """The LIKE prefilter must be wider than the glob, never narrower."""

    def test_freebsd_prefilter_still_admits_every_python_prefix(self):
        session = _FakeSession(SoftwarePackage=[])
        with patch(f"{MOD}.models.SoftwarePackage") as model:
            model.__name__ = "SoftwarePackage"
            api._candidate_packages(session, _host(), "py3*-ansible-core")
        # The prefilter anchors on the fixed tail, so py311/py312/py313 all
        # survive it and the fnmatch decides.
        model.package_name.like.assert_called_once_with("%-ansible-core")

    def test_literal_pattern_prefilters_on_the_whole_name(self):
        session = _FakeSession(SoftwarePackage=[])
        with patch(f"{MOD}.models.SoftwarePackage") as model:
            model.__name__ = "SoftwarePackage"
            api._candidate_packages(session, _host(), "ansible-core")
        model.package_name.like.assert_called_once_with("%ansible-core")

    def test_no_pattern_issues_no_query_at_all(self):
        # Windows has nothing to look for; querying would be pure waste.
        session = _FakeSession(SoftwarePackage=[_pkg("ansible-core", "2.20.1")])
        assert api._candidate_packages(session, _host(), None) == []
        assert session.queries == []

    def test_rows_are_flattened_to_the_fields_the_evaluator_reads(self):
        session = _FakeSession(SoftwarePackage=[_pkg("ansible-core", "2.20.1")])
        assert api._candidate_packages(session, _host(), "ansible-core") == [
            {
                "package_name": "ansible-core",
                "package_version": "2.20.1",
                "package_manager": "apt",
            }
        ]


class TestStatusRoute:
    @pytest.mark.asyncio
    async def test_installed_host_reports_satisfied_with_no_button(self):
        session = _FakeSession(
            Host=[_host()], SoftwarePackage=[_pkg("ansible-core", "2.20.1")]
        )
        result = await api.get_config_mgmt_prerequisite(str(HOST_ID), session)
        assert result.status == "satisfied"
        assert result.installed_version == "2.20.1"
        assert result.can_install is False
        assert result.host_id == str(HOST_ID)

    @pytest.mark.asyncio
    async def test_bare_host_reports_missing_with_a_button(self):
        session = _FakeSession(Host=[_host()], SoftwarePackage=[])
        result = await api.get_config_mgmt_prerequisite(str(HOST_ID), session)
        assert result.status == "missing"
        assert result.can_install is True

    @pytest.mark.asyncio
    async def test_windows_reports_not_required_and_offers_nothing(self):
        session = _FakeSession(Host=[_host(platform="Windows")], SoftwarePackage=[])
        result = await api.get_config_mgmt_prerequisite(str(HOST_ID), session)
        assert result.status == "not_required"
        assert result.executor == "dsc"
        assert result.can_install is False

    @pytest.mark.asyncio
    async def test_old_version_reports_too_old_rather_than_missing(self):
        session = _FakeSession(
            Host=[_host()], SoftwarePackage=[_pkg("ansible-core", "2.14.2")]
        )
        result = await api.get_config_mgmt_prerequisite(str(HOST_ID), session)
        assert result.status == "too_old"
        assert result.installed_version == "2.14.2"
        assert result.minimum_version == "2.20"


class TestInstallRoute:
    @pytest.mark.asyncio
    async def test_install_requires_the_add_package_role(self):
        with _Env():
            with pytest.raises(HTTPException) as exc:
                await api.install_config_mgmt_prerequisite(
                    str(HOST_ID), _FakeSession(Host=[_host()]), _user()
                )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_install_queues_a_deployment_plan_for_the_host(self):
        session = _FakeSession(Host=[_host()])
        with _Env() as env:
            result = await api.install_config_mgmt_prerequisite(
                str(HOST_ID), session, _user(SecurityRoles.ADD_PACKAGE)
            )
        assert result.queued is True
        # Two messages: the install, then the inventory refresh that lets the
        # card notice the install without waiting for the next collection.
        assert len(env.enqueued) == 2
        queued = env.enqueued[0]
        assert queued["host_id"] == str(HOST_ID)
        plan = queued["message_data"]["data"]["parameters"]["plan"]
        assert plan["packages"] == [{"manager": "apt", "name": "ansible-core"}]
        # Nothing is dispatched until the queue rows are durable.
        assert session.commits == 1

    @pytest.mark.asyncio
    async def test_install_is_followed_by_an_inventory_refresh(self):
        # Ordering matters: the refresh has to be queued BEHIND the install or
        # it re-reports the old inventory and the card stays wrong.
        with _Env() as env:
            await api.install_config_mgmt_prerequisite(
                str(HOST_ID),
                _FakeSession(Host=[_host()]),
                _user(SecurityRoles.ADD_PACKAGE),
            )
        refresh = env.enqueued[1]["message_data"]
        assert refresh["data"]["command_type"] == "update_software_inventory"

    @pytest.mark.asyncio
    async def test_install_is_audited(self):
        with _Env() as env:
            await api.install_config_mgmt_prerequisite(
                str(HOST_ID),
                _FakeSession(Host=[_host()]),
                _user(SecurityRoles.ADD_PACKAGE),
            )
        assert len(env.audits) == 1
        assert env.audits[0]["entity_id"] == str(HOST_ID)
        assert env.audits[0]["details"]["executor"] == "ansible-core"

    @pytest.mark.asyncio
    async def test_windows_install_refuses_rather_than_queueing_a_no_op(self):
        session = _FakeSession(Host=[_host(platform="Windows")])
        with _Env() as env:
            with pytest.raises(HTTPException) as exc:
                await api.install_config_mgmt_prerequisite(
                    str(HOST_ID), session, _user(SecurityRoles.ADD_PACKAGE)
                )
        assert exc.value.status_code == 400
        assert env.enqueued == []

    @pytest.mark.asyncio
    async def test_unknown_platform_install_refuses_rather_than_guessing(self):
        # Firing the wrong package manager fails at the far end and reads as a
        # product bug; refusing here is the honest outcome.
        session = _FakeSession(Host=[_host(platform_release="SomeVendorOS 1.0")])
        with _Env() as env:
            with pytest.raises(HTTPException) as exc:
                await api.install_config_mgmt_prerequisite(
                    str(HOST_ID), session, _user(SecurityRoles.ADD_PACKAGE)
                )
        assert exc.value.status_code == 400
        assert env.enqueued == []


class TestEnginesEndpoint:
    """The multi-engine view (Phase 20.1).

    The inventory prefilter exists so a desktop's several-thousand-row package
    list is not dragged into memory. Querying once per engine would undo that,
    so the route de-duplicates patterns before it reads.
    """

    @pytest.mark.asyncio
    async def test_lists_every_applicable_engine_readiest_first(self):
        session = _FakeSession(
            Host=[_host()],
            SoftwarePackage=[_pkg("puppet-agent", "8.10.0", "apt")],
        )
        out = await api.list_config_mgmt_engines(str(HOST_ID), session)
        assert out.host_id == str(HOST_ID)
        assert out.default_engine == "ansible-core"
        names = [e.engine for e in out.engines]
        assert "dsc" not in names, "dsc must not be offered off Windows"
        assert out.engines[0].engine == "puppet"
        assert out.engines[0].status == "satisfied"

    @pytest.mark.asyncio
    async def test_windows_leads_with_the_bundled_engine(self):
        session = _FakeSession(Host=[_host(platform="Windows")], SoftwarePackage=[])
        out = await api.list_config_mgmt_engines(str(HOST_ID), session)
        assert out.default_engine == "dsc"
        assert out.engines[0].engine == "dsc"
        assert out.engines[0].status == "not_required"

    @pytest.mark.asyncio
    async def test_the_inventory_is_not_queried_once_per_engine(self):
        # Four engines apply on Linux but they do not need four reads; the
        # route collapses duplicate patterns first.
        session = _FakeSession(Host=[_host()], SoftwarePackage=[])
        await api.list_config_mgmt_engines(str(HOST_ID), session)
        package_queries = [q for q in session.queries if q is not session.queries[0]]
        assert (
            len(package_queries) <= 3
        ), f"one query per engine defeats the prefilter: {len(package_queries)}"

    @pytest.mark.asyncio
    async def test_malformed_host_id_is_a_400(self):
        with pytest.raises(HTTPException) as exc:
            await api.list_config_mgmt_engines("nope", _FakeSession())
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_unknown_host_is_a_404(self):
        with pytest.raises(HTTPException) as exc:
            await api.list_config_mgmt_engines(str(HOST_ID), _FakeSession(Host=[]))
        assert exc.value.status_code == 404


class TestEngineAwareInstall:
    """Installing a NAMED engine (Phase 20.1 multi-engine).

    The install route gained an ``engine`` query parameter. It is last in the
    signature deliberately: the dependency parameters are passed positionally
    here, so a query param inserted ahead of them shifts the session into
    ``engine`` and hands ``current_user`` a Depends object.
    """

    @pytest.mark.asyncio
    async def test_omitting_the_engine_installs_the_platform_default(self):
        session = _FakeSession(Host=[_host()])
        with _Env() as env:
            await api.install_config_mgmt_prerequisite(
                str(HOST_ID), session, _user(SecurityRoles.ADD_PACKAGE)
            )
        plan = env.enqueued[0]["message_data"]["data"]["parameters"]["plan"]
        assert plan["packages"] == [{"manager": "apt", "name": "ansible-core"}]

    @pytest.mark.asyncio
    async def test_a_licensed_engine_installs_its_own_package(self):
        session = _FakeSession(Host=[_host()])
        with _Env() as env, patch(
            "backend.api.config_mgmt_prereq.require_module", return_value=None
        ):
            await api.install_config_mgmt_prerequisite(
                str(HOST_ID),
                session,
                _user(SecurityRoles.ADD_PACKAGE),
                engine="puppet",
            )
        plan = env.enqueued[0]["message_data"]["data"]["parameters"]["plan"]
        assert plan["packages"] == [{"manager": "apt", "name": "puppet-agent"}]

    @pytest.mark.asyncio
    async def test_an_unlicensed_engine_install_is_refused(self):
        session = _FakeSession(Host=[_host()])
        with _Env() as env, patch(
            "backend.api.config_mgmt_prereq.require_module",
            side_effect=HTTPException(status_code=403, detail="pro_plus_required"),
        ):
            with pytest.raises(HTTPException) as exc:
                await api.install_config_mgmt_prerequisite(
                    str(HOST_ID),
                    session,
                    _user(SecurityRoles.ADD_PACKAGE),
                    engine="chef",
                )
        assert exc.value.status_code == 403
        assert env.enqueued == []

    @pytest.mark.asyncio
    async def test_the_free_engine_never_consults_the_licence(self):
        session = _FakeSession(Host=[_host()])
        with _Env(), patch("backend.api.config_mgmt_prereq.require_module") as gate:
            await api.install_config_mgmt_prerequisite(
                str(HOST_ID),
                session,
                _user(SecurityRoles.ADD_PACKAGE),
                engine="ansible-core",
            )
        gate.assert_not_called()

    @pytest.mark.asyncio
    async def test_an_unknown_engine_is_a_400(self):
        session = _FakeSession(Host=[_host()])
        with _Env() as env:
            with pytest.raises(HTTPException) as exc:
                await api.install_config_mgmt_prerequisite(
                    str(HOST_ID),
                    session,
                    _user(SecurityRoles.ADD_PACKAGE),
                    engine="terraform",
                )
        assert exc.value.status_code == 400
        assert env.enqueued == []

    @pytest.mark.asyncio
    async def test_the_audit_records_the_engine_actually_installed(self):
        # Auditing a Chef install as "ansible-core" would make the trail wrong
        # in exactly the case somebody later needs it to be right.
        session = _FakeSession(Host=[_host()])
        with _Env() as env, patch(
            "backend.api.config_mgmt_prereq.require_module", return_value=None
        ):
            await api.install_config_mgmt_prerequisite(
                str(HOST_ID), session, _user(SecurityRoles.ADD_PACKAGE), engine="chef"
            )
        assert env.audits[0]["details"]["executor"] == "chef"

    @pytest.mark.asyncio
    async def test_an_engine_with_no_package_here_is_refused(self):
        # Salt is not in Ubuntu's repositories; a licence does not change that.
        session = _FakeSession(Host=[_host()])
        with _Env() as env, patch(
            "backend.api.config_mgmt_prereq.require_module", return_value=None
        ):
            with pytest.raises(HTTPException) as exc:
                await api.install_config_mgmt_prerequisite(
                    str(HOST_ID),
                    session,
                    _user(SecurityRoles.ADD_PACKAGE),
                    engine="salt",
                )
        assert exc.value.status_code == 400
        assert env.enqueued == []
