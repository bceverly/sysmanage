# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for the route-collision guard (Phase 13.2.1).

The guard makes a silent route-shadow (two routers claiming the same
method+path — e.g. an OSS router and a Pro+ engine under a shared /api/v1
namespace) into a loud startup error.
"""

import pytest
from fastapi import FastAPI

from backend.startup.route_registration import check_route_collisions


def test_clean_app_passes():
    app = FastAPI()

    @app.get("/api/v1/secrets/types")
    def _types():
        return {}

    # Same prefix, DIFFERENT sub-path — the "C" model — must be fine.
    @app.get("/api/v1/secrets/leases")
    def _leases():
        return {}

    # Same path, different METHOD — not a collision.
    @app.post("/api/v1/secrets/types")
    def _create_type():
        return {}

    check_route_collisions(app)  # no raise


def test_real_app_has_no_collisions():
    import backend.main as m  # noqa: PLC0415

    check_route_collisions(m.app)  # the assembled OSS app must be clean


def test_duplicate_method_path_raises():
    app = FastAPI()

    @app.get("/api/v1/reports/view")
    def _oss_view():
        return {"src": "oss"}

    # Simulate a Pro+ engine claiming the exact same method+path.
    @app.get("/api/v1/reports/view")
    def _engine_view():
        return {"src": "engine"}

    # Default (non-strict): logs loudly, does NOT raise, returns the collisions.
    found = check_route_collisions(app)
    assert any(path == "/api/v1/reports/view" for (_method, path) in found)

    # strict=True: fails fast (for CI / dev).
    with pytest.raises(RuntimeError, match="Route collision"):
        check_route_collisions(app, strict=True)
