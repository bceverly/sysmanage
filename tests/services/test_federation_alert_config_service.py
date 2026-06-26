"""
Tests for the Phase 12.1 operator-configurable alert thresholds
(``federation_alert_config_service``):

  * Defaults are returned when nothing is configured.
  * Overrides take effect; clearing one reverts it to the default.
  * Out-of-range overrides are rejected.
  * ``evaluate_with_config`` threads the effective thresholds into the
    alert sweep (a low offline-multiplier fires more readily).
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

import uuid
from datetime import timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.persistence.models.federation import FederationSite
from backend.services import federation_alert_config_service as cfg_svc
from backend.services import federation_alert_service as alert_svc


@pytest.fixture
def session():
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(
            engine,
            tables=[
                Base.metadata.tables["federation_sites"],
                Base.metadata.tables["federation_alert"],
                Base.metadata.tables["federation_alert_config"],
                Base.metadata.tables["federation_compliance_rollup"],
                Base.metadata.tables["federation_vulnerability_rollup"],
            ],
        )
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        with Session() as s:
            yield s
    finally:
        engine.dispose()


class TestEffectiveThresholds:
    def test_defaults_when_unset(self, session):
        eff = cfg_svc.get_effective_thresholds(session)
        assert eff["offline_multiplier"] == alert_svc.DEFAULT_OFFLINE_MULTIPLIER
        assert eff["compliance_threshold"] == alert_svc.DEFAULT_COMPLIANCE_THRESHOLD
        assert eff["critical_cve_threshold"] == alert_svc.DEFAULT_CRITICAL_CVE_THRESHOLD

    def test_partial_override_keeps_other_defaults(self, session):
        cfg_svc.update_config(session, {"compliance_threshold": 85.0})
        session.commit()
        eff = cfg_svc.get_effective_thresholds(session)
        assert eff["compliance_threshold"] == 85.0
        # untouched → still default
        assert eff["offline_multiplier"] == alert_svc.DEFAULT_OFFLINE_MULTIPLIER

    def test_clearing_override_reverts_to_default(self, session):
        cfg_svc.update_config(session, {"offline_multiplier": 2})
        session.commit()
        assert cfg_svc.get_effective_thresholds(session)["offline_multiplier"] == 2
        cfg_svc.update_config(session, {"offline_multiplier": None})
        session.commit()
        assert (
            cfg_svc.get_effective_thresholds(session)["offline_multiplier"]
            == alert_svc.DEFAULT_OFFLINE_MULTIPLIER
        )


class TestValidation:
    def test_rejects_out_of_range_compliance(self, session):
        with pytest.raises(ValueError):
            cfg_svc.update_config(session, {"compliance_threshold": 150.0})

    def test_rejects_zero_multiplier(self, session):
        with pytest.raises(ValueError):
            cfg_svc.update_config(session, {"offline_multiplier": 0})

    def test_ignores_unknown_keys(self, session):
        cfg_svc.update_config(session, {"bogus": 1})
        session.commit()
        # nothing blew up; effective set is still all-defaults
        eff = cfg_svc.get_effective_thresholds(session)
        assert eff["min_offline_seconds"] == alert_svc.DEFAULT_MIN_OFFLINE_SECONDS


class TestEvaluateWithConfig:
    def _enrolled_site(self, session):
        site = FederationSite(
            id=uuid.uuid4(),
            name="alpha",
            url="https://s",
            status="enrolled",
            sync_interval_seconds=300,
        )
        # Last synced an hour ago.
        site.last_sync_at = alert_svc._utcnow_naive() - timedelta(hours=1)
        session.add(site)
        session.commit()
        return site

    def test_config_threshold_changes_outcome(self, session):
        self._enrolled_site(session)
        # With defaults (multiplier 4 × 300s = 1200s, min 900s) an hour-old
        # sync is well past → offline fires.  Tighten min to a huge value so
        # it should NOT fire, proving the config is actually threaded in.
        cfg_svc.update_config(session, {"min_offline_seconds": 100000})
        session.commit()
        summary = cfg_svc.evaluate_with_config(session)
        session.commit()
        assert summary["opened"] == 0

    def test_default_config_fires_offline(self, session):
        self._enrolled_site(session)
        summary = cfg_svc.evaluate_with_config(session)
        session.commit()
        assert summary["opened"] >= 1
