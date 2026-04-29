"""
Tests for the Phase 8.1 access-groups + registration-keys API.

Exercises:
  - Auth gate on every endpoint.
  - Tree CRUD on AccessGroup including parent_id semantics.
  - Cycle prevention (self-parent, ancestor-loop).
  - Registration-key create returns the secret EXACTLY ONCE; subsequent
    list calls do not echo it.
  - Revoke is idempotent.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name


class TestAccessGroupsAuth:
    def test_list_requires_auth(self, client):
        r = client.get("/api/access-groups")
        assert r.status_code in [401, 403]

    def test_create_requires_auth(self, client):
        r = client.post("/api/access-groups", json={"name": "no-auth"})
        assert r.status_code in [401, 403]


class TestAccessGroupsCrud:
    def test_create_root_group(self, client, auth_headers):
        r = client.post(
            "/api/access-groups",
            json={"name": "DC-East", "description": "East-coast datacenter"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"] == "DC-East"
        assert body["parent_id"] is None
        assert "id" in body

    def test_list_after_create(self, client, auth_headers):
        client.post(
            "/api/access-groups",
            json={"name": "DC-West"},
            headers=auth_headers,
        )
        r = client.get("/api/access-groups", headers=auth_headers)
        assert r.status_code == 200
        names = [g["name"] for g in r.json()]
        assert "DC-West" in names

    def test_create_child_group(self, client, auth_headers):
        parent_resp = client.post(
            "/api/access-groups",
            json={"name": "DC-Central"},
            headers=auth_headers,
        )
        parent_id = parent_resp.json()["id"]
        child_resp = client.post(
            "/api/access-groups",
            json={"name": "DC-Central / Web", "parent_id": parent_id},
            headers=auth_headers,
        )
        assert child_resp.status_code == 200, child_resp.text
        assert child_resp.json()["parent_id"] == parent_id

    def test_create_with_unknown_parent_404(self, client, auth_headers):
        r = client.post(
            "/api/access-groups",
            json={
                "name": "orphan",
                "parent_id": "00000000-0000-0000-0000-000000000099",
            },
            headers=auth_headers,
        )
        assert r.status_code == 404

    def test_get_one(self, client, auth_headers):
        created = client.post(
            "/api/access-groups",
            json={"name": "single"},
            headers=auth_headers,
        ).json()
        r = client.get(f"/api/access-groups/{created['id']}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["id"] == created["id"]

    def test_update_name(self, client, auth_headers):
        created = client.post(
            "/api/access-groups",
            json={"name": "rename-me"},
            headers=auth_headers,
        ).json()
        r = client.put(
            f"/api/access-groups/{created['id']}",
            json={"name": "renamed"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json()["name"] == "renamed"

    def test_delete(self, client, auth_headers):
        created = client.post(
            "/api/access-groups",
            json={"name": "ephemeral"},
            headers=auth_headers,
        ).json()
        r = client.delete(f"/api/access-groups/{created['id']}", headers=auth_headers)
        assert r.status_code == 200


class TestAccessGroupsCycleGuard:
    def test_cannot_set_self_as_parent(self, client, auth_headers):
        created = client.post(
            "/api/access-groups",
            json={"name": "loopy"},
            headers=auth_headers,
        ).json()
        r = client.put(
            f"/api/access-groups/{created['id']}",
            json={"parent_id": created["id"]},
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_cannot_create_ancestor_cycle(self, client, auth_headers):
        """Build a chain a → b, then try to make a's parent be b → cycle."""
        a = client.post(
            "/api/access-groups", json={"name": "a"}, headers=auth_headers
        ).json()
        b = client.post(
            "/api/access-groups",
            json={"name": "b", "parent_id": a["id"]},
            headers=auth_headers,
        ).json()
        # Now try: a.parent = b would create the cycle a → b → a.
        r = client.put(
            f"/api/access-groups/{a['id']}",
            json={"parent_id": b["id"]},
            headers=auth_headers,
        )
        assert r.status_code == 400


