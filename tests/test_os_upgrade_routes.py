# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""OS-upgrade listing, summary, and execution.

Execution is per-host partial success -- every host gets a result entry and
the request returns 200 regardless -- so each skip reason is the only signal
an operator gets.  Two of them matter especially:

* An image-mode (bootc / rpm-ostree) host has no packages to upgrade.  If it
  fell through to the normal path it would be handed an ``apply_updates``
  command its agent cannot satisfy, and the run would look queued for ever
  rather than refused with an explanation.
* The package-manager allowlist is what stops this endpoint being a general
  "upgrade anything" route.  A request naming ``apt`` must be refused
  outright, not silently filtered down to nothing and reported as
  "no upgrades available".
"""

import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.api.updates import os_upgrade_routes as osr
from backend.api.updates.models import UpdateExecutionRequest
from backend.security.roles import SecurityRoles

MOD = "backend.api.updates.os_upgrade_routes"
HOST_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def count(self):
        return len(self._rows)


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


def _host(host_id=None, **overrides):
    host = SimpleNamespace(
        id=host_id or HOST_ID,
        fqdn="host.invalid",
        platform="Linux",
        is_image_mode=False,
    )
    for key, value in overrides.items():
        setattr(host, key, value)
    return host


def _update(host=None, package_manager="ubuntu-release", **overrides):
    host = host or _host()
    row = SimpleNamespace(
        id=uuid.uuid4(),
        host_id=host.id,
        host=host,
        package_name="ubuntu-release-upgrade",
        current_version="24.04",
        available_version="26.04",
        package_manager=package_manager,
        update_type="os",
        requires_reboot=True,
        size_bytes=0,
        discovered_at=datetime(2026, 1, 1),
        updated_at=None,
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def _user(*roles):
    granted = set(roles)
    return SimpleNamespace(
        id="u1",
        userid="admin@invalid",
        _role_cache={},
        load_role_cache=lambda s: None,
        has_role=lambda role: role in granted,
    )


def _bound(session):
    return patch(f"{MOD}.request_sessionmaker", return_value=session)


class TestGetOsUpgrades:
    @pytest.mark.asyncio
    async def test_available_upgrades_are_serialized_with_host_context(self):
        session = _FakeSession(PackageUpdate=[_update()])
        with _bound(session):
            out = await osr.get_os_upgrades(host_id=None)
        assert out["total_count"] == 1
        assert out["hosts_with_upgrades"] == 1
        row = out["os_upgrades"][0]
        assert row["host_fqdn"] == "host.invalid"
        assert row["available_version"] == "26.04"
        assert row["discovered_at"] == "2026-01-01T00:00:00"

    @pytest.mark.asyncio
    async def test_hosts_with_upgrades_counts_distinct_hosts(self):
        host = _host()
        session = _FakeSession(
            PackageUpdate=[_update(host), _update(host), _update(_host("other"))]
        )
        with _bound(session):
            out = await osr.get_os_upgrades(host_id=None)
        # Two upgrades on one host is one host needing attention, not two.
        assert out["total_count"] == 3
        assert out["hosts_with_upgrades"] == 2

    @pytest.mark.asyncio
    async def test_a_never_discovered_timestamp_serializes_as_null(self):
        session = _FakeSession(PackageUpdate=[_update(discovered_at=None)])
        with _bound(session):
            out = await osr.get_os_upgrades(host_id=None)
        assert out["os_upgrades"][0]["discovered_at"] is None

    @pytest.mark.asyncio
    async def test_filtering_by_an_unknown_host_is_a_404(self):
        session = _FakeSession(PackageUpdate=[_update()])
        with _bound(session):
            with pytest.raises(HTTPException) as exc:
                await osr.get_os_upgrades(host_id=HOST_ID)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_filtering_by_a_known_host_succeeds(self):
        session = _FakeSession(PackageUpdate=[_update()], Host=[_host()])
        with _bound(session):
            out = await osr.get_os_upgrades(host_id=HOST_ID)
        assert out["total_count"] == 1

    @pytest.mark.asyncio
    async def test_an_empty_fleet_reports_zeroes(self):
        with _bound(_FakeSession()):
            out = await osr.get_os_upgrades(host_id=None)
        assert out == {"os_upgrades": [], "total_count": 0, "hosts_with_upgrades": 0}

    @pytest.mark.asyncio
    async def test_an_unexpected_failure_is_a_500(self):
        session = _FakeSession()
        session.query = MagicMock(side_effect=RuntimeError("db gone"))
        with _bound(session):
            with pytest.raises(HTTPException) as exc:
                await osr.get_os_upgrades(host_id=None)
        assert exc.value.status_code == 500


class TestGetOsUpgradesSummary:
    @pytest.mark.asyncio
    async def test_upgrades_are_grouped_by_package_manager(self):
        session = _FakeSession(
            PackageUpdate=[
                _update(package_manager="ubuntu-release"),
                _update(_host("h2"), package_manager="ubuntu-release"),
                _update(_host("h3"), package_manager="fedora-release"),
            ],
            Host=[_host(), _host("h2"), _host("h3")],
        )
        with _bound(session):
            out = await osr.get_os_upgrades_summary()
        assert out["total_os_upgrades"] == 3
        assert out["os_upgrades_by_type"] == {
            "ubuntu-release": 2,
            "fedora-release": 1,
        }
        assert out["total_hosts"] == 3

    @pytest.mark.asyncio
    async def test_the_host_id_set_is_replaced_by_a_count(self):
        session = _FakeSession(PackageUpdate=[_update(), _update()], Host=[_host()])
        with _bound(session):
            out = await osr.get_os_upgrades_summary()
        group = out["os_upgrades_summary"][0]
        # A set is not JSON-serialisable; leaving it in would 500 the route.
        assert "host_ids" not in group
        assert group["total_hosts"] == 1

    @pytest.mark.asyncio
    async def test_an_empty_fleet_summarises_to_nothing(self):
        with _bound(_FakeSession()):
            out = await osr.get_os_upgrades_summary()
        assert out["os_upgrades_summary"] == []
        assert out["hosts_with_os_upgrades"] == 0

    @pytest.mark.asyncio
    async def test_an_unexpected_failure_is_a_500(self):
        session = _FakeSession()
        session.query = MagicMock(side_effect=RuntimeError("db gone"))
        with _bound(session):
            with pytest.raises(HTTPException) as exc:
                await osr.get_os_upgrades_summary()
        assert exc.value.status_code == 500


class TestExecuteOsUpgrades:
    async def _execute(self, session, request=None, enqueue_error=None):
        queued = []

        def _enqueue(**kwargs):
            if enqueue_error:
                raise enqueue_error
            queued.append(kwargs)
            return "msg-1"

        with _bound(session):
            with patch(f"{MOD}.queue_ops.enqueue_message", side_effect=_enqueue):
                with patch(f"{MOD}.AuditService.log") as audit:
                    out = await osr.execute_os_upgrades(
                        request
                        or UpdateExecutionRequest(
                            host_ids=[HOST_ID], package_names=["ubuntu-release-upgrade"]
                        ),
                        current_user="admin@invalid",
                    )
        return out, queued, audit

    def _session(self, **overrides):
        defaults = {
            "User": [_user(SecurityRoles.APPLY_HOST_OS_UPGRADE)],
            "Host": [_host()],
            "PackageUpdate": [_update()],
        }
        defaults.update(overrides)
        return _FakeSession(**defaults)

    @pytest.mark.asyncio
    async def test_a_valid_request_queues_and_audits_the_upgrade(self):
        session = self._session()
        out, queued, audit = await self._execute(session)
        result = out["results"][0]
        assert result["status"] == "success"
        assert result["upgrades_count"] == 1
        # OS upgrades always reboot; the UI warns on this flag.
        assert result["requires_reboot"] is True
        assert queued[0]["host_id"] == HOST_ID
        audit.assert_called_once()

    @pytest.mark.asyncio
    async def test_the_queued_command_carries_the_version_pair(self):
        _, queued, _ = await self._execute(self._session())
        packages = queued[0]["message_data"]["data"]["parameters"]["packages"]
        assert packages[0]["current_version"] == "24.04"
        assert packages[0]["available_version"] == "26.04"

    @pytest.mark.asyncio
    async def test_an_unknown_user_is_a_401(self):
        with pytest.raises(HTTPException) as exc:
            await self._execute(self._session(User=[]))
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_a_user_without_the_role_is_a_403(self):
        with pytest.raises(HTTPException) as exc:
            await self._execute(self._session(User=[_user()]))
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_a_cold_role_cache_is_loaded_before_the_check(self):
        user = _user(SecurityRoles.APPLY_HOST_OS_UPGRADE)
        user._role_cache = None
        loaded = []
        user.load_role_cache = lambda s: loaded.append(s)
        await self._execute(self._session(User=[user]))
        assert loaded

    @pytest.mark.asyncio
    async def test_a_non_os_package_manager_is_refused_outright(self):
        # Filtering it down to nothing and reporting "no upgrades" would let
        # this endpoint be probed as a general update route.
        request = UpdateExecutionRequest(
            host_ids=[HOST_ID],
            package_names=["ubuntu-release-upgrade"],
            package_managers=["apt"],
        )
        with pytest.raises(HTTPException) as exc:
            await self._execute(self._session(), request)
        assert exc.value.status_code == 400
        assert "apt" in exc.value.detail

    @pytest.mark.asyncio
    async def test_an_allowlisted_package_manager_is_accepted(self):
        request = UpdateExecutionRequest(
            host_ids=[HOST_ID],
            package_names=["ubuntu-release-upgrade"],
            package_managers=["ubuntu-release"],
        )
        out, _, _ = await self._execute(self._session(), request)
        assert out["results"][0]["status"] == "success"

    @pytest.mark.asyncio
    async def test_an_inactive_or_unknown_host_is_reported_per_host(self):
        out, queued, _ = await self._execute(self._session(Host=[]))
        assert out["results"][0]["status"] == "error"
        assert "not found or inactive" in out["results"][0]["message"]
        assert queued == []

    @pytest.mark.asyncio
    async def test_an_image_mode_host_is_refused_with_an_explanation(self):
        session = self._session(Host=[_host(is_image_mode=True)])
        out, queued, _ = await self._execute(session)
        assert out["results"][0]["status"] == "error"
        assert "image-mode host" in out["results"][0]["message"]
        # Queuing apply_updates here would hang: the agent cannot satisfy it.
        assert queued == []

    @pytest.mark.asyncio
    async def test_a_host_with_nothing_to_upgrade_is_reported_distinctly(self):
        out, queued, _ = await self._execute(self._session(PackageUpdate=[]))
        # Not an error: nothing is wrong, there is simply nothing to do.
        assert out["results"][0]["status"] == "no_updates"
        assert queued == []

    @pytest.mark.asyncio
    async def test_a_queue_failure_is_reported_without_marking_progress(self):
        session = self._session()
        update = session._by_model["PackageUpdate"][0]
        out, _, audit = await self._execute(
            session, enqueue_error=RuntimeError("queue down")
        )
        assert out["results"][0]["status"] == "error"
        assert "Failed to queue" in out["results"][0]["message"]
        # Stamping updated_at on a command that never shipped would make the
        # upgrade look in-flight for ever.
        assert update.updated_at is None
        audit.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_successful_dispatch_stamps_the_upgrade_rows(self):
        session = self._session()
        update = session._by_model["PackageUpdate"][0]
        await self._execute(session)
        assert update.updated_at is not None
        assert session.commits == 1

    @pytest.mark.asyncio
    async def test_a_mixed_batch_reports_one_entry_per_host(self):
        other = str(uuid.uuid4())
        session = self._session()
        request = UpdateExecutionRequest(
            host_ids=[HOST_ID, other], package_names=["ubuntu-release-upgrade"]
        )
        out, queued, _ = await self._execute(session, request)
        assert [r["status"] for r in out["results"]] == ["success", "error"]
        assert len(queued) == 1

    @pytest.mark.asyncio
    async def test_an_unexpected_failure_is_a_500(self):
        session = self._session()
        session.query = MagicMock(side_effect=RuntimeError("db gone"))
        with pytest.raises(HTTPException) as exc:
            await self._execute(session)
        assert exc.value.status_code == 500
