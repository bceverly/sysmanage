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
        with patch(
            "backend.api.airgap_bundles.airgap_bundle_builder.start_build"
        ) as m, patch.object(
            LicenseService,
            "is_pro_plus_active",
            new_callable=PropertyMock,
            return_value=True,
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