class TestRegistrationKeys:
    def test_create_returns_secret_exactly_once(self, client, auth_headers):
        """The plaintext key must be in the create response, but a
        subsequent list call must NOT echo it."""
        r = client.post(
            "/api/registration-keys",
            json={"name": "first-key", "auto_approve": False},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["key"], "create response must include the plaintext key"
        key_id = body["id"]
        secret = body["key"]

        list_resp = client.get("/api/registration-keys", headers=auth_headers)
        assert list_resp.status_code == 200
        for entry in list_resp.json():
            if entry["id"] == key_id:
                # Either the field is absent or it's None — never the secret.
                assert entry.get("key") in (
                    None,
                    "",
                ), "list endpoint leaked the plaintext registration key"
                break
        else:
            raise AssertionError("created key not found in list response")

        # Sanity: secret looks like a token, not blank or whitespace.
        assert len(secret) >= 32

    def test_revoke_is_idempotent(self, client, auth_headers):
        created = client.post(
            "/api/registration-keys",
            json={"name": "revokable"},
            headers=auth_headers,
        ).json()
        r1 = client.post(
            f"/api/registration-keys/{created['id']}/revoke", headers=auth_headers
        )
        r2 = client.post(
            f"/api/registration-keys/{created['id']}/revoke", headers=auth_headers
        )
        assert r1.status_code == 200
        assert r2.status_code == 200

    def test_create_with_unknown_access_group_404(self, client, auth_headers):
        r = client.post(
            "/api/registration-keys",
            json={
                "name": "bad-group",
                "access_group_id": "00000000-0000-0000-0000-000000000abc",
            },
            headers=auth_headers,
        )
        assert r.status_code == 404

    def test_delete(self, client, auth_headers):
        created = client.post(
            "/api/registration-keys",
            json={"name": "to-delete"},
            headers=auth_headers,
        ).json()
        r = client.delete(
            f"/api/registration-keys/{created['id']}", headers=auth_headers
        )
        assert r.status_code == 200


class TestRegistrationKeyEnrollmentFlow:
    """End-to-end:  the agent's /host/register endpoint validates a
    registration_key against the RegistrationKey table, enrolls the
    new host into the matching access group, and applies auto_approve
    when the key allows it."""

    def test_register_without_key_works_pending(self, client, auth_headers):
        """Sanity:  no registration_key → host created with pending
        approval, same as before Phase 8.1."""
        r = client.post(
            "/host/register",
            json={
                "active": True,
                "fqdn": "no-key-host.example.com",
                "hostname": "no-key-host",
                "ipv4": "10.0.0.1",
            },
        )
        assert r.status_code == 200
        assert r.json()["approval_status"] == "pending"

    def test_register_with_invalid_key_403(self, client, auth_headers):
        r = client.post(
            "/host/register",
            json={
                "active": True,
                "fqdn": "bad-key.example.com",
                "hostname": "bad-key",
                "ipv4": "10.0.0.2",
                "registration_key": "definitely-not-a-real-key",
            },
        )
        assert r.status_code == 403

    def test_register_with_valid_auto_approve_key(self, client, auth_headers):
        """Create a registration key with auto_approve=True; verify a
        subsequent /host/register that presents that key creates an
        APPROVED host (not pending)."""
        key_resp = client.post(
            "/api/registration-keys",
            json={"name": "auto-key", "auto_approve": True},
            headers=auth_headers,
        )
        assert key_resp.status_code == 200
        secret = key_resp.json()["key"]

        r = client.post(
            "/host/register",
            json={
                "active": True,
                "fqdn": "auto-approved-host.example.com",
                "hostname": "auto-approved-host",
                "ipv4": "10.0.0.3",
                "registration_key": secret,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # The /host/register endpoint serializes the Host model, but the
        # exact key name varies by SQLAlchemy version (some include
        # ``approval_status``, others wrap fields).  Verify approval via
        # the list endpoint instead — that's the API surface operators use.
        list_resp = client.get("/api/hosts", headers=auth_headers)
        assert list_resp.status_code == 200
        matching = [
            h
            for h in list_resp.json()
            if h.get("fqdn") == "auto-approved-host.example.com"
        ]
        assert matching, "newly-registered host not in /api/hosts"
        assert matching[0].get("approval_status") == "approved", (
            f"expected approved, got {matching[0].get('approval_status')!r}; "
            f"full row: {matching[0]}"
        )

    def test_register_with_valid_non_auto_approve_key(self, client, auth_headers):
        """auto_approve=False:  the key validates, the host enrolls into
        any associated access group, but stays PENDING."""
        key_resp = client.post(
            "/api/registration-keys",
            json={"name": "manual-key", "auto_approve": False},
            headers=auth_headers,
        )
        secret = key_resp.json()["key"]
        r = client.post(
            "/host/register",
            json={
                "active": True,
                "fqdn": "manual-key-host.example.com",
                "hostname": "manual-key-host",
                "ipv4": "10.0.0.4",
                "registration_key": secret,
            },
        )
        assert r.status_code == 200
        # See note in the auto-approve test:  verify via the /api/hosts
        # list endpoint, which reliably exposes approval_status.
        list_resp = client.get("/api/hosts", headers=auth_headers)
        matching = [
            h
            for h in list_resp.json()
            if h.get("fqdn") == "manual-key-host.example.com"
        ]
        assert matching
        assert matching[0].get("approval_status") == "pending"


class TestRegistrationKeyModel:
    """Unit tests for RegistrationKey.is_usable() — the gate the
    registration handler will use to accept/reject incoming agents."""

    def test_revoked_key_not_usable(self):
        from backend.persistence.models import RegistrationKey  # noqa: WPS433

        key = RegistrationKey(name="x", revoked=True, max_uses=None)
        assert key.is_usable() is False

    def test_expired_key_not_usable(self):
        from datetime import datetime, timedelta, timezone
        from backend.persistence.models import RegistrationKey  # noqa: WPS433

        key = RegistrationKey(
            name="x",
            revoked=False,
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(seconds=1),
        )
        assert key.is_usable() is False

    def test_max_uses_exceeded_not_usable(self):
        from backend.persistence.models import RegistrationKey  # noqa: WPS433

        key = RegistrationKey(name="x", revoked=False, max_uses=3, use_count=3)
        assert key.is_usable() is False

    def test_unrestricted_key_is_usable(self):
        from backend.persistence.models import RegistrationKey  # noqa: WPS433

        key = RegistrationKey(name="x", revoked=False, max_uses=None, use_count=0)
        assert key.is_usable() is True
