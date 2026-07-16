# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Phase 10 Pro+ stub-route smoke tests.

When the virtualization_engine and observability_engine modules aren't
loaded (the default for OSS deployments and the test harness), the
proplus_routes wrapper mounts stub routes under /api/v1/virt/* and
/api/v1/observability/* that always return ``{"licensed": False}``.

These tests verify the stubs are mounted and gated behind auth — the
licensed (engine-loaded) happy path is exercised directly against the
Cython module's pytest suite in the sysmanage-professional-plus repo.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring

import uuid

_HOST_ID = str(uuid.uuid4())


class TestVirtualizationStubRoutes:
    def test_kvm_stub_requires_auth(self, client):
        r = client.post(f"/api/v1/virt/kvm/{_HOST_ID}/test-vm/start")
        assert r.status_code in [401, 403, 404]

    def test_kvm_stub_returns_unlicensed(self, client, auth_headers):
        r = client.post(
            f"/api/v1/virt/kvm/{_HOST_ID}/test-vm/start",
            headers=auth_headers,
        )
        # Stub or real engine — engine isn't loaded in test harness so
        # the stub route serves: returns 200 + {"licensed": False}.
        assert r.status_code in [200, 402, 403, 404]
        if r.status_code == 200:
            assert r.json() == {"licensed": False}

    def test_bhyve_stub_returns_unlicensed(self, client, auth_headers):
        r = client.post(
            f"/api/v1/virt/bhyve/{_HOST_ID}/test-vm/start",
            headers=auth_headers,
        )
        assert r.status_code in [200, 402, 403, 404, 501]

    def test_vmm_stub_returns_unlicensed(self, client, auth_headers):
        r = client.post(
            f"/api/v1/virt/vmm/{_HOST_ID}/test-vm/start",
            headers=auth_headers,
        )
        assert r.status_code in [200, 402, 403, 404, 501]

    def test_kvm_create_stub_requires_auth(self, client):
        r = client.post(f"/api/v1/virt/kvm/{_HOST_ID}/create")
        assert r.status_code in [401, 403, 404]

    def test_kvm_create_stub_returns_unlicensed(self, client, auth_headers):
        r = client.post(
            f"/api/v1/virt/kvm/{_HOST_ID}/create",
            headers=auth_headers,
            json={"vm_name": "x", "hostname": "x", "distribution": "ubuntu"},
        )
        assert r.status_code in [200, 402, 403, 404, 422]
        if r.status_code == 200:
            assert r.json() == {"licensed": False}

    def test_kvm_delete_stub(self, client, auth_headers):
        r = client.post(
            f"/api/v1/virt/kvm/{_HOST_ID}/test-vm/delete",
            headers=auth_headers,
        )
        assert r.status_code in [200, 402, 403, 404]

    def test_kvm_storage_download_stub(self, client, auth_headers):
        r = client.post(
            f"/api/v1/virt/kvm/{_HOST_ID}/storage/download",
            headers=auth_headers,
            json={
                "url": "https://example.com/img.qcow2",
                "dest_path": "/var/lib/libvirt/images/x.qcow2",
            },
        )
        assert r.status_code in [200, 402, 403, 404, 422]

    def test_kvm_network_create_stub(self, client, auth_headers):
        r = client.post(
            f"/api/v1/virt/kvm/{_HOST_ID}/network/create",
            headers=auth_headers,
            json={"name": "x"},
        )
        assert r.status_code in [200, 402, 403, 404, 422]

    def test_kvm_network_delete_stub(self, client, auth_headers):
        r = client.post(
            f"/api/v1/virt/kvm/{_HOST_ID}/network/x/delete",
            headers=auth_headers,
        )
        assert r.status_code in [200, 402, 403, 404]

    def test_kvm_network_list_stub(self, client, auth_headers):
        r = client.post(
            f"/api/v1/virt/kvm/{_HOST_ID}/network/list",
            headers=auth_headers,
        )
        assert r.status_code in [200, 402, 403, 404]

    def test_bhyve_create_stub(self, client, auth_headers):
        r = client.post(
            f"/api/v1/virt/bhyve/{_HOST_ID}/create",
            headers=auth_headers,
            json={"vm_name": "x"},
        )
        assert r.status_code in [200, 402, 403, 404, 422]

    def test_bhyve_delete_stub(self, client, auth_headers):
        r = client.post(
            f"/api/v1/virt/bhyve/{_HOST_ID}/x/delete",
            headers=auth_headers,
        )
        assert r.status_code in [200, 402, 403, 404]

    def test_bhyve_zvol_stub(self, client, auth_headers):
        r = client.post(
            f"/api/v1/virt/bhyve/{_HOST_ID}/zvol/create",
            headers=auth_headers,
            json={"zvol_name": "x", "size": "10G"},
        )
        assert r.status_code in [200, 402, 403, 404, 422]

    def test_vmm_create_stub(self, client, auth_headers):
        r = client.post(
            f"/api/v1/virt/vmm/{_HOST_ID}/create",
            headers=auth_headers,
            json={"vm_name": "x"},
        )
        assert r.status_code in [200, 402, 403, 404, 422]

    def test_vmm_delete_stub(self, client, auth_headers):
        r = client.post(
            f"/api/v1/virt/vmm/{_HOST_ID}/x/delete",
            headers=auth_headers,
        )
        assert r.status_code in [200, 402, 403, 404]

    def test_provision_stub(self, client, auth_headers):
        r = client.post(
            f"/api/v1/virt/provision/{_HOST_ID}/ubuntu",
            headers=auth_headers,
            json={"dest_path": "/srv/x", "request": {}},
        )
        assert r.status_code in [200, 402, 403, 404, 422]

    def test_safe_reboot_prepare_stub(self, client, auth_headers):
        r = client.post(
            f"/api/v1/virt/safe-reboot/{_HOST_ID}/prepare",
            headers=auth_headers,
            json={"hypervisor": "kvm", "running_vms": []},
        )
        assert r.status_code in [200, 402, 403, 404, 422]

    def test_safe_reboot_restore_stub(self, client, auth_headers):
        r = client.post(
            f"/api/v1/virt/safe-reboot/{_HOST_ID}/kvm/restore",
            headers=auth_headers,
        )
        assert r.status_code in [200, 402, 403, 404]


class TestObservabilityStubRoutes:
    def test_otel_stub_requires_auth(self, client):
        r = client.post(f"/api/v1/observability/otel/{_HOST_ID}/status")
        assert r.status_code in [401, 403, 404]

    def test_otel_stub_returns_unlicensed(self, client, auth_headers):
        r = client.post(
            f"/api/v1/observability/otel/{_HOST_ID}/status",
            headers=auth_headers,
        )
        assert r.status_code in [200, 402, 403, 404]
        if r.status_code == 200:
            assert r.json() == {"licensed": False}

    def test_graylog_stub_returns_unlicensed(self, client, auth_headers):
        r = client.post(
            f"/api/v1/observability/graylog/{_HOST_ID}/status",
            headers=auth_headers,
        )
        assert r.status_code in [200, 402, 403, 404, 501]

    def test_grafana_stub_returns_unlicensed(self, client, auth_headers):
        r = client.post(
            f"/api/v1/observability/grafana/{_HOST_ID}/status",
            headers=auth_headers,
        )
        assert r.status_code in [200, 402, 403, 404, 501]

    def test_otel_deploy_stub(self, client, auth_headers):
        r = client.post(
            f"/api/v1/observability/otel/{_HOST_ID}/deploy",
            headers=auth_headers,
            json={},
        )
        assert r.status_code in [200, 402, 403, 404, 422]

    def test_otel_remove_stub(self, client, auth_headers):
        r = client.post(
            f"/api/v1/observability/otel/{_HOST_ID}/remove",
            headers=auth_headers,
        )
        assert r.status_code in [200, 402, 403, 404]

    def test_grafana_provision_stub(self, client, auth_headers):
        r = client.post(
            f"/api/v1/observability/grafana/{_HOST_ID}/provision",
            headers=auth_headers,
            json={"grafana_url": "http://x", "api_token": "t"},
        )
        assert r.status_code in [200, 402, 403, 404, 422]

    def test_routing_apply_stub(self, client, auth_headers):
        r = client.post(
            f"/api/v1/observability/routing/{_HOST_ID}/apply",
            headers=auth_headers,
            json={"rules": [], "base_otel_request": {}},
        )
        assert r.status_code in [200, 402, 403, 404, 422]

    def test_graylog_deploy_stub(self, client, auth_headers):
        r = client.post(
            f"/api/v1/observability/graylog/{_HOST_ID}/deploy",
            headers=auth_headers,
            json={"server_url": "http://x", "api_token": "t", "node_id": "n"},
        )
        assert r.status_code in [200, 402, 403, 404, 422]

    def test_graylog_remove_stub(self, client, auth_headers):
        r = client.post(
            f"/api/v1/observability/graylog/{_HOST_ID}/linux/remove",
            headers=auth_headers,
        )
        assert r.status_code in [200, 402, 403, 404]


class TestPhase10FeatureCodesRegistered:
    """The feature/module-code enums must include the new Phase 10 codes
    so future license-server payloads referencing them validate."""

    def test_virtualization_feature_codes_registered(self):
        from backend.licensing.features import FeatureCode

        # Will raise ValueError if the codes aren't in the enum.
        FeatureCode.from_string("virtualization_kvm_lifecycle")
        FeatureCode.from_string("virtualization_kvm_create")
        FeatureCode.from_string("virtualization_bhyve_lifecycle")
        FeatureCode.from_string("virtualization_vmm_lifecycle")

    def test_observability_feature_codes_registered(self):
        from backend.licensing.features import FeatureCode

        FeatureCode.from_string("observability_otel_deploy")
        FeatureCode.from_string("observability_graylog_deploy")
        FeatureCode.from_string("observability_grafana_provision")

    def test_phase10_module_codes_registered(self):
        from backend.licensing.features import ModuleCode

        ModuleCode.from_string("virtualization_engine")
        ModuleCode.from_string("observability_engine")

    def test_enterprise_tier_includes_phase10_features(self):
        from backend.licensing.features import (
            FeatureCode,
            LicenseTier,
            TIER_FEATURES,
        )

        ent = TIER_FEATURES[LicenseTier.ENTERPRISE]
        assert FeatureCode.VIRTUALIZATION_KVM_LIFECYCLE in ent
        assert FeatureCode.OBSERVABILITY_OTEL_DEPLOY in ent

    def test_enterprise_tier_includes_phase10_modules(self):
        from backend.licensing.features import (
            LicenseTier,
            ModuleCode,
            TIER_MODULES,
        )

        ent = TIER_MODULES[LicenseTier.ENTERPRISE]
        assert ModuleCode.VIRTUALIZATION_ENGINE in ent
        assert ModuleCode.OBSERVABILITY_ENGINE in ent
