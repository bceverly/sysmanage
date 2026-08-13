# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A child host must enrol into its PARENT's tenant, not into "No tenant".

``_build_agent_config_yaml`` emitted ``server.*``, ``logging``, ``websocket``,
``script_execution`` and optionally ``auto_approve.token`` -- but never
``security.enrollment_token``, which is the key the agent actually reads
(``config.get_enrollment_token``).

Those two are different things and only the second one places the host:

  * ``auto_approve.token`` skips the pending-approval queue;
  * ``security.enrollment_token`` selects WHICH TENANT DATABASE the host is
    written to.

So a VM created on a tenant-owned hypervisor registered server-scoped and
landed in the bootstrap ("No tenant") database, where the owning tenant's queue
processor never sees it.  Confirmed 2026-08-06 with ``win2022-smoke``.

Two reasons this could not be left: the "No tenant" scope is slated for removal,
after which a token-less registration is simply rejected and child-host
provisioning breaks outright; and ``_reject_if_fqdn_belongs_to_tenant`` already
403s a token-less re-registration whose fqdn lives in a tenant DB, so a
re-provisioned child can fail in a way that looks like a phantom-duplicate bug.
"""

from unittest.mock import patch

import pytest
import yaml

from backend.api import child_host_creation_dispatch as dispatch

PARENT = "aabeadb6-8cc4-4449-bb92-4be7b8e42c51"
TENANT = "tenant-theeverlys"
TOKEN = "enroll-token-abc123"

BASE_PARAMS = {
    "server_url": "sysmanage.example.com",
    "server_port": 8443,
    "use_https": True,
}


def _config(params=None, parent=PARENT):
    return yaml.safe_load(
        dispatch._build_agent_config_yaml({**BASE_PARAMS, **(params or {})}, parent)
    )


def test_child_config_carries_its_parents_enrollment_token():
    """The fix: the child is placed in the parent's tenant."""
    with patch.object(dispatch, "_child_enrollment_token", return_value=TOKEN):
        config = _config()
    assert config["security"]["enrollment_token"] == TOKEN


def test_enrollment_token_is_distinct_from_auto_approve():
    """Both may be present, and they are NOT interchangeable.

    Emitting only auto_approve (the old behaviour) approves a host into no
    tenant at all.
    """
    with patch.object(dispatch, "_child_enrollment_token", return_value=TOKEN):
        config = _config({"auto_approve_token": "AUTO"})
    assert config["auto_approve"]["token"] == "AUTO"
    assert config["security"]["enrollment_token"] == TOKEN


def test_no_token_means_no_security_block():
    """Single-tenant servers mint nothing; the config must stay valid YAML."""
    with patch.object(dispatch, "_child_enrollment_token", return_value=None):
        config = _config()
    assert "security" not in config
    assert config["server"]["hostname"] == "sysmanage.example.com"


def test_an_explicit_token_in_params_wins():
    """A caller that already minted one must not trigger a second mint."""
    with patch.object(dispatch, "_child_enrollment_token") as minter:
        config = _config({"enrollment_token": "EXPLICIT"})
    minter.assert_not_called()
    assert config["security"]["enrollment_token"] == "EXPLICIT"


def test_the_config_is_still_parseable_yaml_with_a_token():
    """The agent parses this file at boot; a malformed one strands the VM."""
    with patch.object(dispatch, "_child_enrollment_token", return_value=TOKEN):
        text = dispatch._build_agent_config_yaml(BASE_PARAMS, PARENT)
    parsed = yaml.safe_load(text)
    assert isinstance(parsed, dict)
    assert set(
        ["server", "logging", "websocket", "script_execution", "security"]
    ) <= set(parsed)


# --------------------------------------------------------------------------
# minting
# --------------------------------------------------------------------------


def test_mint_uses_the_parents_tenant():
    with patch(
        "backend.services.host_tenant_index.tenant_for_host", return_value=TENANT
    ), patch(
        "backend.api.proplus_routes._provisioning_enrollment_token_fn",
        return_value=TOKEN,
    ) as mint:
        assert dispatch._child_enrollment_token(PARENT) == TOKEN
    mint.assert_called_once_with(tenant_id=TENANT)


def test_no_parent_host_mints_nothing():
    assert dispatch._child_enrollment_token(None) is None


def test_an_unresolvable_parent_tenant_declines_rather_than_guessing():
    """Inventing a placement is worse than stating none.

    A token-less registration still works today; a token naming the WRONG
    tenant would put the child in someone else's data plane.
    """
    with patch("backend.services.host_tenant_index.tenant_for_host", return_value=None):
        assert dispatch._child_enrollment_token(PARENT) is None


def test_a_failure_while_minting_does_not_break_creation():
    """Child-host creation must not fail because placement could not be minted."""
    with patch(
        "backend.services.host_tenant_index.tenant_for_host",
        side_effect=RuntimeError("registry unavailable"),
    ):
        assert dispatch._child_enrollment_token(PARENT) is None


@pytest.mark.parametrize("call_site", ["kvm", "wsl", "lxd"])
def test_every_creation_path_passes_the_parent_host(call_site):
    """All three engines build the config; a path that forgot the parent would
    silently produce token-less children again."""
    import inspect

    source = inspect.getsource(dispatch)
    assert (
        source.count("_build_agent_config_yaml(command_params, host_id)") == 3
    ), "a creation path is not passing the parent host id"
