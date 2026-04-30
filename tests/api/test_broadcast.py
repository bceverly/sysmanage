"""
Tests for the Phase 8.5 broadcast endpoint.

Covers:
  - Auth gate.
  - Empty-fleet broadcast returns delivered_count=0 (not an error).
  - Tag-scoped broadcast validates the tag exists (404 on bad UUID).
  - Response carries the canonical fields the UI relies on.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name


class TestBroadcastAuth:
    def test_broadcast_requires_auth(self, client):
        r = client.post(
            "/api/broadcast", json={"broadcast_action": "refresh_inventory"}
        )
        assert r.status_code in [401, 403]


class TestBroadcastBasic:
    def test_broadcast_to_empty_fleet_returns_zero(self, client, auth_headers):
        """No connected agents in the test harness — broadcast must
        still return 200 with delivered_count=0, NEVER 500."""
        r = client.post(
            "/api/broadcast",
            json={"broadcast_action": "refresh_inventory"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["broadcast_action"] == "refresh_inventory"
        assert body["delivered_count"] == 0
        assert "broadcast_id" in body
        assert "elapsed_ms" in body
        assert body["target_filter"] == "all"

    def test_broadcast_with_message_payload(self, client, auth_headers):
        r = client.post(
            "/api/broadcast",
            json={
                "broadcast_action": "banner",
                "message": "scheduled maintenance starts in 5 minutes",
            },
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json()["broadcast_action"] == "banner"

    def test_broadcast_with_unknown_tag_returns_404(self, client, auth_headers):
        r = client.post(
            "/api/broadcast",
            json={
                "broadcast_action": "refresh_inventory",
                "tag_id": "00000000-0000-0000-0000-000000000abc",
            },
            headers=auth_headers,
        )
        assert r.status_code == 404

    def test_broadcast_with_invalid_tag_uuid_returns_400(self, client, auth_headers):
        r = client.post(
            "/api/broadcast",
            json={
                "broadcast_action": "refresh_inventory",
                "tag_id": "not-a-uuid",
            },
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_broadcast_action_required(self, client, auth_headers):
        """Empty broadcast_action → 422 from Pydantic; can't accidentally
        send a meaningless broadcast to the whole fleet."""
        r = client.post(
            "/api/broadcast",
            json={"broadcast_action": ""},
            headers=auth_headers,
        )
        assert r.status_code == 422

    def test_broadcast_platform_filter_accepted(self, client, auth_headers):
        """Platform-only filter (no tag) routes through
        ``broadcast_to_platform``; empty fleet → delivered=0."""
        r = client.post(
            "/api/broadcast",
            json={
                "broadcast_action": "refresh_inventory",
                "platform": "Linux",
            },
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json()["delivered_count"] == 0
        assert r.json()["target_filter"] == "platform:Linux"
