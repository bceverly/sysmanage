# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Operator-configurable federation alert thresholds (Phase 12.1 follow-up).

Persists overrides for the three built-in rollup-alert conditions in the
``federation_alert_config`` singleton row.  Any column left NULL falls
back to the corresponding ``DEFAULT_*`` in ``federation_alert_service``,
so an operator can override just one threshold without restating the rest.

The coordinator's alert tick reads the merged effective thresholds via
:func:`get_effective_thresholds` and feeds them to
``federation_alert_service.evaluate_and_fire``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.persistence.models.federation import (
    SINGLETON_FEDERATION_ALERT_CONFIG_ID,
    FederationAlertConfig,
)
from backend.services import federation_alert_service as alert_svc


def _get_or_create(session: Session) -> FederationAlertConfig:
    row = session.get(FederationAlertConfig, SINGLETON_FEDERATION_ALERT_CONFIG_ID)
    if row is None:
        row = FederationAlertConfig(id=SINGLETON_FEDERATION_ALERT_CONFIG_ID)
        session.add(row)
        session.flush()
    return row


def get_config(session: Session) -> Optional[FederationAlertConfig]:
    """Return the raw config row (may be None / hold NULL overrides)."""
    return session.get(FederationAlertConfig, SINGLETON_FEDERATION_ALERT_CONFIG_ID)


def get_effective_thresholds(session: Session) -> Dict[str, Any]:
    """The thresholds the alert tick should use: operator overrides where
    set, built-in defaults everywhere else.  Always returns a complete set.
    """
    row = get_config(session)
    return {
        "offline_multiplier": (
            row.offline_multiplier
            if row is not None and row.offline_multiplier is not None
            else alert_svc.DEFAULT_OFFLINE_MULTIPLIER
        ),
        "min_offline_seconds": (
            row.min_offline_seconds
            if row is not None and row.min_offline_seconds is not None
            else alert_svc.DEFAULT_MIN_OFFLINE_SECONDS
        ),
        "compliance_threshold": (
            row.compliance_threshold
            if row is not None and row.compliance_threshold is not None
            else alert_svc.DEFAULT_COMPLIANCE_THRESHOLD
        ),
        "critical_cve_threshold": (
            row.critical_cve_threshold
            if row is not None and row.critical_cve_threshold is not None
            else alert_svc.DEFAULT_CRITICAL_CVE_THRESHOLD
        ),
    }


def _validate(field: str, value: Any) -> Any:
    """Coerce + range-check one override.  ``None`` clears the override
    (reverts that threshold to the built-in default)."""
    if value is None:
        return None
    if field == "compliance_threshold":
        value = float(value)
        if not 0.0 <= value <= 100.0:
            raise ValueError("compliance_threshold must be between 0 and 100")
        return value
    value = int(value)
    if field == "offline_multiplier" and value < 1:
        raise ValueError("offline_multiplier must be >= 1")
    if field == "min_offline_seconds" and value < 0:
        raise ValueError("min_offline_seconds must be >= 0")
    if field == "critical_cve_threshold" and value < 0:
        raise ValueError("critical_cve_threshold must be >= 0")
    return value


_FIELDS = (
    "offline_multiplier",
    "min_offline_seconds",
    "compliance_threshold",
    "critical_cve_threshold",
)


def update_config(session: Session, overrides: Dict[str, Any]) -> FederationAlertConfig:
    """Apply operator overrides to the singleton.

    Only the four known threshold fields are honoured; unknown keys are
    ignored.  A field set to ``None`` clears that override (reverts to the
    built-in default).  Raises ``ValueError`` on an out-of-range value.
    Caller commits.
    """
    row = _get_or_create(session)
    for field in _FIELDS:
        if field in overrides:
            setattr(row, field, _validate(field, overrides[field]))
    return row


def evaluate_with_config(session: Session) -> Dict[str, int]:
    """Run the alert sweep using the persisted (or default) thresholds.

    Thin convenience for the coordinator engine tick so it doesn't have to
    know the threshold-merge logic.  Caller commits.
    """
    thresholds = get_effective_thresholds(session)
    return alert_svc.evaluate_and_fire(session, **thresholds)
