# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The OSS-to-Pro+ shim for config-management specs (Phase 20.1).

The property worth defending is that "not licensed" and "not loaded" stay
DISTINGUISHABLE. They look identical to a user and mean opposite things to an
operator: the first is a sales conversation, the second is a broken install --
usually a module with no build for this Python version on the licence server.
Collapsing them sends people to the wrong place.
"""

from unittest.mock import patch

from backend.services import config_mgmt_spec_shim as shim

MOD = "backend.services.config_mgmt_spec_shim"
SPEC = {"engine": "puppet", "argv": ["puppet", "apply"]}


class _Engine:
    def __init__(self, spec=SPEC, raises=None):
        self._spec = spec
        self._raises = raises
        self.calls = []

    def build_spec(self, engine, profile, check_mode=False, timeout=None):
        self.calls.append((engine, profile, check_mode, timeout))
        if self._raises:
            raise self._raises
        return self._spec


class TestSpecRetrieval:
    def test_the_engines_spec_is_returned_verbatim(self):
        engine = _Engine()
        with patch(f"{MOD}.module_loader.get_module", return_value=engine):
            out = shim.build_licensed_spec("puppet", "class x {}")
        assert out is SPEC

    def test_arguments_reach_the_engine_unchanged(self):
        engine = _Engine()
        with patch(f"{MOD}.module_loader.get_module", return_value=engine):
            shim.build_licensed_spec("salt", "state:", check_mode=True, timeout=42)
        assert engine.calls == [("salt", "state:", True, 42)]

    def test_a_missing_module_is_none_not_an_exception(self):
        # The caller turns this into a 503. Raising here would surface as a
        # 500 and read as a server bug rather than a missing module.
        with patch(f"{MOD}.module_loader.get_module", return_value=None):
            assert shim.build_licensed_spec("puppet", "x") is None

    def test_a_module_without_build_spec_is_none(self):
        # Guards against a partially-built or mismatched engine version.
        with patch(f"{MOD}.module_loader.get_module", return_value=object()):
            assert shim.build_licensed_spec("puppet", "x") is None

    def test_an_engine_that_raises_does_not_take_the_request_down(self):
        engine = _Engine(raises=RuntimeError("boom"))
        with patch(f"{MOD}.module_loader.get_module", return_value=engine):
            assert shim.build_licensed_spec("puppet", "x") is None

    def test_an_engine_declining_the_input_is_none(self):
        # build_spec returns None for an unknown engine or empty profile.
        engine = _Engine(spec=None)
        with patch(f"{MOD}.module_loader.get_module", return_value=engine):
            assert shim.build_licensed_spec("puppet", "") is None

    def test_it_asks_for_the_right_module(self):
        with patch(f"{MOD}.module_loader.get_module", return_value=None) as get:
            shim.build_licensed_spec("chef", "x")
        get.assert_called_once_with("config_management_engine")
