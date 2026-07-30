# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Provisioning-bundle endpoint (Phase 18.1 S4): mint a placement-bearing
enrollment token + render first-boot cloud-init user-data."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.api import provisioning_bundle as pb


def _body(**kw):
    base = dict(
        tenant_id="t1",
        site_id="site-1",
        access_group_id="grp-1",
        server_host="srv.example",
    )
    base.update(kw)
    return pb.ProvisioningBundleRequest(**base)


def _run(body):
    return asyncio.run(pb.create_provisioning_bundle(body, current_user="admin@x"))


def test_bundle_mints_placement_token_and_renders():
    engine = MagicMock()
    engine.render_agent_config_yaml.return_value = "server:\n  hostname: srv\n"
    engine.render_cloud_init_user_data.return_value = "#cloud-config\nruncmd:\n"
    engine.agent_install_runcmd.return_value = ["dnf install -y sysmanage-agent"]
    captured = {}

    def fake_gen(session, tenant_id, **kw):
        captured.update(kw)
        captured["tenant_id"] = tenant_id
        return ("sme_TOKEN", MagicMock())

    with patch.object(
        pb.license_service, "has_feature", return_value=True
    ), patch.object(pb.license_service, "has_module", return_value=True), patch.object(
        pb.module_loader, "get_module", return_value=engine
    ), patch.object(
        pb.config, "is_multitenancy_enabled", return_value=True
    ), patch.object(
        pb.enrollment_service, "generate_token", side_effect=fake_gen
    ), patch(
        "backend.persistence.partitions.partition_session"
    ) as psess:
        psess.return_value.__enter__.return_value = MagicMock()
        psess.return_value.__exit__.return_value = False
        resp = _run(_body(os_family="rocky"))

    assert resp.token == "sme_TOKEN"
    assert resp.user_data.startswith("#cloud-config")
    # os_family selects the per-distro install runcmd, which is handed to render
    engine.agent_install_runcmd.assert_called_once_with("rocky")
    assert engine.render_cloud_init_user_data.call_args.args[2] == [
        "dnf install -y sysmanage-agent"
    ]
    # placement forwarded to the token mint
    assert captured["site_id"] == "site-1"
    assert captured["access_group_id"] == "grp-1"
    assert captured["tenant_id"] == "t1"
    # the minted token was embedded into the rendered agent config
    assert (
        engine.render_agent_config_yaml.call_args.kwargs["enrollment_token"]
        == "sme_TOKEN"
    )


def test_bundle_402_without_enterprise_feature():
    with patch.object(pb.license_service, "has_feature", return_value=False):
        with pytest.raises(HTTPException) as exc:
            _run(_body())
    assert exc.value.status_code == 402


def test_bundle_400_when_multitenancy_disabled():
    with patch.object(
        pb.license_service, "has_feature", return_value=True
    ), patch.object(pb.config, "is_multitenancy_enabled", return_value=False):
        with pytest.raises(HTTPException) as exc:
            _run(_body())
    assert exc.value.status_code == 400
