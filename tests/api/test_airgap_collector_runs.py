"""Tests for the one-shot air-gap collector runs API (Phase 11).

These mirror the ``test_airgap_collection_schedule.py`` style: every
test patches ``module_loader.get_module`` so the collector engine
appears loaded (so the 402 license gate doesn't fire) — the actual
engine is never invoked because this API only manages row lifecycle
and serves the produced ISO file.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from backend.api import airgap_collector_runs as runs_module


@contextmanager
def _engine(loaded=True):
    """Patch module_loader.get_module so the collector engine is
    deterministically loaded / unloaded per test."""

    def _resolver(name):
        if name == "airgap_collector_engine" and loaded:
            return MagicMock()
        return None

    with patch.object(runs_module.module_loader, "get_module", side_effect=_resolver):
        yield


class TestRunsAuth:
    def test_anonymous_rejected(self, client):
        # No auth header — JWTBearer should refuse before reaching the
        # handler, regardless of license state.
        r = client.post(
            "/api/v1/airgap/collector/runs",
            json={"iso_label": "x"},
        )
        assert r.status_code in (401, 403)


class TestRunsEngineGate:
    def test_list_returns_402_without_engine(self, client, auth_headers):
        with _engine(loaded=False):
            r = client.get("/api/v1/airgap/collector/runs", headers=auth_headers)
        assert r.status_code == 402

    def test_create_returns_402_without_engine(self, client, auth_headers):
        with _engine(loaded=False):
            r = client.post(
                "/api/v1/airgap/collector/runs",
                json={"iso_label": "x"},
                headers=auth_headers,
            )
        assert r.status_code == 402


class TestRunsCrud:
    def test_list_empty(self, client, auth_headers):
        with _engine():
            r = client.get("/api/v1/airgap/collector/runs", headers=auth_headers)
        assert r.status_code == 200
        assert r.json() == []

    def test_create_run(self, client, auth_headers):
        with _engine():
            r = client.post(
                "/api/v1/airgap/collector/runs",
                json={
                    "iso_label": "smoke-test",
                    "media_size_bytes": 700_000_000,
                    "include_cve": False,
                    "include_compliance": True,
                },
                headers=auth_headers,
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["iso_label"] == "smoke-test"
        assert body["status"] == "QUEUED"
        assert body["media_size_bytes"] == 700_000_000
        assert body["include_cve"] is False
        assert body["include_compliance"] is True
        # One-shot runs leave cron_schedule NULL — that's the whole
        # contract that distinguishes them from scheduled runs.
        assert body["cron_schedule"] is None
        assert body["id"]

    def test_create_uses_defaults(self, client, auth_headers):
        with _engine():
            r = client.post(
                "/api/v1/airgap/collector/runs",
                json={"iso_label": "defaults"},
                headers=auth_headers,
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["media_size_bytes"] == 4_700_000_000
        assert body["include_cve"] is True
        assert body["include_compliance"] is True

    def test_get_returns_404_for_unknown(self, client, auth_headers):
        with _engine():
            r = client.get(
                "/api/v1/airgap/collector/runs/" "00000000-0000-0000-0000-000000000000",
                headers=auth_headers,
            )
        assert r.status_code == 404

    def test_get_returns_400_for_bad_uuid(self, client, auth_headers):
        with _engine():
            r = client.get(
                "/api/v1/airgap/collector/runs/not-a-uuid",
                headers=auth_headers,
            )
        assert r.status_code == 400

    def test_delete_removes_row(self, client, auth_headers):
        with _engine():
            create = client.post(
                "/api/v1/airgap/collector/runs",
                json={"iso_label": "to-delete"},
                headers=auth_headers,
            )
            assert create.status_code == 200, create.text
            run_id = create.json()["id"]

            d = client.delete(
                f"/api/v1/airgap/collector/runs/{run_id}",
                headers=auth_headers,
            )
            assert d.status_code == 204

            g = client.get(
                f"/api/v1/airgap/collector/runs/{run_id}",
                headers=auth_headers,
            )
            assert g.status_code == 404

    def test_list_orders_newest_first(self, client, auth_headers):
        with _engine():
            first = client.post(
                "/api/v1/airgap/collector/runs",
                json={"iso_label": "first"},
                headers=auth_headers,
            ).json()
            second = client.post(
                "/api/v1/airgap/collector/runs",
                json={"iso_label": "second"},
                headers=auth_headers,
            ).json()
            rows = client.get(
                "/api/v1/airgap/collector/runs", headers=auth_headers
            ).json()
        ids = [r["id"] for r in rows]
        assert first["id"] in ids
        assert second["id"] in ids
        # second was created after first; newest-first ordering puts it
        # at (or before) the same position.
        assert ids.index(second["id"]) <= ids.index(first["id"])


class TestRunManifests:
    def test_list_manifests_empty(self, client, auth_headers):
        with _engine():
            run = client.post(
                "/api/v1/airgap/collector/runs",
                json={"iso_label": "no-manifests"},
                headers=auth_headers,
            ).json()
            r = client.get(
                f"/api/v1/airgap/collector/runs/{run['id']}/manifests",
                headers=auth_headers,
            )
        assert r.status_code == 200
        assert r.json() == []

    def test_list_manifests_404_for_unknown_run(self, client, auth_headers):
        with _engine():
            r = client.get(
                "/api/v1/airgap/collector/runs/"
                "00000000-0000-0000-0000-000000000000/manifests",
                headers=auth_headers,
            )
        assert r.status_code == 404


class TestRunDownload:
    def test_download_404_for_unknown_manifest(self, client, auth_headers):
        with _engine():
            r = client.get(
                "/api/v1/airgap/collector/manifests/"
                "00000000-0000-0000-0000-000000000000/download",
                headers=auth_headers,
            )
        assert r.status_code == 404

    def test_download_409_when_not_complete(self, client, auth_headers, test_db):
        # Seed a manifest row pointing at a not-yet-complete run, then
        # hit the download endpoint and expect 409 because the run is
        # still QUEUED.  We seed directly via the test DB sessionmaker
        # because the real engine is what would normally populate a
        # manifest row, and that's deliberately mocked out here.
        import uuid as _uuid

        from sqlalchemy.orm import sessionmaker

        SessionLocal = getattr(test_db, "_testing_sessionmaker", None) or sessionmaker(
            bind=test_db
        )
        with _engine():
            create = client.post(
                "/api/v1/airgap/collector/runs",
                json={"iso_label": "incomplete"},
                headers=auth_headers,
            )
            assert create.status_code == 200, create.text
            run_id = create.json()["id"]
            # Insert a manifest row via raw SQL — the shadow model lives
            # in conftest's TestBase but we don't have a handle to it
            # here, so we hit the table directly.
            manifest_id = str(_uuid.uuid4())
            with SessionLocal() as s:
                from sqlalchemy import text as _text

                s.execute(
                    _text(
                        "INSERT INTO airgap_media_manifest "
                        "(id, run_id, disc_index, disc_count, iso_path, "
                        " iso_sha256, iso_size_bytes, manifest_json, "
                        " signature, signer_fingerprint, "
                        " signature_algorithm, format_version) "
                        "VALUES (:id, :run_id, 1, 1, '/tmp/does-not-exist.iso',"
                        " 'a' * 64, 0, '{}', '', 'fp', 'ed25519', 1)"
                    ),
                    {"id": manifest_id, "run_id": run_id},
                )
                s.commit()
            r = client.get(
                f"/api/v1/airgap/collector/manifests/{manifest_id}/download",
                headers=auth_headers,
            )
        assert r.status_code == 409
        assert "not complete" in r.json()["detail"].lower()
