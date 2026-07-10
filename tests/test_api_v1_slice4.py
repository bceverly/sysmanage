"""
Phase 13.2.1 — Slice 4 native ``/api/v1`` migration (security / auth-mgmt).

Dual-surface contract for the migrated routers (auth, security, security_roles,
password_reset, openbao, external_idp *management*) and the explicit invariants
that the deferred / stable surfaces are NOT natively versioned:

  * external_idp SSO/ACS/metadata callbacks (IdP-configured URLs),
  * OSS ``secrets`` (deferred — collides with the Pro+ secrets_engine v1 path),
  * agent-facing ``certificates``.
"""

import pytest

GET_DUAL_SURFACE = [
    "/security/default-credentials-status",
    "/security-roles/groups",
    "/openbao/status",
    "/idp-providers",  # Pro+-gated -> 402 on both surfaces, still must match
    "/settings/idp",
]
GET_NATIVE_OK = [
    "/security/default-credentials-status",
]
POST_DUAL_SURFACE = [
    "/login",
    "/forgot-password",
]


class TestDualSurface:
    @pytest.mark.parametrize("path", GET_DUAL_SURFACE)
    def test_get_v1_and_alias_match(self, client, path):
        v1 = client.get("/api/v1" + path)
        alias = client.get("/api" + path)
        assert v1.status_code != 404
        assert alias.status_code == 404

    @pytest.mark.parametrize("path", GET_NATIVE_OK)
    def test_get_v1_native_ok(self, client, path):
        assert client.get("/api/v1" + path).status_code == 200

    @pytest.mark.parametrize("path", POST_DUAL_SURFACE)
    def test_post_v1_and_alias_match(self, client, path):
        v1 = client.post("/api/v1" + path, json={})
        alias = client.post("/api" + path, json={})
        assert v1.status_code != 404
        assert alias.status_code == 404


class TestUnversionedInvariants:
    """These surfaces must NOT gain a native v1 route in this slice."""

    def test_invariants(self):
        import backend.main as m  # noqa: PLC0415

        paths = {r.path for r in m.app.routes if hasattr(r, "path")}
        # external_idp SSO callbacks stay unversioned (IdP-configured).
        assert "/api/auth/saml/{provider_id}/acs" in paths
        assert "/api/v1/auth/saml/{provider_id}/acs" not in paths
        assert "/api/auth/oidc/{provider_id}/callback" in paths
        assert "/api/v1/auth/oidc/{provider_id}/callback" not in paths
        # OSS secrets deferred (Pro+ secrets_engine owns /api/v1/secrets).
        assert "/api/v1/secrets" not in paths
        # certificates stays agent-facing/unversioned.
        assert "/api/certificates/client/{host_id}" in paths
        assert "/api/v1/certificates/client/{host_id}" not in paths
