"""
Tests for the Phase 8.7 report-branding endpoint.

Covers:
  - Auth gate (no token → 401/403).
  - GET on a fresh DB returns the auto-created singleton (has_logo=False).
  - PUT updates company name + header text and persists across reads.
  - Logo upload accepts PNG and rejects oversized / wrong-MIME files.
  - GET /logo on a brandless DB returns 404.
  - DELETE /logo wipes the bytes and the GET round-trip drops back to 404.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name

import io


class TestReportBrandingAuth:
    def test_get_branding_requires_auth(self, client):
        r = client.get("/api/report-branding")
        assert r.status_code in (401, 403)

    def test_put_branding_requires_auth(self, client):
        r = client.put("/api/report-branding", json={"company_name": "X"})
        assert r.status_code in (401, 403)

    def test_logo_upload_requires_auth(self, client):
        r = client.post(
            "/api/report-branding/logo",
            files={"file": ("logo.png", io.BytesIO(b"\x89PNG"), "image/png")},
        )
        assert r.status_code in (401, 403)


class TestReportBrandingCrud:
    def test_get_creates_singleton_on_first_read(self, client, auth_headers):
        r = client.get("/api/report-branding", headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "company_name" in body
        assert "header_text" in body
        assert body["has_logo"] is False

    def test_put_updates_company_and_header(self, client, auth_headers):
        r = client.put(
            "/api/report-branding",
            json={"company_name": "Acme Corp", "header_text": "Internal Use"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["company_name"] == "Acme Corp"
        assert body["header_text"] == "Internal Use"

        # Re-read confirms persistence.
        r2 = client.get("/api/report-branding", headers=auth_headers)
        assert r2.json()["company_name"] == "Acme Corp"

    def test_put_with_empty_strings_clears_fields(self, client, auth_headers):
        client.put(
            "/api/report-branding",
            json={"company_name": "X", "header_text": "Y"},
            headers=auth_headers,
        )
        r = client.put(
            "/api/report-branding",
            json={"company_name": "", "header_text": ""},
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json()["company_name"] is None
        assert r.json()["header_text"] is None


class TestReportBrandingLogo:
    # Smallest valid PNG (1×1 transparent pixel) — encodes cleanly.
    _PNG_MIN = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "8900000a49444154789c63000100000500010d0a2db40000000049454e44ae42"
        "6082"
    )

    def test_get_logo_when_missing_returns_404(self, client, auth_headers):
        # Reset state first.
        client.delete("/api/report-branding/logo", headers=auth_headers)
        r = client.get("/api/report-branding/logo", headers=auth_headers)
        assert r.status_code == 404

    def test_upload_png_then_get_round_trip(self, client, auth_headers):
        files = {"file": ("logo.png", io.BytesIO(self._PNG_MIN), "image/png")}
        r = client.post("/api/report-branding/logo", headers=auth_headers, files=files)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["has_logo"] is True
        assert body["logo_mime_type"].startswith("image/png")

        r2 = client.get("/api/report-branding/logo", headers=auth_headers)
        assert r2.status_code == 200
        assert r2.headers["content-type"].startswith("image/png")
        assert r2.content == self._PNG_MIN

    def test_upload_rejects_non_image(self, client, auth_headers):
        files = {
            "file": (
                "payload.exe",
                io.BytesIO(b"MZ\x90\x00"),
                "application/octet-stream",
            ),
        }
        r = client.post("/api/report-branding/logo", headers=auth_headers, files=files)
        assert r.status_code == 400

    def test_upload_rejects_oversize(self, client, auth_headers):
        # 1 MB + 1 byte → over the cap.
        big = b"\x89PNG" + b"\x00" * (1 * 1024 * 1024)
        files = {"file": ("big.png", io.BytesIO(big), "image/png")}
        r = client.post("/api/report-branding/logo", headers=auth_headers, files=files)
        assert r.status_code == 413

    def test_delete_logo_removes_bytes(self, client, auth_headers):
        # Ensure a logo is present, then delete.
        files = {"file": ("logo.png", io.BytesIO(self._PNG_MIN), "image/png")}
        client.post("/api/report-branding/logo", headers=auth_headers, files=files)
        r = client.delete("/api/report-branding/logo", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["has_logo"] is False

        r2 = client.get("/api/report-branding/logo", headers=auth_headers)
        assert r2.status_code == 404
