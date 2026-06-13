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

    def test_loaded_config_mirrors_keys(self):
        """The live (loaded) config exposes both keys after normalization."""
        # The dev config uses ``database:``; the loader mirrors it to
        # ``registry:`` so both resolve to the same connection.
        assert config.get_registry_config() is not None
        assert config.get_registry_config() == config.get_config().get("database")
