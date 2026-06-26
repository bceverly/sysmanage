"""
Tests for the Phase 8.7 report-templates endpoint.

Covers:
  - Auth gate.
  - CRUD round-trip (create / list / read / update / delete).
  - Validation: unknown base_report_type → 400.
  - Validation: unknown field code for the chosen base type → 400.
  - GET /fields/{base} returns the catalog the frontend uses.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name


class TestReportTemplatesAuth:
    def test_list_requires_auth(self, client):
        r = client.get("/api/report-templates")
        assert r.status_code in (401, 403)

    def test_create_requires_auth(self, client):
        r = client.post(
            "/api/report-templates",
            json={"name": "x", "base_report_type": "registered-hosts"},
        )
        assert r.status_code in (401, 403)


class TestReportTemplatesCrud:
    def test_list_empty(self, client, auth_headers):
        r = client.get("/api/report-templates", headers=auth_headers)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_create_then_read_round_trip(self, client, auth_headers):
        payload = {
            "name": "executive-host-summary",
            "description": "Top-level host roll-up",
            "base_report_type": "registered-hosts",
            "selected_fields": ["fqdn", "os", "status", "last_seen"],
            "enabled": True,
        }
        r = client.post("/api/report-templates", json=payload, headers=auth_headers)
        assert r.status_code == 200, r.text
        created = r.json()
        assert created["name"] == "executive-host-summary"
        assert created["selected_fields"] == ["fqdn", "os", "status", "last_seen"]
        tid = created["id"]

        r2 = client.get(f"/api/report-templates/{tid}", headers=auth_headers)
        assert r2.status_code == 200
        assert r2.json()["id"] == tid

    def test_update_replaces_fields(self, client, auth_headers):
        r = client.post(
            "/api/report-templates",
            json={
                "name": "host-wide-network",
                "base_report_type": "registered-hosts",
                "selected_fields": ["fqdn", "ipv4", "ipv6"],
            },
            headers=auth_headers,
        )
        tid = r.json()["id"]

        r2 = client.put(
            f"/api/report-templates/{tid}",
            json={"selected_fields": ["fqdn", "status"]},
            headers=auth_headers,
        )
        assert r2.status_code == 200
        assert r2.json()["selected_fields"] == ["fqdn", "status"]

    def test_delete_removes_template(self, client, auth_headers):
        r = client.post(
            "/api/report-templates",
            json={
                "name": "throwaway",
                "base_report_type": "users-list",
                "selected_fields": ["userid"],
            },
            headers=auth_headers,
        )
        tid = r.json()["id"]

        r2 = client.delete(f"/api/report-templates/{tid}", headers=auth_headers)
        assert r2.status_code == 200

        r3 = client.get(f"/api/report-templates/{tid}", headers=auth_headers)
        assert r3.status_code == 404


class TestReportTemplatesValidation:
    def test_unknown_base_type_rejected(self, client, auth_headers):
        r = client.post(
            "/api/report-templates",
            json={
                "name": "junk",
                "base_report_type": "hot-takes",
                "selected_fields": [],
            },
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_unknown_field_code_rejected(self, client, auth_headers):
        r = client.post(
            "/api/report-templates",
            json={
                "name": "junk2",
                "base_report_type": "registered-hosts",
                "selected_fields": ["fqdn", "made_up_field"],
            },
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_get_fields_for_known_base_type(self, client, auth_headers):
        r = client.get(
            "/api/report-templates/fields/registered-hosts",
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["base_report_type"] == "registered-hosts"
        codes = {f["code"] for f in body["fields"]}
        assert "fqdn" in codes
        assert "ipv4" in codes

    def test_get_fields_for_unknown_base_type(self, client, auth_headers):
        r = client.get(
            "/api/report-templates/fields/no-such-thing", headers=auth_headers
        )
        assert r.status_code == 404

    def test_list_base_types(self, client, auth_headers):
        r = client.get("/api/report-templates/base-types", headers=auth_headers)
        assert r.status_code == 200
        types = r.json()["base_types"]
        assert "registered-hosts" in types
        assert "audit-log" in types
