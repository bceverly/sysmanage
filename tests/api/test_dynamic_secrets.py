"""
Tests for the Phase 8.7 dynamic-secrets endpoints.

Vault is NOT enabled in the test harness, so the issue path is mocked
to simulate a successful OpenBAO write.  We exercise:

  - Auth gate.
  - Bad ``kind`` is rejected with 400.
  - TTL out of [60, 86400] is rejected by Pydantic.
  - Issue → secret returned EXACTLY ONCE; lease row stored without secret.
  - List filters by status / kind.
  - Revoke flips status from ACTIVE → REVOKED.
  - Reconcile transitions ACTIVE-but-expired rows to EXPIRED.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name

from datetime import datetime, timedelta, timezone
from unittest.mock import patch


def _mock_vault_post():
    """Patch the vault POST/DELETE so issue/revoke don't touch
    OpenBAO during tests."""
    return patch(
        "backend.services.dynamic_secrets.VaultService",
        autospec=True,
    )


class TestDynamicSecretsAuth:
    def test_issue_requires_auth(self, client):
        r = client.post(
            "/api/dynamic-secrets/issue",
            json={
                "name": "x",
                "kind": "token",
                "backend_role": "default",
            },
        )
        assert r.status_code in (401, 403)

    def test_list_requires_auth(self, client):
        r = client.get("/api/dynamic-secrets/leases")
        assert r.status_code in (401, 403)


class TestDynamicSecretsKinds:
    def test_kinds_endpoint(self, client, auth_headers):
        r = client.get("/api/dynamic-secrets/kinds", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        kinds = {k["kind"] for k in body["kinds"]}
        assert {"token", "database", "ssh"}.issubset(kinds)
        assert body["ttl"]["min"] == 60
        assert body["ttl"]["max"] == 86400


class TestDynamicSecretsIssue:
    def test_issue_token_returns_secret_once(self, client, auth_headers):
        with _mock_vault_post() as VS:
            VS.return_value.mount_path = "secret"
            VS.return_value._make_request.return_value = {}
            r = client.post(
                "/api/dynamic-secrets/issue",
                json={
                    "name": "ci-runner-creds",
                    "kind": "token",
                    "backend_role": "default",
                    "ttl_seconds": 600,
                },
                headers=auth_headers,
            )
        assert r.status_code == 200, r.text
        body = r.json()
        # Plaintext secret surfaced once.
        assert body["secret"]
        assert isinstance(body["secret"], str)
        assert len(body["secret"]) >= 16
        # Lease row carries metadata but NOT the secret.
        lease = body["lease"]
        assert lease["status"] == "ACTIVE"
        assert lease["kind"] == "token"
        assert "secret" not in lease  # never echoed back from the lease row
        assert lease["ttl_seconds"] == 600
        assert lease["expires_at"] is not None

    def test_issue_rejects_unknown_kind(self, client, auth_headers):
        r = client.post(
            "/api/dynamic-secrets/issue",
            json={
                "name": "x",
                "kind": "fairy-dust",
                "backend_role": "default",
            },
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_issue_rejects_ttl_below_floor(self, client, auth_headers):
        r = client.post(
            "/api/dynamic-secrets/issue",
            json={
                "name": "x",
                "kind": "token",
                "backend_role": "default",
                "ttl_seconds": 5,
            },
            headers=auth_headers,
        )
        # Pydantic ge=60 → 422.
        assert r.status_code == 422

    def test_issue_rejects_ttl_above_ceiling(self, client, auth_headers):
        r = client.post(
            "/api/dynamic-secrets/issue",
            json={
                "name": "x",
                "kind": "token",
                "backend_role": "default",
                "ttl_seconds": 999_999,
            },
            headers=auth_headers,
        )
        assert r.status_code == 422


class TestDynamicSecretsList:
    def test_list_empty_then_after_issue(self, client, auth_headers):
        # Make sure we can issue one and then see it in the list.
        with _mock_vault_post() as VS:
            VS.return_value.mount_path = "secret"
            VS.return_value._make_request.return_value = {}
            client.post(
                "/api/dynamic-secrets/issue",
                json={
                    "name": "list-target",
                    "kind": "token",
                    "backend_role": "default",
                    "ttl_seconds": 300,
                },
                headers=auth_headers,
            )
        r = client.get(
            "/api/dynamic-secrets/leases?status=ACTIVE", headers=auth_headers
        )
        assert r.status_code == 200
        names = [le["name"] for le in r.json()]
        assert "list-target" in names

    def test_list_rejects_unknown_status(self, client, auth_headers):
        r = client.get(
            "/api/dynamic-secrets/leases?status=NOT-A-STATUS",
            headers=auth_headers,
        )
        assert r.status_code == 400


class TestDynamicSecretsRevoke:
    def test_revoke_flips_status_to_revoked(self, client, auth_headers):
        with _mock_vault_post() as VS:
            VS.return_value.mount_path = "secret"
            VS.return_value._make_request.return_value = {}
            issue_resp = client.post(
                "/api/dynamic-secrets/issue",
                json={
                    "name": "to-revoke",
                    "kind": "token",
                    "backend_role": "default",
                    "ttl_seconds": 300,
                },
                headers=auth_headers,
            )
            lease_id = issue_resp.json()["lease"]["id"]

            r = client.post(
                f"/api/dynamic-secrets/leases/{lease_id}/revoke",
                headers=auth_headers,
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["lease"]["status"] == "REVOKED"
        assert body["lease"]["revoked_at"] is not None

    def test_revoke_unknown_lease_returns_404(self, client, auth_headers):
        r = client.post(
            "/api/dynamic-secrets/leases/00000000-0000-0000-0000-000000000abc/revoke",
            headers=auth_headers,
        )
        assert r.status_code == 404

    def test_revoke_invalid_uuid_returns_400(self, client, auth_headers):
        r = client.post(
            "/api/dynamic-secrets/leases/not-a-uuid/revoke",
            headers=auth_headers,
        )
        assert r.status_code == 400


class TestDynamicSecretsReconcile:
    def test_reconcile_transitions_expired_active_rows(
        self, client, auth_headers, session
    ):
        from backend.persistence import models

        # Insert an ACTIVE row with expires_at in the past.
        old = models.DynamicSecretLease(
            name="ancient",
            kind="token",
            backend_role="default",
            ttl_seconds=60,
            issued_at=datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(hours=2),
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(hours=1),
            status="ACTIVE",
        )
        session.add(old)
        session.commit()

        r = client.post("/api/dynamic-secrets/reconcile", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["transitioned_count"] >= 1

        session.refresh(old)
        assert old.status == "EXPIRED"
