# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 13.1.J — per-tenant edition gating in ``LicenseService``.

When a tenant is in scope, ``has_feature`` / ``has_module`` must gate down to
that tenant's edition even though the server's global license is broader (the
SaaS server is licensed at the top tier and physically hosts every engine; each
tenant is independently Community / Professional / Enterprise).

Resolution of *which* tenant is active and its edition lives in the licensed
multitenancy_engine; here we drive the OSS seam (``edition_for_active_tenant``)
directly to prove the gating math.
"""

# pylint: disable=protected-access,redefined-outer-name

from datetime import datetime, timedelta, timezone

import pytest

from backend.licensing.features import (
    TIER_FEATURES,
    TIER_MODULES,
    FeatureCode,
    LicenseTier,
)
from backend.licensing.license_service import LicenseService
from backend.licensing.validator import LicensePayload
from backend.services import tenant_edition

# A capability available to Professional (and up), and one that is Enterprise-only.
PRO_FEATURE = FeatureCode.HEALTH_ANALYSIS
ENT_ONLY_MODULE = next(
    iter(TIER_MODULES[LicenseTier.ENTERPRISE] - TIER_MODULES[LicenseTier.PROFESSIONAL])
)


@pytest.fixture
def enterprise_service():
    """A service whose GLOBAL license includes the full Enterprise surface."""
    svc = LicenseService()
    now = datetime.now(timezone.utc)
    svc._cached_license = LicensePayload(
        license_id="test-license",
        tier=LicenseTier.ENTERPRISE,
        features=[f.value for f in TIER_FEATURES[LicenseTier.ENTERPRISE]],
        modules=[m.value for m in TIER_MODULES[LicenseTier.ENTERPRISE]],
        expires_at=now + timedelta(days=365),
        issued_at=now,
        offline_days=30,
    )
    return svc


def _active_edition(monkeypatch, edition):
    monkeypatch.setattr(tenant_edition, "edition_for_active_tenant", lambda: edition)


class TestPerTenantEditionGating:
    def test_no_active_tenant_uses_global_license(
        self, enterprise_service, monkeypatch
    ):
        """Server scope (no tenant) — the global license governs, unchanged."""
        _active_edition(monkeypatch, None)
        assert enterprise_service.has_feature(PRO_FEATURE) is True
        assert enterprise_service.has_module(ENT_ONLY_MODULE) is True

    def test_enterprise_tenant_gets_full_surface(self, enterprise_service, monkeypatch):
        _active_edition(monkeypatch, "enterprise")
        assert enterprise_service.has_feature(PRO_FEATURE) is True
        assert enterprise_service.has_module(ENT_ONLY_MODULE) is True

    def test_professional_tenant_gated_below_enterprise(
        self, enterprise_service, monkeypatch
    ):
        """A Professional tenant keeps Pro features but not Enterprise-only ones."""
        _active_edition(monkeypatch, "professional")
        assert enterprise_service.has_feature(PRO_FEATURE) is True
        assert enterprise_service.has_module(ENT_ONLY_MODULE) is False

    def test_community_tenant_gets_no_proplus(self, enterprise_service, monkeypatch):
        _active_edition(monkeypatch, "community")
        assert enterprise_service.has_feature(PRO_FEATURE) is False
        assert enterprise_service.has_module(ENT_ONLY_MODULE) is False

    def test_unknown_edition_does_not_over_restrict(
        self, enterprise_service, monkeypatch
    ):
        """A garbage edition string must fail open to the global license, not
        silently lock a tenant out of everything."""
        _active_edition(monkeypatch, "bogus")
        assert enterprise_service.has_feature(PRO_FEATURE) is True

    def test_edition_cannot_exceed_global_license(
        self, enterprise_service, monkeypatch
    ):
        """Edition gating only ever NARROWS: an item the server isn't licensed
        for stays unavailable even for an Enterprise tenant."""
        enterprise_service._cached_license.modules = []
        _active_edition(monkeypatch, "enterprise")
        assert enterprise_service.has_module(ENT_ONLY_MODULE) is False
