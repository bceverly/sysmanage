# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Profile CRUD and assignments (Phase 20.1).

The behaviour worth pinning here is SNAPSHOT-ON-WRITE. A profile edit has to
leave behind what the profile used to contain, not what it now contains --
history whose every row is the value that replaced it looks correct until
somebody tries to restore from it. The tests below assert the direction, not
merely that a row appeared.

The other trap is that an update validates the RESULT rather than the delta.
Changing only the engine still has to be valid alongside the existing content,
and a check that looked at the changed field alone would accept a request that
produces an invalid profile.
"""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.api import config_mgmt_profiles as api
from backend.security.roles import SecurityRoles
from backend.services import config_mgmt_engines as registry
from backend.services import config_mgmt_profile_service as svc

PROFILE_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")
HOST_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
ASSIGN_ID = uuid.UUID("55555555-5555-4555-8555-555555555555")


def _matches(row, expression):
    """Evaluate a simple SQLAlchemy comparison against a plain object."""
    column = getattr(expression, "left", None)
    bound = getattr(expression, "right", None)
    name = getattr(column, "key", None)
    if name is None or not hasattr(bound, "value"):
        raise AssertionError("unsupported filter expression: %r" % (expression,))
    actual, expected = getattr(row, name), bound.value
    operator = expression.operator.__name__
    if operator == "eq":
        return actual == expected
    if operator == "ne":
        return actual != expected
    raise AssertionError("unsupported filter operator: %s" % operator)


class _Query:
    """A fake query that actually EVALUATES its criteria.

    A ``filter()`` that just returns ``self`` makes every filtering test
    vacuous -- it cannot tell "excluded the row being edited" from "forgot to".
    Unrecognised expressions raise rather than being skipped, so a new filter
    fails loudly here instead of quietly passing.
    """

    def __init__(self, rows):
        self._rows = rows
        self.ordered = False

    def filter(self, *criteria, **_k):
        for expression in criteria:
            self._rows = [r for r in self._rows if _matches(r, expression)]
        return self

    def order_by(self, *_a):
        self.ordered = True
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _Session:
    def __init__(self, **by_name):
        self._by_name = by_name
        self.added = []
        self.deleted = []
        self.commits = 0

    def query(self, entity):
        return _Query(self._by_name.get(entity.__name__, []))

    def add(self, obj):
        self.added.append(obj)

    def delete(self, obj):
        self.deleted.append(obj)

    def commit(self):
        self.commits += 1


def profile(**over):
    base = {
        "id": PROFILE_ID,
        "name": "baseline",
        "description": "hardening",
        "engine": "ansible-core",
        "content": "- hosts: all\n",
        "version": 3,
        "is_active": True,
        "created_by": "author@invalid",
        "updated_by": "editor@invalid",
        "created_at": datetime(2026, 8, 20, 9, 0, 0),
        "updated_at": datetime(2026, 8, 26, 9, 0, 0),
    }
    base.update(over)
    return SimpleNamespace(**base)


def user(*roles):
    granted = set(roles)
    return SimpleNamespace(
        userid="editor@invalid", has_role=lambda role: role in granted
    )


class _Engine:
    """Stand-in for the licensed module."""

    def __init__(self, problem=None):
        self.problem = problem
        self.validated = []

    def validate_profile(self, name, engine, content):
        self.validated.append((name, engine, content))
        # Share the real identity vocabulary. A fake that accepts any string
        # lets a fixture invent an engine name that production would reject,
        # and the test then proves nothing about the identity it used.
        if (engine or "").strip().lower() not in registry.ALL_ENGINES:
            return "unknown configuration management engine: %s" % engine
        return self.problem

    def validate_assignment(self, host_id, tag_id, site_id, schedule):
        return self.problem

    def next_version(self, current):
        return int(current) + 1

    def snapshot_of(self, prof):
        return {
            "profile_id": prof.id,
            "version": prof.version,
            "engine": prof.engine,
            "content": prof.content,
            "created_by": prof.updated_by or prof.created_by,
        }


def _with_engine(engine):
    return patch.object(svc, "_engine", lambda: engine)


class TestCreate:
    @pytest.mark.asyncio
    async def test_requires_add_script_role(self):
        with pytest.raises(HTTPException) as err:
            await api.create_profile(
                api.ProfileCreateRequest(name="n", engine="ansible-core", content="x"),
                _Session(),
                user(),
            )
        assert err.value.status_code == 403

    @pytest.mark.asyncio
    async def test_engine_rejection_becomes_400_with_the_engines_words(self):
        with _with_engine(_Engine(problem="engine 'nope' is not supported")):
            with pytest.raises(HTTPException) as err:
                await api.create_profile(
                    api.ProfileCreateRequest(name="n", engine="nope", content="x"),
                    _Session(),
                    user(SecurityRoles.ADD_SCRIPT),
                )
        assert err.value.status_code == 400
        assert "nope" in err.value.detail

    @pytest.mark.asyncio
    async def test_duplicate_name_is_409_not_a_500_from_the_unique_index(self):
        session = _Session(ConfigProfile=[profile()])
        with _with_engine(_Engine()):
            with pytest.raises(HTTPException) as err:
                await api.create_profile(
                    api.ProfileCreateRequest(
                        name="baseline", engine="ansible-core", content="x"
                    ),
                    session,
                    user(SecurityRoles.ADD_SCRIPT),
                )
        assert err.value.status_code == 409
        assert "baseline" in err.value.detail
        assert session.commits == 0

    @pytest.mark.asyncio
    async def test_stored_profile_starts_at_version_one_and_is_normalised(self):
        session = _Session()
        with _with_engine(_Engine()):
            out = await api.create_profile(
                api.ProfileCreateRequest(
                    name="  baseline  ", engine="Ansible-Core", content="x"
                ),
                session,
                user(SecurityRoles.ADD_SCRIPT),
            )
        assert out.name == "baseline"
        assert out.engine == "ansible-core"
        assert out.version == 1
        assert session.commits == 1


class TestUpdate:
    @pytest.mark.asyncio
    async def test_requires_edit_script_role(self):
        with pytest.raises(HTTPException) as err:
            await api.update_profile(
                str(PROFILE_ID),
                api.ProfileUpdateRequest(content="y"),
                _Session(ConfigProfile=[profile()]),
                user(SecurityRoles.ADD_SCRIPT),
            )
        assert err.value.status_code == 403

    @pytest.mark.asyncio
    async def test_content_change_snapshots_the_outgoing_body(self):
        # The history row must hold what the profile USED to contain.
        row = profile(content="OLD", version=3)
        session = _Session(ConfigProfile=[row])
        with _with_engine(_Engine()):
            out = await api.update_profile(
                str(PROFILE_ID),
                api.ProfileUpdateRequest(content="NEW"),
                session,
                user(SecurityRoles.EDIT_SCRIPT),
            )
        assert len(session.added) == 1
        snapshot = session.added[0]
        assert snapshot.content == "OLD"
        assert snapshot.version == 3
        assert out.content == "NEW"
        assert out.version == 4

    @pytest.mark.asyncio
    async def test_description_only_edit_does_not_burn_a_version(self):
        # Otherwise the history fills with rows nobody can tell apart.
        session = _Session(ConfigProfile=[profile(version=3)])
        with _with_engine(_Engine()):
            out = await api.update_profile(
                str(PROFILE_ID),
                api.ProfileUpdateRequest(description="new words"),
                session,
                user(SecurityRoles.EDIT_SCRIPT),
            )
        assert session.added == []
        assert out.version == 3
        assert out.description == "new words"

    @pytest.mark.asyncio
    async def test_rewriting_content_with_identical_text_is_not_a_new_version(self):
        session = _Session(ConfigProfile=[profile(content="SAME", version=3)])
        with _with_engine(_Engine()):
            out = await api.update_profile(
                str(PROFILE_ID),
                api.ProfileUpdateRequest(content="SAME"),
                session,
                user(SecurityRoles.EDIT_SCRIPT),
            )
        assert session.added == []
        assert out.version == 3

    @pytest.mark.asyncio
    async def test_engine_change_is_validated_against_existing_content(self):
        # The delta alone says nothing about whether the RESULT is valid.
        engine = _Engine()
        session = _Session(ConfigProfile=[profile(content="EXISTING")])
        with _with_engine(engine):
            await api.update_profile(
                str(PROFILE_ID),
                api.ProfileUpdateRequest(engine="salt"),
                session,
                user(SecurityRoles.EDIT_SCRIPT),
            )
        assert engine.validated == [("baseline", "salt", "EXISTING")]

    @pytest.mark.asyncio
    async def test_unset_fields_are_left_alone(self):
        session = _Session(ConfigProfile=[profile()])
        with _with_engine(_Engine()):
            out = await api.update_profile(
                str(PROFILE_ID),
                api.ProfileUpdateRequest(description="only this"),
                session,
                user(SecurityRoles.EDIT_SCRIPT),
            )
        assert out.content == "- hosts: all\n"
        assert out.engine == "ansible-core"
        assert out.name == "baseline"

    @pytest.mark.asyncio
    async def test_renaming_onto_another_profile_is_409(self):
        other = profile(id=uuid.uuid4(), name="taken")
        session = _Session(ConfigProfile=[profile(), other])
        with _with_engine(_Engine()):
            with pytest.raises(HTTPException) as err:
                await api.update_profile(
                    str(PROFILE_ID),
                    api.ProfileUpdateRequest(name="taken"),
                    session,
                    user(SecurityRoles.EDIT_SCRIPT),
                )
        assert err.value.status_code == 409

    @pytest.mark.asyncio
    async def test_renaming_a_profile_to_its_own_name_is_allowed(self):
        # The uniqueness check must exclude the row being edited or no profile
        # can ever be saved twice.
        row = profile()
        session = _Session(ConfigProfile=[row])
        with _with_engine(_Engine()):
            out = await api.update_profile(
                str(PROFILE_ID),
                api.ProfileUpdateRequest(name="baseline", description="d"),
                session,
                user(SecurityRoles.EDIT_SCRIPT),
            )
        assert out.name == "baseline"


class TestReadAndDelete:
    @pytest.mark.asyncio
    async def test_missing_profile_is_404(self):
        with pytest.raises(HTTPException) as err:
            await api.get_profile(str(PROFILE_ID), _Session())
        assert err.value.status_code == 404

    @pytest.mark.asyncio
    async def test_malformed_id_is_400_not_500(self):
        with pytest.raises(HTTPException) as err:
            await api.get_profile("not-a-uuid", _Session())
        assert err.value.status_code == 400

    @pytest.mark.asyncio
    async def test_list_is_ordered(self):
        session = _Session(ConfigProfile=[profile(), profile(id=uuid.uuid4())])
        out = await api.list_profiles(None, session)
        assert len(out) == 2

    @pytest.mark.asyncio
    async def test_naive_timestamps_come_back_marked_utc(self):
        session = _Session(ConfigProfile=[profile()])
        out = await api.list_profiles(None, session)
        assert out[0].updated_at.tzinfo is timezone.utc

    @pytest.mark.asyncio
    async def test_delete_requires_delete_script_role(self):
        with pytest.raises(HTTPException) as err:
            await api.delete_profile(
                str(PROFILE_ID),
                _Session(ConfigProfile=[profile()]),
                user(SecurityRoles.EDIT_SCRIPT),
            )
        assert err.value.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_removes_the_profile(self):
        row = profile()
        session = _Session(ConfigProfile=[row])
        out = await api.delete_profile(
            str(PROFILE_ID), session, user(SecurityRoles.DELETE_SCRIPT)
        )
        assert session.deleted == [row]
        assert out["success"] is True


class TestAssignments:
    @pytest.mark.asyncio
    async def test_engine_rejection_becomes_400(self):
        session = _Session(ConfigProfile=[profile()])
        with _with_engine(
            _Engine(problem="assign to exactly one of host, tag or site")
        ):
            with pytest.raises(HTTPException) as err:
                await api.create_assignment(
                    str(PROFILE_ID),
                    api.AssignmentCreateRequest(
                        host_id=str(HOST_ID), tag_id=str(uuid.uuid4())
                    ),
                    session,
                    user(SecurityRoles.EDIT_SCRIPT),
                )
        assert err.value.status_code == 400
        assert session.commits == 0

    @pytest.mark.asyncio
    async def test_blank_schedule_is_stored_as_null_not_empty_string(self):
        # A scheduler filtering on "schedule IS NOT NULL" would otherwise pick
        # up an unscheduled assignment and try to parse "".
        session = _Session(ConfigProfile=[profile()])
        with _with_engine(_Engine()):
            out = await api.create_assignment(
                str(PROFILE_ID),
                api.AssignmentCreateRequest(host_id=str(HOST_ID), schedule="   "),
                session,
                user(SecurityRoles.EDIT_SCRIPT),
            )
        assert out.schedule is None

    @pytest.mark.asyncio
    async def test_assignment_records_its_target(self):
        session = _Session(ConfigProfile=[profile()])
        with _with_engine(_Engine()):
            out = await api.create_assignment(
                str(PROFILE_ID),
                api.AssignmentCreateRequest(host_id=str(HOST_ID), schedule="0 3 * * *"),
                session,
                user(SecurityRoles.EDIT_SCRIPT),
            )
        assert out.host_id == str(HOST_ID)
        assert out.tag_id is None
        assert out.schedule == "0 3 * * *"

    @pytest.mark.asyncio
    async def test_deleting_a_missing_assignment_is_404(self):
        with pytest.raises(HTTPException) as err:
            await api.delete_assignment(
                str(ASSIGN_ID), _Session(), user(SecurityRoles.EDIT_SCRIPT)
            )
        assert err.value.status_code == 404


class TestEngineAbsent:
    """The router is gated on the module, but the service fails closed too."""

    def test_validation_refuses_rather_than_passing_when_engine_is_missing(self):
        with patch.object(svc, "_engine", lambda: None):
            assert svc.validate_profile("n", "ansible-core", "x") is not None
            assert svc.validate_assignment(str(HOST_ID), None, None, None) is not None


class TestEngineIdentityAgreement:
    """The identity strings must be the same word in every repository.

    The server registry, the agent registry and the licensed engine each hold
    their own list. They only work because the strings match exactly -- a
    profile stored as "ansible" instead of "ansible-core" is accepted by the
    API and then rejected by the agent at apply time, which is the worst place
    to find out.
    """

    def test_licensed_engine_accepts_every_identity_the_server_offers(self):
        from backend.licensing.module_loader import module_loader  # noqa: PLC0415

        module = module_loader.get_module("config_management_engine")
        if module is None:
            pytest.skip("licensed module not loaded in this environment")
        for engine in registry.ALL_ENGINES:
            assert module.validate_profile("n", engine, "body") is None, engine
