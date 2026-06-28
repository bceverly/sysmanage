"""
Integration tests for the API-key management endpoints (Phase 13.2).

Exercises the full HTTP round-trip through the shared ``client`` fixture
(in-memory engine + mocked auth as ``test_user@example.com``).
"""


class TestApiKeyCrud:
    """Create / list / get / revoke lifecycle."""

    def test_create_returns_plaintext_once(self, client):
        resp = client.post("/api/api-keys", json={"name": "ci-pipeline"})
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "ci-pipeline"
        assert body["key"].startswith("smk_")
        assert body["key_prefix"] == body["key"][:12]
        assert body["is_active"] is True
        # The hash must never be exposed.
        assert "key_hash" not in body

    def test_list_omits_secret(self, client):
        client.post("/api/api-keys", json={"name": "k1"})
        resp = client.get("/api/api-keys")
        assert resp.status_code == 200
        keys = resp.json()
        assert len(keys) >= 1
        for k in keys:
            assert "key" not in k  # plaintext never re-exposed
            assert "key_hash" not in k
            assert k["key_prefix"].startswith("smk_")

    def test_get_single_key(self, client):
        created = client.post("/api/api-keys", json={"name": "single"}).json()
        resp = client.get(f"/api/api-keys/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]
        assert "key" not in resp.json()

    def test_get_missing_key_404(self, client):
        resp = client.get("/api/api-keys/00000000-0000-0000-0000-000000000999")
        assert resp.status_code == 404

    def test_revoke_key(self, client):
        created = client.post("/api/api-keys", json={"name": "to-revoke"}).json()
        resp = client.delete(f"/api/api-keys/{created['id']}")
        assert resp.status_code == 204
        # After revocation the key is listed as inactive.
        listed = client.get("/api/api-keys").json()
        match = [k for k in listed if k["id"] == created["id"]]
        assert match and match[0]["is_active"] is False
        assert match[0]["revoked_at"] is not None

    def test_revoke_missing_key_404(self, client):
        resp = client.delete("/api/api-keys/00000000-0000-0000-0000-000000000999")
        assert resp.status_code == 404

    def test_create_requires_name(self, client):
        resp = client.post("/api/api-keys", json={})
        assert resp.status_code == 422


class TestApiKeyManagementGuard:
    """API-key auth may not manage API keys."""

    def test_create_forbidden_with_api_key_auth(self, client):
        resp = client.post(
            "/api/api-keys",
            json={"name": "nope"},
            headers={"Authorization": "Bearer smk_someapikeyvalue"},
        )
        assert resp.status_code == 403

    def test_revoke_forbidden_with_api_key_auth(self, client):
        created = client.post("/api/api-keys", json={"name": "guarded"}).json()
        resp = client.delete(
            f"/api/api-keys/{created['id']}",
            headers={"Authorization": "Bearer smk_someapikeyvalue"},
        )
        assert resp.status_code == 403
