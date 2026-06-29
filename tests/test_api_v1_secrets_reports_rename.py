"""
Phase 13.2.1 (option A) — OSS secrets/reports renamed under /api/v1.

The Pro+ secrets_engine/reporting_engine own /api/v1/secrets and /api/v1/reports
(same endpoint names), so OSS takes DISTINCT v1 names:

  * OSS secrets  -> /api/v1/stored-secrets   (+ deprecated /api/secrets alias)
  * OSS reports  -> /api/v1/reporting        (+ deprecated /api/reports alias)

This keeps the two editions collision-free (the route-collision guard would fire
otherwise) while preserving the old unversioned paths for one release.
"""

import pytest

# (new canonical, old alias) pairs that resolve param-free with the test user.
SECRETS_PAIRS = [
    ("/api/v1/stored-secrets", "/api/secrets"),
    ("/api/v1/stored-secrets/types", "/api/secrets/types"),
]


class TestSecretsRename:
    @pytest.mark.parametrize("new,old", SECRETS_PAIRS)
    def test_new_and_alias_match(self, client, new, old):
        rn = client.get(new)
        ro = client.get(old)
        assert rn.status_code != 404, f"{new} should be native"
        assert ro.status_code != 404, f"{old} alias should still work"
        assert rn.status_code == ro.status_code

    def test_new_canonical_is_200(self, client):
        assert client.get("/api/v1/stored-secrets").status_code == 200


class TestRenameInvariants:
    def test_distinct_from_proplus_names(self):
        import backend.main as m  # noqa: PLC0415

        paths = {r.path for r in m.app.routes if hasattr(r, "path")}
        # OSS canonical names present on both surfaces.
        assert "/api/v1/stored-secrets/types" in paths
        assert "/api/secrets/types" in paths
        assert "/api/v1/reporting/view/{report_type}" in paths
        assert "/api/reports/view/{report_type}" in paths

    def test_oss_did_not_take_proplus_names(self):
        # The OSS routers themselves must not register the bare Pro+ names.
        # (Checked via the routers' own paths, not the live app, since a sibling
        # test may mount the Pro+ stubs onto the shared app.)
        from backend.api import secrets  # noqa: PLC0415
        from backend.api.reports.endpoints import (
            router as reports_router,
        )  # noqa: PLC0415

        # reports router carries no baked /api prefix now (added at registration).
        assert reports_router.prefix == ""
        # secrets sub-routers expose relative paths (no /secrets baked in).
        secret_paths = {rt.path for r in secrets.ordered_routers for rt in r.routes}
        assert "/types" in secret_paths
        assert "/secrets/types" not in secret_paths
