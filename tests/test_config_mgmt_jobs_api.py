# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Inventory, job-template and fleet-job endpoints (Phase 20.1).

Launching is the sharp edge: it runs executable content on every host an
inventory names, so the rules pinned here are the ones that stop it doing that
by accident.

* **Launch is RUN_SCRIPT.** The same permission as applying a profile to one
  host, because it is that operation with a larger blast radius rather than a
  different one.
* **A retired profile is never re-imposed**, by launch any more than by
  remediation.
* **Concurrency is CLAMPED, not rejected.** An operator who types 10,000 means
  "as fast as possible", and the stored value shows them what they got.
* **An inventory in use cannot be deleted**, because the foreign key is
  CASCADE and allowing it would silently take every template built on it --
  and their schedules with them.
"""

import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.api import config_mgmt_inventories as inv_api
from backend.api import config_mgmt_jobs as api
from backend.security.roles import SecurityRoles
from backend.services import config_mgmt_fleet as fleet

INV = uuid.UUID("55555555-5555-4555-8555-555555555555")
PROFILE = uuid.UUID("44444444-4444-4444-8444-444444444444")
TEMPLATE = uuid.UUID("88888888-8888-4888-8888-888888888888")
JOB = uuid.UUID("66666666-6666-4666-8666-666666666666")


class _Engine:
    def validate_inventory(self, name, all_hosts, member_count):
        if not str(name or "").strip():
            return "inventory name is required"
        if not all_hosts and not member_count:
            return "an inventory needs at least one host, tag or site"
        return None

    def validate_inventory_member(self, host_id, tag_id, site_id):
        targets = [t for t in (host_id, tag_id, site_id) if t]
        return None if len(targets) == 1 else "exactly one target"

    def validate_job_template(self, name, profile_id, inventory_id, schedule=None):
        if not str(name or "").strip():
            return "job template name is required"
        if not profile_id or not inventory_id:
            return "a job template needs a profile and an inventory"
        if schedule and len(str(schedule).split()) != 5:
            return "invalid cron expression"
        return None

    def clamp_concurrency(self, value):
        return 20 if value is None else max(1, min(500, int(value)))

    def clamp_timeout(self, value):
        return None if value is None else max(60, min(21600, int(value)))

    def job_is_terminal(self, status):
        return status in ("completed", "failed", "canceled")

    def inventory_selectors(self, inventory, _members):
        return {
            "all_hosts": bool(inventory.all_hosts),
            "host_ids": [],
            "tag_ids": [],
            "site_ids": [],
        }


class _Query:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *_a, **_k):
        return self

    def order_by(self, *_a):
        return self

    def limit(self, _n):
        return self

    def offset(self, _n):
        return self

    def all(self):
        return list(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None

    def count(self):
        return len(self.rows)


class _Session:
    def __init__(self, **by_name):
        self._by_name = by_name
        self.commits = 0
        self.added = []
        self.deleted = []

    def query(self, entity, *_rest):
        return _Query(self._by_name.get(getattr(entity, "__name__", ""), []))

    def add(self, row):
        self.added.append(row)

    def flush(self):
        pass

    def delete(self, row):
        self.deleted.append(row)

    def commit(self):
        self.commits += 1


def user(*roles):
    granted = set(roles)
    return SimpleNamespace(
        userid="op@invalid", id=uuid.uuid4(), has_role=lambda r: r in granted
    )


def inventory(**over):
    base = {
        "id": INV,
        "name": "web tier",
        "description": None,
        "all_hosts": False,
        "created_by": "op",
        "updated_by": "op",
        "created_at": None,
        "updated_at": None,
    }
    base.update(over)
    return SimpleNamespace(**base)


def profile(active=True):
    return SimpleNamespace(
        id=PROFILE,
        name="baseline",
        engine="ansible-core",
        content="- hosts: all\n",
        is_active=active,
    )


def template(**over):
    base = {
        "id": TEMPLATE,
        "name": "nightly baseline",
        "description": None,
        "profile_id": PROFILE,
        "inventory_id": INV,
        "check_mode": True,
        "concurrency": 20,
        "timeout_seconds": None,
        "schedule": "0 3 * * *",
        "enabled": True,
        "created_by": "op",
        "updated_by": "op",
        "created_at": None,
        "updated_at": None,
        "last_launched_at": None,
    }
    base.update(over)
    return SimpleNamespace(**base)


def job_row(**over):
    base = {
        "id": JOB,
        "template_id": TEMPLATE,
        "template_name": "nightly baseline",
        "profile_id": PROFILE,
        "profile_name": "baseline",
        "inventory_name": "web tier",
        "status": "running",
        "check_mode": True,
        "concurrency": 20,
        "total_targets": 10,
        "succeeded_count": 4,
        "failed_count": 1,
        "skipped_count": 0,
        "requested_by": "op",
        "detail": None,
        "created_at": None,
        "started_at": None,
        "finished_at": None,
    }
    base.update(over)
    return SimpleNamespace(**base)


def _engine():
    return patch.object(fleet.shim, "engine_module", _Engine)


class TestInventories:
    @pytest.mark.asyncio
    async def test_creating_needs_the_add_script_role(self):
        with pytest.raises(HTTPException) as err:
            await inv_api.create_inventory(
                inv_api.InventoryRequest(name="x"), _Session(), user()
            )
        assert err.value.status_code == 403

    @pytest.mark.asyncio
    async def test_a_brand_new_inventory_may_be_empty(self):
        # Refusing an empty one at creation would make a multi-tag inventory
        # impossible to build -- there would be no valid first step.
        with _engine():
            out = await inv_api.create_inventory(
                inv_api.InventoryRequest(name="web tier"),
                _Session(),
                user(SecurityRoles.ADD_SCRIPT),
            )
        assert out.name == "web tier"
        assert out.host_count == 0

    @pytest.mark.asyncio
    async def test_a_nameless_inventory_is_refused(self):
        with _engine():
            with pytest.raises(HTTPException) as err:
                await inv_api.create_inventory(
                    inv_api.InventoryRequest(name="   "),
                    _Session(),
                    user(SecurityRoles.ADD_SCRIPT),
                )
        assert err.value.status_code == 400

    @pytest.mark.asyncio
    async def test_a_duplicate_name_is_409(self):
        session = _Session(ConfigInventory=[inventory()])
        with _engine():
            with pytest.raises(HTTPException) as err:
                await inv_api.create_inventory(
                    inv_api.InventoryRequest(name="web tier"),
                    session,
                    user(SecurityRoles.ADD_SCRIPT),
                )
        assert err.value.status_code == 409

    @pytest.mark.asyncio
    async def test_an_inventory_in_use_cannot_be_deleted(self):
        # The FK is CASCADE; allowing this would silently delete every
        # template built on it, and their schedules would stop firing with
        # nothing to show for it.
        session = _Session(
            ConfigInventory=[inventory()], ConfigJobTemplate=[template()]
        )
        with pytest.raises(HTTPException) as err:
            await inv_api.delete_inventory(
                str(INV), session, user(SecurityRoles.DELETE_SCRIPT)
            )
        assert err.value.status_code == 409

    @pytest.mark.asyncio
    async def test_an_unused_inventory_deletes(self):
        session = _Session(ConfigInventory=[inventory()], ConfigJobTemplate=[])
        out = await inv_api.delete_inventory(
            str(INV), session, user(SecurityRoles.DELETE_SCRIPT)
        )
        assert out["success"] is True
        assert session.deleted

    @pytest.mark.asyncio
    async def test_a_member_needs_exactly_one_target(self):
        session = _Session(ConfigInventory=[inventory()])
        with _engine():
            with pytest.raises(HTTPException) as err:
                await inv_api.add_member(
                    str(INV),
                    inv_api.MemberRequest(
                        host_id=str(uuid.uuid4()), tag_id=str(uuid.uuid4())
                    ),
                    session,
                    user(SecurityRoles.EDIT_SCRIPT),
                )
        assert err.value.status_code == 400

    @pytest.mark.asyncio
    async def test_a_malformed_id_is_400_not_500(self):
        with pytest.raises(HTTPException) as err:
            await inv_api.get_inventory("not-a-uuid", _Session())
        assert err.value.status_code == 400

    @pytest.mark.asyncio
    async def test_the_preview_answers_who_am_i_about_to_change(self):
        # The reason resolution is never cached: this is the question an
        # operator needs answered before launching at four thousand machines.
        hosts = [
            SimpleNamespace(id=uuid.uuid4(), fqdn="b.invalid"),
            SimpleNamespace(id=uuid.uuid4(), fqdn="a.invalid"),
        ]
        session = _Session(ConfigInventory=[inventory(all_hosts=True)])
        with _engine():
            with patch.object(fleet, "resolve_hosts", lambda *_a: hosts):
                out = await inv_api.preview_inventory(str(INV), session)
        assert out == ["a.invalid", "b.invalid"]


class TestJobTemplates:
    @pytest.mark.asyncio
    async def test_an_absurd_concurrency_is_clamped_rather_than_rejected(self):
        session = _Session(ConfigProfile=[profile()], ConfigInventory=[inventory()])
        with _engine():
            out = await api.create_template(
                api.TemplateRequest(
                    name="t",
                    profile_id=str(PROFILE),
                    inventory_id=str(INV),
                    concurrency=100000,
                ),
                session,
                user(SecurityRoles.ADD_SCRIPT),
            )
        assert out.concurrency == 500

    @pytest.mark.asyncio
    async def test_an_unspecified_concurrency_gets_the_default(self):
        session = _Session(ConfigProfile=[profile()], ConfigInventory=[inventory()])
        with _engine():
            out = await api.create_template(
                api.TemplateRequest(
                    name="t", profile_id=str(PROFILE), inventory_id=str(INV)
                ),
                session,
                user(SecurityRoles.ADD_SCRIPT),
            )
        assert out.concurrency == 20

    @pytest.mark.asyncio
    async def test_a_bad_cron_is_refused(self):
        session = _Session(ConfigProfile=[profile()], ConfigInventory=[inventory()])
        with _engine():
            with pytest.raises(HTTPException) as err:
                await api.create_template(
                    api.TemplateRequest(
                        name="t",
                        profile_id=str(PROFILE),
                        inventory_id=str(INV),
                        schedule="whenever",
                    ),
                    session,
                    user(SecurityRoles.ADD_SCRIPT),
                )
        assert err.value.status_code == 400

    @pytest.mark.asyncio
    async def test_a_template_naming_a_missing_profile_is_404(self):
        session = _Session(ConfigProfile=[], ConfigInventory=[inventory()])
        with _engine():
            with pytest.raises(HTTPException) as err:
                await api.create_template(
                    api.TemplateRequest(
                        name="t", profile_id=str(PROFILE), inventory_id=str(INV)
                    ),
                    session,
                    user(SecurityRoles.ADD_SCRIPT),
                )
        assert err.value.status_code == 404

    @pytest.mark.asyncio
    async def test_creating_needs_the_add_script_role(self):
        with pytest.raises(HTTPException) as err:
            await api.create_template(
                api.TemplateRequest(
                    name="t", profile_id=str(PROFILE), inventory_id=str(INV)
                ),
                _Session(),
                user(),
            )
        assert err.value.status_code == 403


class TestLaunch:
    @pytest.mark.asyncio
    async def test_launching_needs_the_run_script_role(self):
        # Not EDIT_SCRIPT: launching runs executable content on every host the
        # inventory names.
        with pytest.raises(HTTPException) as err:
            await api.launch_template(
                str(TEMPLATE), _Session(), user(SecurityRoles.EDIT_SCRIPT)
            )
        assert err.value.status_code == 403

    @pytest.mark.asyncio
    async def test_a_retired_profile_is_not_relaunched(self):
        session = _Session(
            ConfigJobTemplate=[template()],
            ConfigProfile=[profile(active=False)],
            ConfigInventory=[inventory()],
        )
        with pytest.raises(HTTPException) as err:
            await api.launch_template(
                str(TEMPLATE), session, user(SecurityRoles.RUN_SCRIPT)
            )
        assert err.value.status_code == 400

    @pytest.mark.asyncio
    async def test_the_first_wave_goes_out_before_the_response_returns(self):
        # A job sitting at zero for up to a minute reads as a broken button,
        # and the first thing an operator does is press it again.
        session = _Session(
            ConfigJobTemplate=[template()],
            ConfigProfile=[profile()],
            ConfigInventory=[inventory()],
        )
        created = job_row(total_targets=3, status="pending")
        advanced = []
        with patch.object(api.runner, "create_job", lambda *_a: created):
            with patch.object(
                api.runner, "advance_job", lambda _s, j: advanced.append(j)
            ):
                out = await api.launch_template(
                    str(TEMPLATE), session, user(SecurityRoles.RUN_SCRIPT)
                )
        assert advanced == [created]
        assert out.total_targets == 3

    @pytest.mark.asyncio
    async def test_launching_stamps_the_schedule_anchor(self):
        # last_launched_at is what derives due-ness; leaving it would make a
        # scheduled template fire again on the very next tick.
        tmpl = template()
        session = _Session(
            ConfigJobTemplate=[tmpl],
            ConfigProfile=[profile()],
            ConfigInventory=[inventory()],
        )
        stamp = datetime(2026, 8, 30, 3, 0, 0)
        created = job_row(created_at=stamp)
        with patch.object(api.runner, "create_job", lambda *_a: created):
            with patch.object(api.runner, "advance_job", lambda *_a: None):
                await api.launch_template(
                    str(TEMPLATE), session, user(SecurityRoles.RUN_SCRIPT)
                )
        assert tmpl.last_launched_at == stamp


class TestJobViews:
    @pytest.mark.asyncio
    async def test_a_job_reports_what_is_left_to_do(self):
        session = _Session(ConfigJob=[job_row()])
        out = await api.get_job(str(JOB), session)
        assert out.outstanding_count == 5

    @pytest.mark.asyncio
    async def test_a_missing_job_is_404(self):
        with pytest.raises(HTTPException) as err:
            await api.get_job(str(JOB), _Session(ConfigJob=[]))
        assert err.value.status_code == 404

    def test_failed_sorts_ahead_of_every_other_target_status(self):
        # The endpoint orders by status IN SQL, relying on "failed" coming
        # first alphabetically. That is lucky rather than obvious, so it is
        # pinned here: the question an operator opens this page with is "which
        # ones went wrong", and hostname order buries twelve failures among
        # four thousand successes. If a status is ever added that sorts ahead
        # of "failed", this fails and the ORDER BY needs a CASE.
        from backend.persistence.models import config_fleet as cf

        statuses = sorted(
            (
                cf.TARGET_PENDING,
                cf.TARGET_QUEUED,
                cf.TARGET_SUCCEEDED,
                cf.TARGET_FAILED,
                cf.TARGET_SKIPPED,
            )
        )
        assert statuses[0] == cf.TARGET_FAILED

    @pytest.mark.asyncio
    async def test_targets_are_listed_for_a_job(self):
        targets = [
            SimpleNamespace(
                id=uuid.uuid4(),
                job_id=JOB,
                host_id=uuid.uuid4(),
                host_fqdn=f"{n}.invalid",
                status=s,
                command_id=None,
                run_id=None,
                detail=None,
                queued_at=None,
                finished_at=None,
            )
            for n, s in (("a", "succeeded"), ("b", "failed"))
        ]
        session = _Session(ConfigJob=[job_row()], ConfigJobTarget=targets)
        out = await api.list_job_targets(str(JOB), None, 100, 0, session)
        assert {t.host_fqdn for t in out} == {"a.invalid", "b.invalid"}


class TestCancel:
    @pytest.mark.asyncio
    async def test_cancelling_needs_the_run_script_role(self):
        with pytest.raises(HTTPException) as err:
            await api.cancel_job(
                str(JOB),
                api.CancelRequest(),
                _Session(),
                user(SecurityRoles.EDIT_SCRIPT),
            )
        assert err.value.status_code == 403

    @pytest.mark.asyncio
    async def test_a_finished_job_cannot_be_cancelled(self):
        session = _Session(ConfigJob=[job_row(status="completed")])
        with _engine():
            with pytest.raises(HTTPException) as err:
                await api.cancel_job(
                    str(JOB),
                    api.CancelRequest(),
                    session,
                    user(SecurityRoles.RUN_SCRIPT),
                )
        assert err.value.status_code == 400

    @pytest.mark.asyncio
    async def test_the_reason_is_recorded_on_the_job(self):
        row = job_row()
        session = _Session(ConfigJob=[row])
        with _engine():
            with patch.object(
                api.runner,
                "cancel_job",
                lambda _s, j, reason: setattr(j, "detail", reason) or 0,
            ):
                await api.cancel_job(
                    str(JOB),
                    api.CancelRequest(reason="wrong inventory"),
                    session,
                    user(SecurityRoles.RUN_SCRIPT),
                )
        assert row.detail == "wrong inventory"


class TestInventoryEditing:
    @pytest.mark.asyncio
    async def test_the_list_resolves_a_live_host_count_per_row(self):
        # Never a cached column: the number changes whenever a host is tagged
        # or retired, and a stale count on a launch screen misleads.
        session = _Session(
            ConfigInventory=[inventory(all_hosts=True)],
            Host=[SimpleNamespace(id=uuid.uuid4(), fqdn="a.invalid", site_id=None)],
        )
        with _engine():
            out = await inv_api.list_inventories(session)
        assert out[0].host_count == 1

    @pytest.mark.asyncio
    async def test_an_update_is_validated_against_the_result_not_the_delta(self):
        # Clearing all_hosts on an inventory with no members would leave one
        # that selects nothing, which the engine refuses.
        session = _Session(
            ConfigInventory=[inventory(all_hosts=True)],
            ConfigInventoryMember=[],
        )
        with _engine():
            with pytest.raises(HTTPException) as err:
                await inv_api.update_inventory(
                    str(INV),
                    inv_api.InventoryUpdateRequest(all_hosts=False),
                    session,
                    user(SecurityRoles.EDIT_SCRIPT),
                )
        assert err.value.status_code == 400

    @pytest.mark.asyncio
    async def test_a_rename_that_collides_is_409(self):
        session = _Session(ConfigInventory=[inventory(all_hosts=True)])
        with _engine():
            with pytest.raises(HTTPException) as err:
                await inv_api.update_inventory(
                    str(INV),
                    inv_api.InventoryUpdateRequest(name="web tier"),
                    session,
                    user(SecurityRoles.EDIT_SCRIPT),
                )
        assert err.value.status_code == 409

    @pytest.mark.asyncio
    async def test_editing_needs_the_edit_script_role(self):
        with pytest.raises(HTTPException) as err:
            await inv_api.update_inventory(
                str(INV), inv_api.InventoryUpdateRequest(name="x"), _Session(), user()
            )
        assert err.value.status_code == 403

    @pytest.mark.asyncio
    async def test_a_member_is_added_with_exactly_one_target(self):
        session = _Session(ConfigInventory=[inventory()])
        host_id = str(uuid.uuid4())
        with _engine():
            out = await inv_api.add_member(
                str(INV),
                inv_api.MemberRequest(host_id=host_id),
                session,
                user(SecurityRoles.EDIT_SCRIPT),
            )
        assert out.host_id == host_id
        assert out.tag_id is None

    @pytest.mark.asyncio
    async def test_members_are_listed_for_an_inventory(self):
        member = SimpleNamespace(
            id=uuid.uuid4(),
            inventory_id=INV,
            host_id=uuid.uuid4(),
            tag_id=None,
            site_id=None,
            created_at=None,
        )
        session = _Session(
            ConfigInventory=[inventory()], ConfigInventoryMember=[member]
        )
        out = await inv_api.list_members(str(INV), session)
        assert len(out) == 1

    @pytest.mark.asyncio
    async def test_removing_a_missing_member_is_404_not_a_silent_success(self):
        with pytest.raises(HTTPException) as err:
            await inv_api.delete_member(
                str(uuid.uuid4()), _Session(), user(SecurityRoles.EDIT_SCRIPT)
            )
        assert err.value.status_code == 404


class TestTemplateEditing:
    @pytest.mark.asyncio
    async def test_templates_are_listed(self):
        session = _Session(ConfigJobTemplate=[template()])
        out = await api.list_templates(session)
        assert out[0].name == "nightly baseline"

    @pytest.mark.asyncio
    async def test_one_template_is_fetchable(self):
        session = _Session(ConfigJobTemplate=[template()])
        out = await api.get_template(str(TEMPLATE), session)
        assert out.id == str(TEMPLATE)

    @pytest.mark.asyncio
    async def test_an_update_reclamps_the_concurrency(self):
        row = template()
        session = _Session(ConfigJobTemplate=[row])
        with _engine():
            out = await api.update_template(
                str(TEMPLATE),
                api.TemplateUpdateRequest(concurrency=99999),
                session,
                user(SecurityRoles.EDIT_SCRIPT),
            )
        assert out.concurrency == 500

    @pytest.mark.asyncio
    async def test_an_update_to_a_bad_cron_is_refused(self):
        session = _Session(ConfigJobTemplate=[template()])
        with _engine():
            with pytest.raises(HTTPException) as err:
                await api.update_template(
                    str(TEMPLATE),
                    api.TemplateUpdateRequest(schedule="nightly please"),
                    session,
                    user(SecurityRoles.EDIT_SCRIPT),
                )
        assert err.value.status_code == 400

    @pytest.mark.asyncio
    async def test_deleting_a_template_leaves_its_job_history(self):
        # config_job.template_id is ON DELETE SET NULL and the name is
        # denormalised onto every job, so the record that a fleet-wide change
        # happened stays readable.
        session = _Session(ConfigJobTemplate=[template()])
        out = await api.delete_template(
            str(TEMPLATE), session, user(SecurityRoles.DELETE_SCRIPT)
        )
        assert out["success"] is True
        assert session.deleted

    @pytest.mark.asyncio
    async def test_deleting_needs_the_delete_script_role(self):
        with pytest.raises(HTTPException) as err:
            await api.delete_template(str(TEMPLATE), _Session(), user())
        assert err.value.status_code == 403

    @pytest.mark.asyncio
    async def test_jobs_can_be_filtered_by_status(self):
        session = _Session(ConfigJob=[job_row()])
        out = await api.list_jobs("running", 25, session)
        assert len(out) == 1
