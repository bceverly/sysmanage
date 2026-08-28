# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The host-independent engine catalog (Phase 20.1).

Exists so profile AUTHORING has one source for the engine list. Before it, the
authoring page carried its own copy of the identities, and a second copy of
that list is how the server starts accepting a word the UI never offers.

The identity strings are the contract: the server, the agent and the licensed
engine all key on them, and a profile stored as "ansible" instead of
"ansible-core" is accepted here and then rejected at apply time -- the worst
place to find out.
"""

import pytest

from backend.api import config_mgmt_prereq as api
from backend.services import config_mgmt_engines as engines


class TestCatalog:
    @pytest.mark.asyncio
    async def test_lists_every_identity_the_server_accepts(self):
        out = await api.list_config_mgmt_engine_catalog()
        assert [e.engine for e in out.engines] == list(engines.ALL_ENGINES)

    @pytest.mark.asyncio
    async def test_licensed_adapters_are_labelled_not_omitted(self):
        # Hiding them would tell a Puppet shop that Puppet is unsupported when
        # it is actually a paid adapter.
        out = await api.list_config_mgmt_engine_catalog()
        licensed = {e.engine for e in out.engines if e.requires_license}
        assert licensed == set(engines.LICENSED_ENGINES)
        assert "puppet" in licensed

    @pytest.mark.asyncio
    async def test_open_source_engines_are_not_marked_licensed(self):
        out = await api.list_config_mgmt_engine_catalog()
        free = {e.engine for e in out.engines if not e.requires_license}
        assert free == set(engines.OSS_ENGINES)

    @pytest.mark.asyncio
    async def test_dsc_is_reported_as_vendored_and_windows_only(self):
        # It ships with the agent, so the UI must not offer to install it.
        out = await api.list_config_mgmt_engine_catalog()
        dsc = next(e for e in out.engines if e.engine == engines.DSC)
        assert dsc.vendored is True
        assert dsc.windows_only is True

    @pytest.mark.asyncio
    async def test_exactly_one_default_and_it_matches_the_registry(self):
        out = await api.list_config_mgmt_engine_catalog()
        defaults = [e.engine for e in out.engines if e.is_default]
        assert defaults == [engines.DEFAULT_ENGINE]
        assert out.default_engine == engines.DEFAULT_ENGINE

    @pytest.mark.asyncio
    async def test_identities_are_not_binary_names(self):
        # `chef`, never `chef-client`: the ordered binaries tuple lives in the
        # agent and is what lets Chef move to cinc without a rename here.
        out = await api.list_config_mgmt_engine_catalog()
        names = {e.engine for e in out.engines}
        assert "chef" in names
        assert "chef-client" not in names
        assert "ansible-playbook" not in names
