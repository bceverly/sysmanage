"""
Tests for backend/advisory/advisory_service.py — the OSS wrapper that delegates
to the Pro+ advisory_engine (Phase 14.1).  Mirrors test_vulnerability_service.py:
the engine is mocked, so this exercises the wrapper + license gating in isolation.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

from backend.advisory.advisory_service import AdvisoryService, AdvisoryServiceError

adv_service_module = sys.modules["backend.advisory.advisory_service"]


class TestAdvisoryServiceError:
    def test_error_message(self):
        assert str(AdvisoryServiceError("boom")) == "boom"

    def test_error_inheritance(self):
        assert isinstance(AdvisoryServiceError("x"), Exception)


class TestGetModule:
    def test_no_license_raises(self):
        with patch.object(adv_service_module, "license_service") as lic, patch.object(
            adv_service_module, "module_loader"
        ):
            lic.has_module.return_value = False
            with pytest.raises(AdvisoryServiceError) as exc:
                AdvisoryService()._get_module()
            assert "Pro+ license" in str(exc.value)

    def test_module_not_loaded_raises(self):
        with patch.object(adv_service_module, "license_service") as lic, patch.object(
            adv_service_module, "module_loader"
        ) as loader:
            lic.has_module.return_value = True
            loader.get_module.return_value = None
            with pytest.raises(AdvisoryServiceError) as exc:
                AdvisoryService()._get_module()
            assert "not loaded" in str(exc.value)

    def test_success_returns_engine(self):
        with patch.object(adv_service_module, "license_service") as lic, patch.object(
            adv_service_module, "module_loader"
        ) as loader:
            lic.has_module.return_value = True
            engine = MagicMock()
            loader.get_module.return_value = engine
            assert AdvisoryService()._get_module() is engine


class TestDelegation:
    """Each wrapper method delegates to engine._advisory_service."""

    def _patched(self, engine):
        session = MagicMock()
        session.__enter__.return_value = session
        session.__exit__.return_value = False
        svc = AdvisoryService()
        return (
            svc,
            patch.multiple(
                adv_service_module,
                license_service=MagicMock(has_module=MagicMock(return_value=True)),
                module_loader=MagicMock(get_module=MagicMock(return_value=engine)),
            ),
            session,
        )

    def test_compute_delegates(self):
        engine = MagicMock()
        engine._advisory_service.compute_applicable_advisories.return_value = {
            "applicable_count": 3
        }
        svc, patcher, session = self._patched(engine)
        with patcher, patch.object(svc, "_get_db_session", return_value=session):
            out = svc.compute_applicable_advisories("host-1")
        assert out["applicable_count"] == 3
        engine._advisory_service.compute_applicable_advisories.assert_called_once()

    def test_list_delegates(self):
        engine = MagicMock()
        engine._advisory_service.list_advisories.return_value = {
            "total": 0,
            "advisories": [],
        }
        svc, patcher, session = self._patched(engine)
        with patcher, patch.object(svc, "_get_db_session", return_value=session):
            out = svc.list_advisories(source="ubuntu", severity="HIGH")
        assert out["total"] == 0
        kwargs = engine._advisory_service.list_advisories.call_args.kwargs
        assert kwargs["source"] == "ubuntu"
        assert kwargs["severity"] == "HIGH"

    def test_fleet_summary_delegates(self):
        engine = MagicMock()
        engine._advisory_service.get_fleet_summary.return_value = {
            "total_applicable": 7
        }
        svc, patcher, session = self._patched(engine)
        with patcher, patch.object(svc, "_get_db_session", return_value=session):
            out = svc.get_fleet_summary()
        assert out["total_applicable"] == 7
