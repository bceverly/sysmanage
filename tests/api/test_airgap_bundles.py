"""API tests for /api/airgap-bundles endpoints.

The build subprocess is patched out — we only verify the API surface
(create → row inserted, list, get, delete) and the queued-state
contract; the actual buildAirGapBundle.sh execution is its own beast
(Docker per distro, takes minutes) and is exercised via the standalone
script's smoke test, not here.
"""

from unittest.mock import PropertyMock, patch

import pytest

from backend.licensing.license_service import LicenseService


class TestAirGapBundlesAPI:
    """Smoke tests for the bundle lifecycle endpoints."""

    @pytest.fixture(autouse=True)
    def _mute_builder(self):
        # Patch the builder so the POST doesn't actually spawn a thread
        # that would try to docker-run.
        # Also patch ``LicenseService.is_pro_plus_active`` (a property)
        # to True — endpoints are Pro+-gated and the test fixture has
        # no license configured.  PropertyMock is required because a
        # plain ``patch`` on a property has no deleter to restore.
        # Also force the resource pre-flight to "sufficient" so the
        # build gate doesn't 409 on a low-RAM CI runner (it reads real
        # /proc/meminfo otherwise).  The gate itself is covered by its
        # own test below, which overrides this.
        with patch(
            "backend.api.airgap_bundles.airgap_bundle_builder.start_build"
        ) as m, patch.object(
            LicenseService,
            "is_pro_plus_active",
            new_callable=PropertyMock,
            return_value=True,
        ), patch(
            "backend.api.airgap_bundles._check_build_resources",
            return_value={
                "ram_total_mb": 8000,
                "ram_available_mb": 6000,
                "swap_total_mb": 0,
                "swap_free_mb": 0,
                "available_mb": 6000,
                "disk_free_gb": 50.0,
                "disk_total_gb": 100.0,
                "min_available_mb": 2048,
                "min_disk_gb": 5,
                "severity": "ok",
                "sufficient": True,
                "reason": None,
            },
        ):
            yield m

    def test_list_empty(self, client, auth_headers):
        resp = client.get("/api/airgap-bundles", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_server_bundle(self, client, auth_headers, _mute_builder):
        resp = client.post(
            "/api/airgap-bundles",
            json={"product": "server"},
            headers=auth_headers,
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["product"] == "server"
        assert body["status"] == "queued"
        assert body["size_bytes"] is None
        assert body["completed_at"] is None
        _mute_builder.assert_called_once()

    def test_create_agent_bundle(self, client, auth_headers, _mute_builder):
        resp = client.post(
            "/api/airgap-bundles",
            json={"product": "agent"},
            headers=auth_headers,
        )
        assert resp.status_code == 202
        assert resp.json()["product"] == "agent"

    def test_create_blocked_when_resources_insufficient(self, client, auth_headers):
        # Override the autouse "sufficient" mock with an insufficient one
        # and confirm the build is refused with 409 before any thread is
        # spawned (server-side gate).
        with patch(
            "backend.api.airgap_bundles._check_build_resources",
            return_value={
                "ram_total_mb": 1000,
                "ram_available_mb": 400,
                "swap_total_mb": 0,
                "swap_free_mb": 0,
                "available_mb": 400,
                "disk_free_gb": 50.0,
                "disk_total_gb": 100.0,
                "min_available_mb": 2048,
                "min_disk_gb": 5,
                "severity": "insufficient",
                "sufficient": False,
                "reason": "only 400 MB of RAM+swap free; need >= 2048 MB",
            },
        ):
            resp = client.post(
                "/api/airgap-bundles",
                json={"product": "server"},
                headers=auth_headers,
            )
        assert resp.status_code == 409, resp.text
        assert "Insufficient host resources" in resp.json()["detail"]

    def test_proplus_bundle_not_resource_gated(self, client, auth_headers):
        # The Pro+ overlay bundle is a lightweight file copy and must
        # NOT be blocked by the resource gate even when it would report
        # insufficient for the Docker-driven products.
        with patch(
            "backend.api.airgap_bundles._check_build_resources",
            return_value={
                "ram_total_mb": 1000,
                "ram_available_mb": 400,
                "swap_total_mb": 0,
                "swap_free_mb": 0,
                "available_mb": 400,
                "disk_free_gb": 50.0,
                "disk_total_gb": 100.0,
                "min_available_mb": 2048,
                "min_disk_gb": 5,
                "severity": "insufficient",
                "sufficient": False,
                "reason": "low",
            },
        ):
            resp = client.post(
                "/api/airgap-bundles",
                json={"product": "proplus"},
                headers=auth_headers,
            )
        assert resp.status_code == 202, resp.text

    def test_resource_status_endpoint(self, client, auth_headers):
        resp = client.get("/api/airgap-bundles/resource-status", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        for key in ("sufficient", "severity", "min_available_mb", "min_disk_gb"):
            assert key in body

    def test_create_rejects_unknown_product(self, client, auth_headers):
        resp = client.post(
            "/api/airgap-bundles",
            json={"product": "scanner"},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_get_returns_404_for_unknown_id(self, client, auth_headers):
        resp = client.get(
            "/api/airgap-bundles/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_download_409_when_not_ready(self, client, auth_headers, _mute_builder):
        # Create a bundle (stays in 'queued' because builder is muted).
        r = client.post(
            "/api/airgap-bundles",
            json={"product": "server"},
            headers=auth_headers,
        )
        bundle_id = r.json()["id"]

        resp = client.get(
            f"/api/airgap-bundles/{bundle_id}/download", headers=auth_headers
        )
        assert resp.status_code == 409
        assert "not ready" in resp.json()["detail"].lower()

    def test_delete_removes_row(self, client, auth_headers, _mute_builder):
        r = client.post(
            "/api/airgap-bundles",
            json={"product": "agent"},
            headers=auth_headers,
        )
        bundle_id = r.json()["id"]

        d = client.delete(f"/api/airgap-bundles/{bundle_id}", headers=auth_headers)
        assert d.status_code == 204

        # And the row is really gone.
        g = client.get(f"/api/airgap-bundles/{bundle_id}", headers=auth_headers)
        assert g.status_code == 404

    def test_list_orders_newest_first(self, client, auth_headers, _mute_builder):
        first = client.post(
            "/api/airgap-bundles",
            json={"product": "server"},
            headers=auth_headers,
        ).json()
        second = client.post(
            "/api/airgap-bundles",
            json={"product": "agent"},
            headers=auth_headers,
        ).json()

        rows = client.get("/api/airgap-bundles", headers=auth_headers).json()
        # Newest first by created_at ordering — second post should be first.
        ids = [r["id"] for r in rows]
        assert second["id"] in ids
        assert first["id"] in ids
        assert ids.index(second["id"]) <= ids.index(first["id"])

    def test_anonymous_rejected(self, client):
        # No auth header — JWTBearer should refuse before reaching the handler.
        resp = client.post("/api/airgap-bundles", json={"product": "server"})
        assert resp.status_code in (401, 403)

    def test_docker_status_missing_binary(self, client, auth_headers):
        # When `docker` isn't on PATH, the endpoint must return
        # installed=False rather than 500.  We force shutil.which to
        # return None to simulate a docker-less host.
        with patch("backend.api.airgap_bundles.shutil.which", return_value=None):
            resp = client.get("/api/airgap-bundles/docker-status", headers=auth_headers)
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["installed"] is False
            assert body["running"] is False
            assert body["user_in_group"] is False
            assert body["permission_denied"] is False
            assert body["process_user"]  # always populated
            assert body["error"]

    def test_docker_status_installed_but_daemon_down(self, client, auth_headers):
        # docker binary exists but `docker info` returns non-zero.  The
        # response should report installed=True/running=False with a
        # non-empty error preview.
        import subprocess as _subprocess

        version_proc = _subprocess.CompletedProcess(
            args=["docker", "--version"],
            returncode=0,
            stdout="Docker version 24.0.0, build abcdef\n",
            stderr="",
        )
        info_proc = _subprocess.CompletedProcess(
            args=["docker", "info"],
            returncode=1,
            stdout="",
            stderr="Cannot connect to the Docker daemon at unix:///var/run/docker.sock\n",
        )
        with patch(
            "backend.api.airgap_bundles.shutil.which", return_value="/usr/bin/docker"
        ), patch(
            "backend.api.airgap_bundles.subprocess.run",
            side_effect=[version_proc, info_proc],
        ):
            resp = client.get("/api/airgap-bundles/docker-status", headers=auth_headers)
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["installed"] is True
            assert body["running"] is False
            assert body["version"].startswith("Docker version")
            assert body["permission_denied"] is False
            assert "daemon" in body["error"].lower()

    def test_docker_status_permission_denied(self, client, auth_headers):
        # docker binary exists, daemon is up, but the calling user
        # isn't in the docker group — the endpoint must flag this as
        # permission_denied=True so the UI shows the right remediation.
        import subprocess as _subprocess

        version_proc = _subprocess.CompletedProcess(
            args=["docker", "--version"],
            returncode=0,
            stdout="Docker version 24.0.0, build abcdef\n",
            stderr="",
        )
        info_proc = _subprocess.CompletedProcess(
            args=["docker", "info"],
            returncode=1,
            stdout="",
            stderr="permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock\n",
        )
        with patch(
            "backend.api.airgap_bundles.shutil.which", return_value="/usr/bin/docker"
        ), patch(
            "backend.api.airgap_bundles.subprocess.run",
            side_effect=[version_proc, info_proc],
        ):
            resp = client.get("/api/airgap-bundles/docker-status", headers=auth_headers)
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["installed"] is True
            assert body["running"] is False
            assert body["permission_denied"] is True


class TestAirGapBundlesProPlusGate:
    """The Pro+ gate must reject Community-tier access even when the
    user is authenticated.  Separate class so we don't accidentally
    inherit the autouse license bypass from TestAirGapBundlesAPI."""

    def test_post_returns_403_on_community(self, client, auth_headers):
        # No license patch — license_service.is_pro_plus_active is
        # whatever the test fixture's default is (False on Community).
        with patch.object(
            LicenseService,
            "is_pro_plus_active",
            new_callable=PropertyMock,
            return_value=False,
        ):
            resp = client.post(
                "/api/airgap-bundles",
                json={"product": "server"},
                headers=auth_headers,
            )
            assert resp.status_code == 403
            assert "pro_plus" in str(resp.json()).lower()

    def test_list_returns_403_on_community(self, client, auth_headers):
        with patch.object(
            LicenseService,
            "is_pro_plus_active",
            new_callable=PropertyMock,
            return_value=False,
        ):
            resp = client.get("/api/airgap-bundles", headers=auth_headers)
            assert resp.status_code == 403
