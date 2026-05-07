"""Unit tests for backend.licensing.migration_compat."""

from unittest.mock import MagicMock

import pytest

from backend.licensing.migration_compat import (
    ModuleIncompatibility,
    _Registry,
    check_module_compatibility,
    clear_incompatibility,
    get_current_oss_revision,
    get_incompatibilities,
    is_at_or_above,
)


class TestRegistry:
    def test_record_and_all(self):
        reg = _Registry()
        entry = ModuleIncompatibility(
            module_code="x",
            required_revision="r1",
            required_revision_human="hr1",
            current_revision="r0",
        )
        reg.record(entry)
        assert reg.all() == [entry]

    def test_record_overwrites_same_code(self):
        reg = _Registry()
        reg.record(
            ModuleIncompatibility(
                module_code="x",
                required_revision="r1",
                required_revision_human=None,
                current_revision=None,
            )
        )
        reg.record(
            ModuleIncompatibility(
                module_code="x",
                required_revision="r2",
                required_revision_human=None,
                current_revision=None,
            )
        )
        all_entries = reg.all()
        assert len(all_entries) == 1
        assert all_entries[0].required_revision == "r2"

    def test_clear(self):
        reg = _Registry()
        reg.record(
            ModuleIncompatibility(
                module_code="x",
                required_revision="r1",
                required_revision_human=None,
                current_revision=None,
            )
        )
        reg.clear("x")
        assert reg.all() == []

    def test_clear_missing_is_noop(self):
        reg = _Registry()
        reg.clear("never-recorded")
        assert reg.all() == []


class TestGetCurrentOssRevision:
    def test_returns_first_row(self):
        session = MagicMock()
        result = MagicMock()
        result.fetchall.return_value = [("v3uchildist0",)]
        session.execute.return_value = result
        assert get_current_oss_revision(session) == "v3uchildist0"

    def test_returns_none_when_empty(self):
        session = MagicMock()
        result = MagicMock()
        result.fetchall.return_value = []
        session.execute.return_value = result
        assert get_current_oss_revision(session) is None

    def test_returns_none_when_table_missing(self):
        session = MagicMock()
        session.execute.side_effect = RuntimeError("relation does not exist")
        assert get_current_oss_revision(session) is None


class TestIsAtOrAbove:
    def test_none_current_is_never_compatible(self):
        # Without a real alembic config we still expect False quickly.
        assert is_at_or_above(None, "anything", "/nonexistent.ini") is False

    def test_equal_revisions_is_compatible(self, tmp_path):
        # Equal short-circuit fires before reading alembic config.
        assert is_at_or_above("rev1", "rev1", "/nonexistent.ini") is True

    def test_unreadable_alembic_cfg_returns_false(self):
        # current != target and no readable cfg → False (fail-closed for the
        # comparison itself; the caller then fail-opens at module load time).
        assert is_at_or_above("rev1", "rev2", "/nonexistent.ini") is False

    def test_ancestor_relationship_with_real_alembic(self):
        # Use the repo's own alembic config to verify ancestor walking.
        import os

        cfg = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
        )
        if not os.path.exists(cfg):
            pytest.skip("alembic.ini not present")
        # Head is its own ancestor
        assert is_at_or_above("v3uchildist0", "v3uchildist0", cfg) is True
        # Head should be at-or-above the original child_host migration
        assert is_at_or_above("v3uchildist0", "a1c2d3e4f5g6", cfg) is True


class TestCheckModuleCompatibility:
    def test_no_min_revision_clears_and_returns_none(self):
        clear_incompatibility("test_mod")
        session = MagicMock()
        result = check_module_compatibility(
            module_code="test_mod",
            module_info={"version": "1"},
            session=session,
            alembic_cfg_path="/nonexistent.ini",
        )
        assert result is None
        assert all(e.module_code != "test_mod" for e in get_incompatibilities())

    def test_incompatible_records_entry(self):
        clear_incompatibility("test_mod")
        session = MagicMock()
        # Empty alembic_version -> current is None -> incompatible
        result_obj = MagicMock()
        result_obj.fetchall.return_value = []
        session.execute.return_value = result_obj
        result = check_module_compatibility(
            module_code="test_mod",
            module_info={
                "min_oss_alembic_revision": "needed_rev",
                "min_oss_alembic_revision_human": "human-readable",
            },
            session=session,
            alembic_cfg_path="/nonexistent.ini",
        )
        assert result is not None
        assert result.module_code == "test_mod"
        assert result.required_revision == "needed_rev"
        assert result.required_revision_human == "human-readable"
        assert result.current_revision is None
        assert any(e.module_code == "test_mod" for e in get_incompatibilities())
        clear_incompatibility("test_mod")

    def test_compatible_clears_previous_entry(self):
        # First, record an incompatibility for this module.
        clear_incompatibility("test_mod_2")
        session = MagicMock()
        result_obj = MagicMock()
        result_obj.fetchall.return_value = []
        session.execute.return_value = result_obj
        check_module_compatibility(
            module_code="test_mod_2",
            module_info={"min_oss_alembic_revision": "needed"},
            session=session,
            alembic_cfg_path="/nonexistent.ini",
        )
        assert any(e.module_code == "test_mod_2" for e in get_incompatibilities())

        # Now check with a module that doesn't declare a min — should clear.
        result = check_module_compatibility(
            module_code="test_mod_2",
            module_info={"version": "1"},
            session=session,
            alembic_cfg_path="/nonexistent.ini",
        )
        assert result is None
        assert all(e.module_code != "test_mod_2" for e in get_incompatibilities())
