# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 13.1.F — per-tenant backup/RPO orchestration (OSS schema + read model).

SysManage tracks each tenant's backup schedule (RPO target) and runs an
operator-configured **external** backup command — pgBackRest / wal-g / a
``pg_dump`` wrapper — on that cadence (orchestrate-only: the backup bytes live
wherever that tool puts them, never inside SysManage).  This module holds the
OSS-side pieces:

  * reading the server-level backup command templates from ``sysmanage.yaml``
    (the commands are *bootstrap* config, never per-tenant operator-editable, so
    a tenant can't inject a command to run on the server);
  * the per-tenant RPO settings (target seconds + enable flag) stored in
    ``registry_tenant.settings``;
  * the pure RPO-compliance read model + safe command templating.

The orchestration that actually iterates tenants, runs the commands, and records
``registry_tenant_backup`` rows lives in the licensed ``multitenancy_engine``
(the moat); it imports the helpers here so the schedule math + templating stay
OSS-testable.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from backend.config import config as app_config
from backend.config.settings_service import get_tenant_setting, set_tenant_setting

# RPO compliance states — the read model the UI + alerting consume.
RPO_COMPLIANT = "compliant"
RPO_AT_RISK = "at_risk"
RPO_BREACHED = "breached"
RPO_UNKNOWN = "unknown"

# Per-tenant settings keys (in ``registry_tenant.settings``).
SETTING_RPO_SECONDS = "backup.rpo_seconds"
SETTING_ENABLED = "backup.enabled"

# Defaults when the server config / tenant leaves a value unset.
DEFAULT_RPO_SECONDS = 86400  # 24h
DEFAULT_FULL_VERIFY_INTERVAL = 604800  # 7d between scheduled full restore-verifies
DEFAULT_TICK_INTERVAL = 300  # orchestrator loop cadence (5 min)
# Within this fraction of the RPO target, a tenant is flagged "at risk" so an
# operator can act before the window is actually breached.
AT_RISK_FRACTION = 0.8

# The only placeholders an operator's command template may reference.  Templating
# substitutes from a fixed whitelist so a stray ``{}`` in the template can never
# pull an unintended attribute.
_TEMPLATE_KEYS = ("tenant_id", "slug", "host", "port", "dbname", "region")


@dataclass(frozen=True)
class BackupConfig:
    """Server-level (bootstrap) backup orchestration config.

    The three command templates are rendered per-tenant with the placeholders in
    :data:`_TEMPLATE_KEYS`.  ``backup_command`` being unset disables backup
    orchestration entirely (the tick becomes a logged no-op).
    """

    backup_command: Optional[str]
    verify_command: Optional[str]
    full_restore_command: Optional[str]
    default_rpo_seconds: int
    full_verify_interval_seconds: int
    tick_interval_seconds: int

    @property
    def enabled(self) -> bool:
        """Backups run only when an operator has configured a backup command."""
        return bool(self.backup_command)


def get_backup_config() -> BackupConfig:
    """Read the ``backup`` section of ``sysmanage.yaml`` into a BackupConfig.

    Tolerant of a missing/!malformed section — an absent ``backup.command``
    simply means orchestration is disabled.
    """
    try:
        raw = app_config.config.get("backup", {}) or {}
    except Exception:  # noqa: BLE001 — config read must never raise here
        raw = {}

    def _int(key: str, default: int) -> int:
        try:
            return int(raw.get(key, default))
        except (TypeError, ValueError):
            return default

    return BackupConfig(
        backup_command=(raw.get("command") or None),
        verify_command=(raw.get("verify_command") or None),
        full_restore_command=(raw.get("full_restore_command") or None),
        default_rpo_seconds=_int("default_rpo_seconds", DEFAULT_RPO_SECONDS),
        full_verify_interval_seconds=_int(
            "full_verify_interval_seconds", DEFAULT_FULL_VERIFY_INTERVAL
        ),
        tick_interval_seconds=_int("tick_interval_seconds", DEFAULT_TICK_INTERVAL),
    )


def rpo_status(
    rpo_seconds: Optional[int],
    last_success_at: Optional[datetime],
    now: datetime,
) -> str:
    """Classify a tenant's RPO compliance from its last successful backup.

    Pure read model (no I/O), so it is fully unit-tested OSS-side and shared by
    the engine + the control-plane API:

      * ``unknown``   — no RPO target (backups disabled / not configured)
      * ``breached``  — never backed up, or the last good backup is older than
                        the target
      * ``at_risk``   — within :data:`AT_RISK_FRACTION` of the target
      * ``compliant`` — comfortably inside the window
    """
    if not rpo_seconds or rpo_seconds <= 0:
        return RPO_UNKNOWN
    if last_success_at is None:
        return RPO_BREACHED
    age = (now - last_success_at).total_seconds()
    if age > rpo_seconds:
        return RPO_BREACHED
    if age >= rpo_seconds * AT_RISK_FRACTION:
        return RPO_AT_RISK
    return RPO_COMPLIANT


def tenant_rpo_seconds(tenant_id: str) -> Optional[int]:
    """The tenant's effective RPO target in seconds, or ``None`` if disabled.

    Falls back to the server-level ``default_rpo_seconds`` when the tenant has no
    explicit target; returns ``None`` when backups are disabled for the tenant so
    callers skip it entirely.
    """
    enabled = get_tenant_setting(tenant_id, SETTING_ENABLED, default=True)
    if not enabled:
        return None
    raw = get_tenant_setting(tenant_id, SETTING_RPO_SECONDS, default=None)
    if raw is None:
        return get_backup_config().default_rpo_seconds
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return get_backup_config().default_rpo_seconds
    return value if value > 0 else None


def set_tenant_backup_config(
    tenant_id: str,
    *,
    rpo_seconds: Optional[int] = None,
    enabled: Optional[bool] = None,
) -> None:
    """Persist a tenant's RPO target / enable flag (only the args provided).

    ``rpo_seconds`` of ``None`` is treated as "leave unchanged"; pass a value to
    set it.  Use :func:`clear_tenant_rpo` semantics by setting it to ``0`` if a
    caller wants to fall back to the server default.
    """
    if enabled is not None:
        set_tenant_setting(tenant_id, SETTING_ENABLED, bool(enabled))
    if rpo_seconds is not None:
        set_tenant_setting(tenant_id, SETTING_RPO_SECONDS, int(rpo_seconds))


def render_backup_command(template: str, context: Dict[str, object]) -> list:
    """Render a command template into an argv list (no shell).

    Only the whitelisted :data:`_TEMPLATE_KEYS` are substituted; any other
    ``{name}`` placeholder is left literal rather than raising, so a typo in the
    operator's template fails loudly at exec time instead of crashing the tick.

    The operator-controlled *template* is tokenized first (``shlex.split``), then
    each token is substituted — so a tenant-derived value (slug, dbname) can
    never introduce extra argv tokens or flags no matter what it contains.  The
    command runs with ``shell=False`` on this argv, so there is no shell
    interpolation surface either.
    """
    safe = {key: str(context.get(key, "")) for key in _TEMPLATE_KEYS}

    class _Defaulting(dict):
        def __missing__(self, key):  # noqa: D401 — leave unknown placeholders literal
            return "{" + key + "}"

    mapping = _Defaulting(safe)
    return [token.format_map(mapping) for token in shlex.split(template)]
