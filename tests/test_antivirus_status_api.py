# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Antivirus deploy / enable / disable / remove and coverage reporting.

The bulk deploy is the interesting one: it is partial-success by design, so a
host that fails is reported in ``failed_hosts`` and the request still returns
200.  That makes every "continue" branch a silent outcome -- an operator who
selects forty hosts and gets thirty-eight deployments sees a success banner
unless the per-host reason text is right.  Each of those reasons is asserted.

The OS-name derivation feeding the AntivirusDefault lookup is the other trap:
OpenBSD reports ``platform_release`` as a bare "7.7", so keying the lookup off
platform_release alone finds no default and the host is skipped with a
confusing "no antivirus configured for OS: 7" message.

Coverage counts open-source and commercial AV as a UNION -- double-counting a
host running both would report >100% coverage.
"""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.api import antivirus_status as av
from backend.security.roles import SecurityRoles

MOD = "backend.api.antivirus_status"
HOST_ID = uuid.UUID("99999999-9999-4999-8999-999999999999")


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def count(self):
        return len(self._rows)


class _FakeSession:
    def __init__(self, **by_key):
        self._by_key = {k: list(v) for k, v in by_key.items()}
        self.commits = 0
        self.closed = False

    def query(self, *entities):
        # Column queries (AntivirusStatus.host_id) key off the attribute name
        # prefixed by its class, so the coverage route's two scalar selects
        # stay distinguishable from a whole-entity select.
        entity = entities[0]
        name = getattr(entity, "__name__", None)
        if name is None:
            name = f"{entity.class_.__name__}.{entity.key}"
        return _FakeQuery(self._by_key.get(name, []))

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True

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


def _user(*roles):
    granted = set(roles)
    return SimpleNamespace(
        id="u1", userid="admin@invalid", has_role=lambda role: role in granted
    )


def _default(os_name="Ubuntu", package="clamav"):
    return SimpleNamespace(os_name=os_name, antivirus_package=package)


class _Env:
    """Patches the queue, plan builder, audit trail and audit engine."""

    def __init__(self, plan=None):
        self.plan = plan or {"commands": []}
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
            patch(f"{MOD}.av_plan_builder.build_deploy_plan", return_value=self.plan),
            patch(f"{MOD}.av_plan_builder.build_enable_plan", return_value=self.plan),
            patch(f"{MOD}.av_plan_builder.build_disable_plan", return_value=self.plan),
            patch(f"{MOD}.av_plan_builder.build_remove_plan", return_value=self.plan),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *_exc):
        for p in self._patches:
            p.stop()
        return False


class TestHostInfoForAvPlanner:
    def test_only_the_three_os_fields_are_packed(self):
        assert av._host_info_for_av_planner(_host()) == {
            "platform": "Linux",
            "platform_release": "Ubuntu 24.04",
            "platform_version": "24.04",
        }


class TestStatusResponseCoercion:
    """The response model normalises what SQLAlchemy hands it."""

    def test_uuid_columns_are_rendered_as_strings(self):
        # Pydantic would otherwise serialise a UUID object and the frontend
        # compares host_id against a string from the URL.
        out = av.AntivirusStatusResponse(
            id=uuid.uuid4(),
            host_id=HOST_ID,
            last_updated=datetime(2026, 1, 1),
        )
        assert out.host_id == str(HOST_ID)
        assert isinstance(out.id, str)

    def test_string_ids_pass_through_unchanged(self):
        out = av.AntivirusStatusResponse(
            id="s1", host_id="h1", last_updated=datetime(2026, 1, 1)
        )
        assert (out.id, out.host_id) == ("s1", "h1")

    def test_a_naive_timestamp_is_stamped_utc(self):
        # Columns are stored naive-UTC; without this the browser renders them
        # in local time and "last updated" drifts by the offset.
        out = av.AntivirusStatusResponse(
            id="s1", host_id="h1", last_updated=datetime(2026, 1, 1)
        )
        assert out.last_updated.tzinfo == timezone.utc

    def test_an_aware_timestamp_is_left_alone(self):
        aware = datetime(2026, 1, 1, tzinfo=timezone.utc)
        out = av.AntivirusStatusResponse(id="s1", host_id="h1", last_updated=aware)
        assert out.last_updated == aware


class TestGetAntivirusStatus:
    @pytest.mark.asyncio
    async def test_a_recorded_status_is_returned(self):
        status = SimpleNamespace(id="s1")
        db = _FakeSession(Host=[_host()], AntivirusStatus=[status])
        assert await av.get_antivirus_status(str(HOST_ID), db=db) is status

    @pytest.mark.asyncio
    async def test_a_host_that_has_never_reported_returns_null_not_404(self):
        # "No AV data yet" is a normal state for a freshly enrolled host; a
        # 404 here would render as an error banner on every new host.
        db = _FakeSession(Host=[_host()])
        assert await av.get_antivirus_status(str(HOST_ID), db=db) is None

    @pytest.mark.asyncio
    async def test_a_malformed_host_id_is_a_400(self):
        with pytest.raises(HTTPException) as exc:
            await av.get_antivirus_status("not-a-uuid", db=_FakeSession())
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_an_unknown_host_is_a_404(self):
        with pytest.raises(HTTPException) as exc:
            await av.get_antivirus_status(str(HOST_ID), db=_FakeSession())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_an_unexpected_failure_is_a_500(self):
        db = _FakeSession()
        db.query = MagicMock(side_effect=RuntimeError("db gone"))
        with pytest.raises(HTTPException) as exc:
            await av.get_antivirus_status(str(HOST_ID), db=db)
        assert exc.value.status_code == 500


class TestDeployAntivirus:
    async def _deploy(self, host_ids, db, user=None, env=None):
        env = env or _Env()
        with env:
            out = await av.deploy_antivirus(
                av.AntivirusDeployRequest(host_ids=host_ids),
                db_session=db,
                current_user=user or _user(SecurityRoles.DEPLOY_ANTIVIRUS),
            )
        return out, env

    @pytest.mark.asyncio
    async def test_a_user_without_the_role_is_a_403(self):
        with pytest.raises(HTTPException) as exc:
            await self._deploy([str(HOST_ID)], _FakeSession(), user=_user())
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_a_deployable_host_is_queued_and_audited(self):
        db = _FakeSession(Host=[_host()], AntivirusDefault=[_default()])
        out, env = await self._deploy([str(HOST_ID)], db)
        assert out.success_count == 1
        assert out.failed_hosts == []
        assert "all 1 hosts" in out.message
        assert env.enqueued[0]["host_id"] == str(HOST_ID)
        assert env.audits[0]["details"] == {"antivirus_package": "clamav"}

    @pytest.mark.asyncio
    async def test_a_malformed_id_is_reported_not_raised(self):
        out, env = await self._deploy(["not-a-uuid"], _FakeSession())
        assert out.success_count == 0
        assert out.failed_hosts[0]["reason"] == "Invalid host ID format"
        assert env.enqueued == []

    @pytest.mark.asyncio
    async def test_an_unknown_host_is_reported(self):
        out, _ = await self._deploy([str(HOST_ID)], _FakeSession())
        assert out.failed_hosts[0]["reason"] == "Host not found"

    @pytest.mark.asyncio
    async def test_a_host_with_no_os_strings_is_reported(self):
        host = _host(platform=None, platform_release=None)
        db = _FakeSession(Host=[host], AntivirusDefault=[_default()])
        out, _ = await self._deploy([str(HOST_ID)], db)
        assert "determine host operating system" in out.failed_hosts[0]["reason"]

    @pytest.mark.asyncio
    async def test_an_os_with_no_configured_default_is_reported_by_name(self):
        db = _FakeSession(Host=[_host()], AntivirusDefault=[_default("Debian")])
        out, _ = await self._deploy([str(HOST_ID)], db)
        assert "OS: Ubuntu" in out.failed_hosts[0]["reason"]

    @pytest.mark.asyncio
    async def test_a_default_row_with_a_blank_package_is_reported(self):
        db = _FakeSession(Host=[_host()], AntivirusDefault=[_default(package="")])
        out, _ = await self._deploy([str(HOST_ID)], db)
        assert "No antivirus default" in out.failed_hosts[0]["reason"]

    @pytest.mark.asyncio
    async def test_macos_is_keyed_on_the_platform_not_its_release_codename(self):
        # platform_release on macOS is a Darwin kernel version; matching on it
        # would never find the macOS default.
        host = _host(platform="macOS", platform_release="23.5.0")
        db = _FakeSession(Host=[host], AntivirusDefault=[_default("macOS")])
        out, _ = await self._deploy([str(HOST_ID)], db)
        assert out.success_count == 1

    @pytest.mark.asyncio
    async def test_a_numeric_bsd_release_falls_back_to_the_platform(self):
        # OpenBSD reports platform_release "7.7"; keying on it yields "7" and
        # matches no default at all.
        host = _host(platform="OpenBSD", platform_release="7.7")
        db = _FakeSession(Host=[host], AntivirusDefault=[_default("OpenBSD")])
        out, _ = await self._deploy([str(HOST_ID)], db)
        assert out.success_count == 1

    @pytest.mark.asyncio
    async def test_the_version_is_stripped_from_the_release_string(self):
        host = _host(platform_release="Ubuntu 25.04")
        db = _FakeSession(Host=[host], AntivirusDefault=[_default("Ubuntu")])
        out, _ = await self._deploy([str(HOST_ID)], db)
        assert out.success_count == 1

    @pytest.mark.asyncio
    async def test_a_partial_batch_reports_both_halves(self):
        db = _FakeSession(Host=[_host()], AntivirusDefault=[_default()])
        out, _ = await self._deploy([str(HOST_ID), "not-a-uuid"], db)
        assert out.success_count == 1
        assert len(out.failed_hosts) == 1
        assert "1 of 2 hosts" in out.message

    @pytest.mark.asyncio
    async def test_a_wholly_failed_batch_says_so(self):
        out, _ = await self._deploy(["bad-1", "bad-2"], _FakeSession())
        assert out.message == "Antivirus deployment failed for all hosts"

    @pytest.mark.asyncio
    async def test_a_per_host_exception_does_not_abort_the_batch(self):
        db = _FakeSession(Host=[_host()], AntivirusDefault=[_default()])
        env = _Env()
        with env:
            with patch(
                f"{MOD}.queue_ops.enqueue_message",
                side_effect=RuntimeError("queue down"),
            ):
                out = await av.deploy_antivirus(
                    av.AntivirusDeployRequest(host_ids=[str(HOST_ID)]),
                    db_session=db,
                    current_user=_user(SecurityRoles.DEPLOY_ANTIVIRUS),
                )
        assert out.success_count == 0
        assert "queue down" in out.failed_hosts[0]["reason"]


class TestSingleHostActions:
    ACTIONS = [
        ("enable_antivirus", SecurityRoles.ENABLE_ANTIVIRUS, "enable"),
        ("disable_antivirus", SecurityRoles.DISABLE_ANTIVIRUS, "disable"),
        # "remov" matches both the message ("remove command sent") and the
        # audit description ("antivirus removal"), which use different words.
        ("remove_antivirus", SecurityRoles.REMOVE_ANTIVIRUS, "remov"),
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("route,role,word", ACTIONS)
    async def test_each_action_queues_a_plan_and_audits_it(self, route, role, word):
        db = _FakeSession(Host=[_host()])
        env = _Env()
        with env:
            out = await getattr(av, route)(
                str(HOST_ID), db=db, current_user=_user(role)
            )
        assert word in out["message"]
        assert env.enqueued[0]["host_id"] == str(HOST_ID)
        assert db.commits == 1
        assert word in env.audits[0]["description"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("route,role,_word", ACTIONS)
    async def test_each_action_needs_its_own_role(self, route, role, _word):
        # Distinct roles: an operator allowed to enable AV must not thereby be
        # allowed to remove it.
        other = next(r for _, r, _ in self.ACTIONS if r != role)
        with pytest.raises(HTTPException) as exc:
            await getattr(av, route)(
                str(HOST_ID), db=_FakeSession(), current_user=_user(other)
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("route,role,_word", ACTIONS)
    async def test_an_unknown_host_is_a_404(self, route, role, _word):
        env = _Env()
        with env:
            with pytest.raises(HTTPException) as exc:
                await getattr(av, route)(
                    str(HOST_ID), db=_FakeSession(), current_user=_user(role)
                )
        assert exc.value.status_code == 404
        assert env.enqueued == []

    @pytest.mark.asyncio
    async def test_an_unexpected_removal_failure_is_a_500(self):
        db = _FakeSession(Host=[_host()])
        env = _Env()
        with env:
            with patch(
                f"{MOD}.queue_ops.enqueue_message",
                side_effect=RuntimeError("queue down"),
            ):
                with pytest.raises(HTTPException) as exc:
                    await av.remove_antivirus(
                        str(HOST_ID),
                        db=db,
                        current_user=_user(SecurityRoles.REMOVE_ANTIVIRUS),
                    )
        assert exc.value.status_code == 500


class TestAntivirusCoverage:
    @pytest.mark.asyncio
    async def test_an_empty_fleet_reports_zero_rather_than_dividing_by_zero(self):
        out = await av.get_antivirus_coverage(db=_FakeSession())
        assert out.total_hosts == 0
        assert out.coverage_percentage == 0.0

    @pytest.mark.asyncio
    async def test_open_source_and_commercial_are_counted_as_a_union(self):
        both = uuid.uuid4()
        db = _FakeSession(
            Host=[_host(), _host(), _host(), _host()],
            **{
                "AntivirusStatus.host_id": [(both,), (uuid.uuid4(),)],
                "CommercialAntivirusStatus.host_id": [(both,)],
            },
        )
        out = await av.get_antivirus_coverage(db=db)
        # A host running both must count once; summing would report 3/4 here
        # and could exceed 100% on a mixed fleet.
        assert out.hosts_with_antivirus == 2
        assert out.hosts_without_antivirus == 2
        assert out.coverage_percentage == 50.0

    @pytest.mark.asyncio
    async def test_the_percentage_is_rounded_to_two_places(self):
        db = _FakeSession(
            Host=[_host()] * 3,
            **{"AntivirusStatus.host_id": [(uuid.uuid4(),)]},
        )
        out = await av.get_antivirus_coverage(db=db)
        assert out.coverage_percentage == 33.33

    @pytest.mark.asyncio
    async def test_a_query_failure_is_a_500(self):
        db = _FakeSession()
        db.query = MagicMock(side_effect=RuntimeError("db gone"))
        with pytest.raises(HTTPException) as exc:
            await av.get_antivirus_coverage(db=db)
        assert exc.value.status_code == 500
