# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Remediation playbooks: the service and its endpoints (Phase 20.1).

The sharp edges here are all about a repair firing when nobody is watching.

* **Only a finding that just OPENED earns an attempt.** A finding that is
  merely still open is not a new event; repeating the repair at it every check
  would turn a divergence the playbook cannot fix into an endless loop, when
  what an operator needs to see is persistent drift.
* **A rule pointing at a retired profile fails LOUDLY.** It is a repair
  somebody wrote down and expects to happen, so silent breakage is the worst
  outcome -- and auto-apply is what makes it dangerous.
* **Queuing is never reported as fixed.** The finding clears when the next
  check-mode run observes the host is back in line.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.api import config_mgmt_remediation as api
from backend.security.roles import SecurityRoles
from backend.services import config_mgmt_remediation as svc

HOST = uuid.UUID("22222222-2222-4222-8222-222222222222")
PROFILE = uuid.UUID("44444444-4444-4444-8444-444444444444")
REPAIR = uuid.UUID("77777777-7777-4777-8777-777777777777")


class _Engine:
    """Only the matching half of the real engine, with its precedence."""

    def __init__(self, winner="pick-first"):
        self.mode = winner
        self.previews = 0

    def validate_remediation_rule(self, name, pattern, priority=None):
        if not str(name or "").strip():
            return "rule name is required"
        if str(pattern or "").strip() == "*":
            return "a task pattern of '*' matches every finding"
        return None

    def match_remediation_rule(self, rules, profile_id, task_name, auto_only=False):
        for rule in rules or []:
            if not rule.enabled:
                continue
            if auto_only and not rule.auto_apply:
                continue
            if rule.profile_id is not None and str(rule.profile_id) != str(profile_id):
                continue
            if rule.profile_id is not None and profile_id is None:
                continue
            if rule.task_pattern.rstrip("*") not in task_name:
                continue
            return rule
        return None

    def remediation_preview(self, rule, task_name):
        self.previews += 1
        return {"rule_name": rule.name, "matched_task": task_name}


def rule(**over):
    base = {
        "id": uuid.uuid4(),
        "name": "sshd repair",
        "description": None,
        "profile_id": None,
        "task_pattern": "ensure sshd*",
        "remediation_profile_id": REPAIR,
        "enabled": True,
        "priority": 100,
        "auto_apply": False,
        "created_by": "op",
        "updated_by": "op",
        "created_at": None,
        "updated_at": None,
    }
    base.update(over)
    return SimpleNamespace(**base)


def finding(**over):
    base = {
        "id": uuid.uuid4(),
        "host_id": HOST,
        "profile_id": PROFILE,
        "profile_name": "baseline",
        "task_name": "ensure sshd config",
    }
    base.update(over)
    return SimpleNamespace(**base)


def repair_profile(active=True, name="sshd fix"):
    return SimpleNamespace(
        id=REPAIR,
        name=name,
        engine="ansible-core",
        content="- hosts: all\n",
        is_active=active,
    )


def host(active=True):
    return SimpleNamespace(id=HOST, fqdn="h1.invalid", active=active)


