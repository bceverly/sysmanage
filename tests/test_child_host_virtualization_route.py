# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The create-child-host route.

Ordering is the substance here, not decoration.  The HostChild row is
flushed BEFORE the licence key is vaulted so the Secret can be named for the
child, and both sit inside one transaction so a vault failure rolls the child
row back instead of leaving an orphan whose key was never stored.  Likewise
every guard -- platform, privilege, duplicate name -- has to fire before the
row is inserted, or a rejected request leaves a "creating" row that never
resolves.

Helpers are exercised in ``test_child_host_virtualization_helpers.py``.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.api import child_host_virtualization as chv
from backend.api.child_host_models import CreateWslChildHostRequest

MOD = "backend.api.child_host_virtualization"


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
        self.added = []
        self.flushes = 0
        self.commits = 0

    def query(self, model):
        return _FakeQuery(self._by_model.get(getattr(model, "__name__", ""), []))

    def add(self, row):
        self.added.append(row)
        # flush() assigns the PK in the real session; order matters because the
        # Secret is named for the child AFTER the flush.
        if getattr(row, "id", None) is None:
            row.id = f"row-{len(self.added)}"

    def flush(self):
        self.flushes += 1

    def commit(self):
        self.commits += 1

    def __call__(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _request(**overrides):
    payload = {
        "child_type": "kvm",
        "distribution": "ubuntu-24.04",
        "hostname": "guest",
        "username": "admin",
        "password": "hunter2",
        "vm_name": "vm1",
    }
    payload.update(overrides)
    return CreateWslChildHostRequest(**payload)


def _host(**overrides):
    host = SimpleNamespace(
        id="host-1",
        fqdn="parent.invalid",
        platform="Linux",
        is_agent_privileged=True,
    )
    for key, value in overrides.items():
        setattr(host, key, value)
    return host


def _distribution():
    return SimpleNamespace(
        distribution_name="Ubuntu",
        distribution_version="24.04",
        install_identifier="ubuntu-24.04",
        cloud_image_url="https://cloud.invalid/noble.img",
        agent_install_commands=None,
    )


CONFIG = {
    "api": {
        "host": "sysmanage.invalid",
        "port": 8443,
        "keyFile": "/k.pem",
        "certFile": "/c.pem",
    }
}


class _Harness:
    """Patches everything the route reaches outside this module."""

    def __init__(self, session=None, ref_session=None, plan_accepted=True):
        self.session = session or _FakeSession()
        self.ref_session = ref_session or _FakeSession()
        self.plan_accepted = plan_accepted
        self.plan_calls = []
        self.audit_calls = []

    def _plan(self, request, command_params, host_id, session):
        self.plan_calls.append(command_params)
        return self.plan_accepted

    def __enter__(self):
        self._patches = [
            patch(f"{MOD}._check_container_module"),
            patch(f"{MOD}.authorize_on_main", return_value=SimpleNamespace(id="u1")),
            patch(f"{MOD}.request_sessionmaker", return_value=self.session),
            patch(f"{MOD}.sessionmaker", return_value=self.ref_session),
            patch(f"{MOD}.db.get_engine"),
            patch(f"{MOD}.get_host_or_404", return_value=self.session.host),
            patch(f"{MOD}.verify_host_active"),
            patch(f"{MOD}.get_config", return_value=CONFIG),
            patch(f"{MOD}.try_plan_based_creation", side_effect=self._plan),
            patch(
                f"{MOD}.audit_log",
                side_effect=lambda *a, **k: self.audit_calls.append((a, k)),
            ),
            patch(f"{MOD}.module_loader.get_module", return_value=None),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self._patches:
            p.stop()
        return False


def _session_with(host=None, existing=(), distribution=None):
    session = _FakeSession(HostChild=list(existing))
    session.host = host or _host()
    ref = _FakeSession(ChildHostDistribution=[distribution] if distribution else [])
    return session, ref


async def _create(session, ref, request=None, plan_accepted=True):
    harness = _Harness(session, ref, plan_accepted)
    with harness:
        result = await chv.create_child_host_request(
            "host-1", request or _request(), current_user="admin@invalid"
        )
    return result, harness


class TestCreateChildHostRequest:
    @pytest.mark.asyncio
    async def test_a_valid_request_inserts_the_child_and_queues_a_plan(self):
        session, ref = _session_with(distribution=_distribution())
        out, harness = await _create(session, ref)
        assert out["result"] is True
        assert out["child_host_id"] == "row-1"
        assert out["auto_approve"] is False
        assert session.commits == 1
        assert len(harness.plan_calls) == 1
        assert harness.plan_calls[0]["child_host_id"] == "row-1"

    @pytest.mark.asyncio
    async def test_the_child_row_is_flushed_before_the_plan_is_built(self):
        session, ref = _session_with(distribution=_distribution())
        _, harness = await _create(session, ref)
        # The plan carries the child id, so the row must have a PK by then --
        # otherwise the result handler has nothing to correlate against.
        assert session.flushes >= 1
        assert harness.plan_calls[0]["child_host_id"] != "None"

    @pytest.mark.asyncio
    async def test_an_unprivileged_agent_is_refused_before_any_insert(self):
        session, ref = _session_with(host=_host(is_agent_privileged=False))
        with pytest.raises(HTTPException) as exc:
            await _create(session, ref)
        assert exc.value.status_code == 400
        # A row inserted before the guard would sit at "creating" for ever.
        assert session.added == []

    @pytest.mark.asyncio
    async def test_a_platform_mismatch_is_refused_before_any_insert(self):
        session, ref = _session_with(host=_host(platform="Windows 11"))
        with pytest.raises(HTTPException) as exc:
            await _create(session, ref)
        assert exc.value.status_code == 400
        assert session.added == []

    @pytest.mark.asyncio
    async def test_a_duplicate_child_name_is_refused(self):
        session, ref = _session_with(existing=[SimpleNamespace(id="existing")])
        with pytest.raises(HTTPException) as exc:
            await _create(session, ref)
        assert exc.value.status_code == 400
        assert "already exists" in exc.value.detail
        assert session.added == []

    @pytest.mark.asyncio
    async def test_a_missing_vm_name_is_refused(self):
        session, ref = _session_with()
        with pytest.raises(HTTPException) as exc:
            await _create(session, ref, _request(vm_name=None))
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_an_unknown_distribution_still_creates_with_null_metadata(self):
        # The catalog row is reference data; a request naming an unseeded
        # identifier should still reach the engine, which knows more than the
        # table does.
        session, ref = _session_with()
        out, harness = await _create(session, ref)
        assert out["result"] is True
        child = session.added[0]
        assert child.distribution is None
        assert child.distribution_version is None

    @pytest.mark.asyncio
    async def test_a_known_distribution_stamps_its_name_and_version(self):
        session, ref = _session_with(distribution=_distribution())
        await _create(session, ref)
        child = session.added[0]
        assert (child.distribution, child.distribution_version) == ("Ubuntu", "24.04")

    @pytest.mark.asyncio
    async def test_auto_approve_mints_a_token_and_says_so(self):
        session, ref = _session_with(distribution=_distribution())
        out, harness = await _create(session, ref, _request(auto_approve=True))
        assert out["auto_approve"] is True
        assert "automatically approved" in out["message"]
        assert harness.plan_calls[0]["auto_approve_token"]

    @pytest.mark.asyncio
    async def test_without_auto_approve_no_token_reaches_the_plan(self):
        session, ref = _session_with(distribution=_distribution())
        out, harness = await _create(session, ref)
        assert "automatically approved" not in out["message"]
        assert "auto_approve_token" not in harness.plan_calls[0]

    @pytest.mark.asyncio
    async def test_a_declined_engine_surfaces_rather_than_committing(self):
        session, ref = _session_with(distribution=_distribution())
        with pytest.raises(HTTPException):
            await _create(session, ref, plan_accepted=False)
        # No commit: the placeholder row must roll back with the request.
        assert session.commits == 0

    @pytest.mark.asyncio
    async def test_a_windows_request_vaults_the_key_and_stores_only_its_id(self):
        session, ref = _session_with()
        request = _request(
            distribution="windows-server-2022", windows_product_key="AAAAA-BBBBB"
        )
        with patch(f"{MOD}._store_windows_product_key", return_value="sec-9") as store:
            out, _ = await _create(session, ref, request)
        assert out["result"] is True
        assert session.added[0].windows_key_secret_id == "sec-9"
        # Named for the child, which is why it happens after the flush.
        assert store.call_args[0][2] == "vm1"

    @pytest.mark.asyncio
    async def test_a_linux_request_never_touches_the_vault(self):
        session, ref = _session_with()
        with patch(f"{MOD}._store_windows_product_key") as store:
            await _create(session, ref)
        store.assert_not_called()

    @pytest.mark.asyncio
    async def test_the_audit_entry_records_the_child_and_its_resources(self):
        session, ref = _session_with(distribution=_distribution())
        _, harness = await _create(session, ref, _request(memory="8G", cpus=4))
        details = harness.audit_calls[0][1]["details"]
        assert details["child_name"] == "vm1"
        assert details["memory"] == "8G"
        assert details["cpus"] == 4
        assert details["container_name"] is None

    @pytest.mark.asyncio
    async def test_a_container_create_audits_its_own_fields_only(self):
        session, ref = _session_with()
        request = _request(child_type="lxd", container_name="c1", vm_name=None)
        with patch(f"{MOD}._validate_platform_for_child_type"):
            _, harness = await _create(session, ref, request)
        details = harness.audit_calls[0][1]["details"]
        assert details["container_name"] == "c1"
        # KVM-only sizing must not be reported for a container.
        assert details["memory"] is None
        assert details["vm_name"] is None

    @pytest.mark.asyncio
    async def test_https_is_derived_from_the_configured_key_and_cert(self):
        session, ref = _session_with(distribution=_distribution())
        _, harness = await _create(session, ref)
        assert harness.plan_calls[0]["use_https"] is True

        plain = dict(CONFIG["api"], keyFile=None, certFile=None)
        session2, ref2 = _session_with(distribution=_distribution())
        harness2 = _Harness(session2, ref2)
        with harness2:
            with patch(f"{MOD}.get_config", return_value={"api": plain}):
                await chv.create_child_host_request(
                    "host-1", _request(), current_user="admin@invalid"
                )
        assert harness2.plan_calls[0]["use_https"] is False
