"""
API tests for the Phase 12 federation role + identity-key endpoints that
drive the federation card on Settings → Server Role.

Federation role is a SEPARATE axis from the air-gap server_role — these
verify the two coexist independently, plus the identity public-key copy +
trusted-peer import surface.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring,redefined-outer-name

import pytest


@pytest.fixture
def fed_keydirs(tmp_path, monkeypatch):
    """Point the identity service at writable tmp paths for the FS-touching
    key endpoints."""
    key_file = str(tmp_path / "id" / "identity-ed25519.pem")
    peer_dir = str(tmp_path / "peers")
    monkeypatch.setattr(
        "backend.config.config.get_federation_identity_key_file", lambda: key_file
    )
    monkeypatch.setattr(
        "backend.config.config.get_federation_peer_public_key_dir", lambda: peer_dir
    )
    return key_file, peer_dir


class TestFederationRoleEndpoint:
    def test_default_role_is_none(self, client, auth_headers):
        r = client.get("/api/v1/federation-role", headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["role"] == "none"
        assert set(body["valid_roles"]) == {"none", "coordinator", "site"}

    # NB: the role-WRITE path (PUT) and its independence from server_role are
    # covered deterministically in
    # ``tests/services/test_server_config_federation_role.py`` — the service
    # uses ``db.get_session_local()`` (the real configured DB), so writing it
    # through the API client here would hit the live DB, the same reason the
    # air-gap server-role PUT isn't API-tested either.

    def test_requires_auth(self, client):
        assert client.get("/api/v1/federation-role").status_code in (401, 403)


class TestIdentityKeyEndpoint:
    def test_identity_key_is_available(self, client, auth_headers, fed_keydirs):
        r = client.get("/api/v1/federation/identity-key", headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "PUBLIC KEY" in body["public_key_pem"]
        assert len(body["fingerprint"]) == 64

    def test_peer_import_list_remove(self, client, auth_headers, fed_keydirs):
        # Use this server's own public key as a stand-in peer key.
        own = client.get(
            "/api/v1/federation/identity-key", headers=auth_headers
        ).json()["public_key_pem"]

        imp = client.post(
            "/api/v1/federation/trusted-peers",
            json={"name": "coord-1", "public_key_pem": own},
            headers=auth_headers,
        )
        assert imp.status_code == 200, imp.text
        assert imp.json()["name"] == "coord-1"

        lst = client.get("/api/v1/federation/trusted-peers", headers=auth_headers)
        assert len(lst.json()["trusted"]) == 1

        rm = client.delete(
            "/api/v1/federation/trusted-peers/coord-1", headers=auth_headers
        )
        assert rm.status_code == 204
        assert (
            client.get("/api/v1/federation/trusted-peers", headers=auth_headers).json()[
                "trusted"
            ]
            == []
        )

    def test_peer_import_rejects_garbage(self, client, auth_headers, fed_keydirs):
        r = client.post(
            "/api/v1/federation/trusted-peers",
            json={"name": "bad", "public_key_pem": "not a key"},
            headers=auth_headers,
        )
        assert r.status_code == 400