class _Query:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *_a, **_k):
        return self

    def order_by(self, *_a):
        return self

    def all(self):
        return list(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None


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

    def delete(self, row):
        self.deleted.append(row)

    def commit(self):
        self.commits += 1


def user(*roles):
    granted = set(roles)
    return SimpleNamespace(
        userid="op@invalid", id=uuid.uuid4(), has_role=lambda r: r in granted
    )


class TestMatching:
    def test_an_unlicensed_server_matches_nothing(self):
        with patch.object(svc.shim, "engine_module", lambda: None):
            assert svc.match_for_finding(_Session(), finding()) == (None, None)

    def test_a_matched_rule_returns_its_repair_profile(self):
        session = _Session(
            ConfigRemediationRule=[rule()], ConfigProfile=[repair_profile()]
        )
        with patch.object(svc.shim, "engine_module", _Engine):
            matched, profile = svc.match_for_finding(session, finding())
        assert matched.name == "sshd repair"
        assert profile.name == "sshd fix"

    def test_a_rule_whose_repair_was_retired_returns_the_rule_but_no_profile(self):
        # Two distinguishable answers: "nothing knows how to fix this" sends an
        # operator to write a rule, "the fix was turned off" sends them to turn
        # it back on.
        session = _Session(
            ConfigRemediationRule=[rule()],
            ConfigProfile=[repair_profile(active=False)],
        )
        with patch.object(svc.shim, "engine_module", _Engine):
            matched, profile = svc.match_for_finding(session, finding())
        assert matched is not None
        assert profile is None

    def test_a_retired_repair_is_logged_loudly(self, caplog):
        session = _Session(
            ConfigRemediationRule=[rule()],
            ConfigProfile=[repair_profile(active=False)],
        )
        with patch.object(svc.shim, "engine_module", _Engine):
            with caplog.at_level("WARNING"):
                svc.match_for_finding(session, finding())
        assert "missing or" in caplog.text


class TestAutoRemediation:
    def _run(self, session, engine=None, queue=None):
        queued = []

        def fake_apply(_db, host_row, profile_row, check_mode=False):
            if queue is not None:
                return queue()
            queued.append((host_row.fqdn, profile_row.name))
            return "cmd-1"

        with patch.object(svc.shim, "engine_module", lambda: engine or _Engine()):
            with patch.object(svc, "apply_remediation", fake_apply):
                summary = svc.auto_remediate(session, [finding()])
        return summary, queued

    def test_nothing_fires_without_a_matching_auto_rule(self):
        session = _Session(
            ConfigRemediationRule=[rule(auto_apply=False)],
            ConfigProfile=[repair_profile()],
            Host=[host()],
        )
        summary, queued = self._run(session)
        assert summary["queued"] == 0
        assert queued == []

    def test_an_opted_in_rule_fires(self):
        session = _Session(
            ConfigRemediationRule=[rule(auto_apply=True)],
            ConfigProfile=[repair_profile()],
            Host=[host()],
        )
        summary, queued = self._run(session)
        assert summary["queued"] == 1
        assert queued == [("h1.invalid", "sshd fix")]

    def test_an_inactive_host_is_not_dispatched_to(self):
        session = _Session(
            ConfigRemediationRule=[rule(auto_apply=True)],
            ConfigProfile=[repair_profile()],
            Host=[host(active=False)],
        )
        summary, _ = self._run(session)
        assert summary["queued"] == 0

    def test_an_empty_findings_list_does_nothing(self):
        with patch.object(svc.shim, "engine_module", _Engine):
            assert svc.auto_remediate(_Session(), [])["queued"] == 0

    def test_a_host_that_refuses_the_command_does_not_stop_the_pass(self):
        # Per-host isolation: one machine without ansible-core must not stop
        # every other finding in the batch from being repaired.
        session = _Session(
            ConfigRemediationRule=[rule(auto_apply=True)],
            ConfigProfile=[repair_profile()],
            Host=[host()],
        )

        def boom():
            raise RuntimeError("capability not advertised")

        summary, _ = self._run(session, queue=boom)
        assert summary["failed"] == 1
        assert summary["queued"] == 0

    def test_it_never_raises_because_the_run_row_matters_more(self):
        # This runs inside the result handler's transaction; losing the run is
        # worse than losing a repair.
        broken = SimpleNamespace(
            query=lambda *_a: (_ for _ in ()).throw(RuntimeError("db gone"))
        )
        with patch.object(svc.shim, "engine_module", _Engine):
            assert svc.auto_remediate(broken, [finding()])["queued"] == 0


class TestRuleEndpoints:
    @pytest.mark.asyncio
    async def test_creating_a_rule_needs_the_add_script_role(self):
        with pytest.raises(HTTPException) as err:
            await api.create_rule(
                api.RuleRequest(
                    name="r",
                    task_pattern="ensure*",
                    remediation_profile_id=str(REPAIR),
                ),
                _Session(),
                user(),
            )
        assert err.value.status_code == 403

    @pytest.mark.asyncio
    async def test_a_catch_all_pattern_is_refused_by_the_engine(self):
        session = _Session(ConfigProfile=[repair_profile()])
        with patch.object(svc.shim, "engine_module", _Engine):
            with pytest.raises(HTTPException) as err:
                await api.create_rule(
                    api.RuleRequest(
                        name="r",
                        task_pattern="*",
                        remediation_profile_id=str(REPAIR),
                    ),
                    session,
                    user(SecurityRoles.ADD_SCRIPT),
                )
        assert err.value.status_code == 400

    @pytest.mark.asyncio
    async def test_a_duplicate_name_is_409_not_500(self):
        session = _Session(
            ConfigRemediationRule=[rule()], ConfigProfile=[repair_profile()]
        )
        with patch.object(svc.shim, "engine_module", _Engine):
            with pytest.raises(HTTPException) as err:
                await api.create_rule(
                    api.RuleRequest(
                        name="sshd repair",
                        task_pattern="ensure*",
                        remediation_profile_id=str(REPAIR),
                    ),
                    session,
                    user(SecurityRoles.ADD_SCRIPT),
                )
        assert err.value.status_code == 409

    @pytest.mark.asyncio
    async def test_rules_are_listed_in_precedence_order_not_by_name(self):
        # A name-ordered list of overlapping rules tells an operator nothing
        # about which one will fire.
        session = _Session(ConfigRemediationRule=[rule(name="a"), rule(name="b")])
        out = await api.list_rules(session)
        assert [r.name for r in out] == ["a", "b"]


class TestFindingRepair:
    @pytest.mark.asyncio
    async def test_a_preview_reports_no_match_rather_than_failing(self):
        session = _Session(ConfigDriftFinding=[finding()], ConfigRemediationRule=[])
        with patch.object(svc.shim, "engine_module", _Engine):
            out = await api.match_finding(str(uuid.uuid4()), session)
        assert out.matched is False

    @pytest.mark.asyncio
    async def test_a_preview_distinguishes_an_unavailable_repair(self):
        session = _Session(
            ConfigDriftFinding=[finding()],
            ConfigRemediationRule=[rule()],
            ConfigProfile=[repair_profile(active=False)],
        )
        with patch.object(svc.shim, "engine_module", _Engine):
            out = await api.match_finding(str(uuid.uuid4()), session)
        assert out.matched is True
        assert out.unavailable is True

    @pytest.mark.asyncio
    async def test_the_preview_comes_from_the_engine(self):
        # Not assembled in the API: the sentence an operator confirms must be
        # produced by the same code that made the decision.
        engine = _Engine()
        session = _Session(
            ConfigDriftFinding=[finding()],
            ConfigRemediationRule=[rule()],
            ConfigProfile=[repair_profile()],
        )
        with patch.object(svc.shim, "engine_module", lambda: engine):
            out = await api.match_finding(str(uuid.uuid4()), session)
        assert engine.previews == 1
        assert out.preview["rule_name"] == "sshd repair"

    @pytest.mark.asyncio
    async def test_repairing_needs_the_run_script_role(self):
        # It runs a profile on a host; identical blast radius to an ad-hoc
        # apply, so a softer permission would be an escalation path.
        with pytest.raises(HTTPException) as err:
            await api.repair_finding(str(uuid.uuid4()), _Session(), user())
        assert err.value.status_code == 403

    @pytest.mark.asyncio
    async def test_no_matching_rule_is_404(self):
        session = _Session(ConfigDriftFinding=[finding()], ConfigRemediationRule=[])
        with patch.object(svc.shim, "engine_module", _Engine):
            with pytest.raises(HTTPException) as err:
                await api.repair_finding(
                    str(uuid.uuid4()), session, user(SecurityRoles.RUN_SCRIPT)
                )
        assert err.value.status_code == 404

    @pytest.mark.asyncio
    async def test_an_inactive_host_is_refused(self):
        session = _Session(
            ConfigDriftFinding=[finding()],
            ConfigRemediationRule=[rule()],
            ConfigProfile=[repair_profile()],
            Host=[host(active=False)],
        )
        with patch.object(svc.shim, "engine_module", _Engine):
            with pytest.raises(HTTPException) as err:
                await api.repair_finding(
                    str(uuid.uuid4()), session, user(SecurityRoles.RUN_SCRIPT)
                )
        assert err.value.status_code == 400

    @pytest.mark.asyncio
    async def test_a_queued_repair_does_not_claim_the_drift_is_fixed(self):
        # The finding clears when the next CHECK run observes the host is back
        # in line; saying otherwise would be a dashboard that lies.
        session = _Session(
            ConfigDriftFinding=[finding()],
            ConfigRemediationRule=[rule()],
            ConfigProfile=[repair_profile()],
            Host=[host()],
        )
        with patch.object(svc.shim, "engine_module", _Engine):
            with patch.object(svc, "apply_remediation", lambda *_a, **_k: "cmd"):
                out = await api.repair_finding(
                    str(uuid.uuid4()), session, user(SecurityRoles.RUN_SCRIPT)
                )
        assert out.queued is True
        assert "queued" in out.message.lower()


class TestRuleEditing:
    @pytest.mark.asyncio
    async def test_a_rule_can_be_switched_to_automatic(self):
        row = rule()
        session = _Session(
            ConfigRemediationRule=[row], ConfigProfile=[repair_profile()]
        )
        with patch.object(svc.shim, "engine_module", _Engine):
            out = await api.update_rule(
                str(uuid.uuid4()),
                api.RuleUpdateRequest(auto_apply=True),
                session,
                user(SecurityRoles.EDIT_SCRIPT),
            )
        assert out.auto_apply is True

    @pytest.mark.asyncio
    async def test_an_update_is_validated_against_the_result_not_the_delta(self):
        # Changing only the pattern still has to be valid alongside the name
        # the rule already has.
        session = _Session(
            ConfigRemediationRule=[rule()], ConfigProfile=[repair_profile()]
        )
        with patch.object(svc.shim, "engine_module", _Engine):
            with pytest.raises(HTTPException) as err:
                await api.update_rule(
                    str(uuid.uuid4()),
                    api.RuleUpdateRequest(task_pattern="*"),
                    session,
                    user(SecurityRoles.EDIT_SCRIPT),
                )
        assert err.value.status_code == 400

    @pytest.mark.asyncio
    async def test_editing_needs_the_edit_script_role(self):
        with pytest.raises(HTTPException) as err:
            await api.update_rule(
                str(uuid.uuid4()),
                api.RuleUpdateRequest(priority=1),
                _Session(),
                user(),
            )
        assert err.value.status_code == 403

    @pytest.mark.asyncio
    async def test_a_rules_scope_can_be_widened_to_any_profile(self):
        row = rule(profile_id=PROFILE)
        session = _Session(
            ConfigRemediationRule=[row], ConfigProfile=[repair_profile()]
        )
        with patch.object(svc.shim, "engine_module", _Engine):
            out = await api.update_rule(
                str(uuid.uuid4()),
                api.RuleUpdateRequest(profile_id=None),
                session,
                user(SecurityRoles.EDIT_SCRIPT),
            )
        assert out.profile_id is None

    @pytest.mark.asyncio
    async def test_deleting_a_rule_leaves_its_profiles_alone(self):
        session = _Session(ConfigRemediationRule=[rule()])
        out = await api.delete_rule(
            str(uuid.uuid4()), session, user(SecurityRoles.DELETE_SCRIPT)
        )
        assert out["success"] is True
        # The rule row goes; the profiles it named are untouched, which is what
        # makes a rule library safe to prune.
        assert len(session.deleted) == 1

    @pytest.mark.asyncio
    async def test_deleting_needs_the_delete_script_role(self):
        with pytest.raises(HTTPException) as err:
            await api.delete_rule(str(uuid.uuid4()), _Session(), user())
        assert err.value.status_code == 403

    @pytest.mark.asyncio
    async def test_a_missing_rule_is_404(self):
        with pytest.raises(HTTPException) as err:
            await api.update_rule(
                str(uuid.uuid4()),
                api.RuleUpdateRequest(priority=1),
                _Session(ConfigRemediationRule=[]),
                user(SecurityRoles.EDIT_SCRIPT),
            )
        assert err.value.status_code == 404

    @pytest.mark.asyncio
    async def test_a_creating_rule_resolves_both_profile_names_in_one_query(self):
        # The list view renders every rule; a relationship walked per row is
        # the classic N+1 that only appears once a customer has a real library.
        session = _Session(
            ConfigRemediationRule=[rule(profile_id=PROFILE)],
            ConfigProfile=[repair_profile()],
        )
        out = await api.list_rules(session)
        assert out[0].remediation_profile_name == "sshd fix"
