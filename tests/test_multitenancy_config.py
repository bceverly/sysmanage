"""
Tests for the multi-tenancy config accessors — Phase 13.1.A.

Covers the default-off ``multitenancy.enabled`` toggle and the
``registry:`` / ``database:`` alias-and-deprecate behavior.
"""

from unittest.mock import patch

from backend.config import config


class TestMultitenancyToggle:
    def test_disabled_by_default(self):
        """Absent block → multi-tenancy is off (homelab default)."""
        with patch.object(config, "config", {}):
            assert config.is_multitenancy_enabled() is False

    def test_disabled_when_explicitly_false(self):
        with patch.object(config, "config", {"multitenancy": {"enabled": False}}):
            assert config.is_multitenancy_enabled() is False

    def test_enabled_when_set(self):
        with patch.object(config, "config", {"multitenancy": {"enabled": True}}):
            assert config.is_multitenancy_enabled() is True


class TestRegistryAlias:
    def test_prefers_registry_block(self):
        cfg = {"registry": {"name": "reg"}, "database": {"name": "legacy"}}
        with patch.object(config, "config", cfg):
            assert config.get_registry_config() == {"name": "reg"}

    def test_falls_back_to_database_block(self):
        """Legacy ``database:``-only config is still honored."""
        cfg = {"database": {"name": "legacy"}}
        with patch.object(config, "config", cfg):
            assert config.get_registry_config() == {"name": "legacy"}

    def test_registry_and_database_mirror_each_other(self):
        """After load-time normalization both keys point at the same block, and
        get_registry_config prefers ``registry``.

        Uses a controlled config rather than the live module global so the test
        is robust under the parallel suite (other tests patch ``config.config``,
        which would otherwise perturb a read of the live singleton).
        """
        block = {"name": "sysmanage", "host": "db", "user": "sysmanage"}
        with patch.object(config, "config", {"registry": block, "database": block}):
            assert config.get_registry_config() is block
            assert config.get_config().get("database") is block
