"""
Server-scoped configuration settings API — Phase 13.1.H.

Exposes the operational (C-bucket) ``sysmanage.yaml`` options that have moved
to the DB-backed Settings table so they can be edited in the UI
(Settings → Configuration) instead of by hand-editing YAML.  Each setting is
read **DB-first with a YAML fallback** (via ``settings_service``); a write
persists it to the ``server_configuration.settings`` bag.

The **email** group is per-tenant: when multi-tenancy is enabled and a tenant
is active (bound from the JWT by the active-tenant middleware), email settings
read/write the tenant's scope (``registry_tenant.settings`` + a per-tenant
OpenBAO path) instead of the server scope.  In single-tenant / collapsed mode
there is no active tenant, so email resolves to server scope — unchanged.

See ``docs/planning/config-classification.md``.
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.config import config, secrets_service, settings_service
from backend.persistence.tenant_context import get_active_tenant

logger = logging.getLogger(__name__)

router = APIRouter()


def _scoped_tenant(desc: dict):
    """Return the tenant to scope ``desc`` to, or None for server scope.

    Only the email group is per-tenant; everything else (jwt timeouts, mq
    tunables, …) is server-wide.  When multi-tenancy is disabled the active
    tenant is always None, so the email group resolves to server scope too —
    the single-tenant default, unchanged.
    """
    if desc.get("group") != "email":
        return None
    if not config.is_multitenancy_enabled():
        return None
    return get_active_tenant()


# Editable server-scoped settings.  ``yaml`` is the path into sysmanage.yaml
# used as the fallback when the DB has no value yet.
_SETTINGS: List[dict] = [
    {
        "key": "heartbeat_timeout",
        "type": "int",
        "group": "monitoring",
        "yaml": ["monitoring", "heartbeat_timeout"],
        "default": 5,
    },
    {
        "key": "max_failed_logins",
        "type": "int",
        "group": "security",
        "yaml": ["security", "max_failed_logins"],
        "default": 5,
    },
    {
        "key": "account_lockout_duration",
        "type": "int",
        "group": "security",
        "yaml": ["security", "account_lockout_duration"],
        "default": 15,
    },
    {
        "key": "jwt_auth_timeout",
        "type": "int",
        "group": "security",
        "yaml": ["security", "jwt_auth_timeout"],
        "default": 3600,
    },
    {
        "key": "jwt_refresh_timeout",
        "type": "int",
        "group": "security",
        "yaml": ["security", "jwt_refresh_timeout"],
        "default": 86400,
    },
    {
        "key": "cookie_domain",
        "type": "str",
        "group": "security",
        "yaml": ["security", "cookie_domain"],
        "default": "",
    },
    {
        "key": "mq_expiration_minutes",
        "type": "int",
        "group": "message_queue",
        "yaml": ["message_queue", "expiration_timeout_minutes"],
        "default": 60,
    },
    {
        "key": "mq_cleanup_minutes",
        "type": "int",
        "group": "message_queue",
        "yaml": ["message_queue", "cleanup_interval_minutes"],
        "default": 30,
    },
    {
        "key": "email_enabled",
        "type": "bool",
        "group": "email",
        "yaml": ["email", "enabled"],
        "default": False,
    },
    {
        "key": "email_host",
        "type": "str",
        "group": "email",
        "yaml": ["email", "smtp", "host"],
        "default": "",
    },
    {
        "key": "email_port",
        "type": "int",
        "group": "email",
        "yaml": ["email", "smtp", "port"],
        "default": 587,
    },
    {
        "key": "email_use_tls",
        "type": "bool",
        "group": "email",
        "yaml": ["email", "smtp", "use_tls"],
        "default": True,
    },
    {
        "key": "email_use_ssl",
        "type": "bool",
        "group": "email",
        "yaml": ["email", "smtp", "use_ssl"],
        "default": False,
    },
    {
        "key": "email_username",
        "type": "str",
        "group": "email",
        "yaml": ["email", "smtp", "username"],
        "default": "",
    },
    {
        "key": "email_from_address",
        "type": "str",
        "group": "email",
        "yaml": ["email", "from_address"],
        "default": "",
    },
    {
        "key": "email_from_name",
        "type": "str",
        "group": "email",
        "yaml": ["email", "from_name"],
        "default": "",
    },
    # Secret: the SMTP password lives in OpenBAO, never in the settings DB.
    # Its value is never returned to the UI (write-only); a blank submission
    # leaves the stored secret unchanged.
    {
        "key": "email_password",
        "type": "secret",
        "group": "email",
        "secret_name": "smtp_password",  # nosec B105 - OpenBAO key name, not a secret
        "yaml": ["email", "smtp", "password"],
        "default": "",
    },
]
_BY_KEY = {s["key"]: s for s in _SETTINGS}


def _yaml_value(path: List[str]) -> Any:
    node: Any = config.get_config()
    for part in path:
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _secret_configured(desc: dict) -> bool:
    """True when a secret value exists (OpenBAO or the YAML fallback)."""
    tenant_id = _scoped_tenant(desc)
    if tenant_id and secrets_service.get_tenant_secret(
        tenant_id, desc["secret_name"], default=None
    ):
        return True
    value = secrets_service.get_secret(
        desc["secret_name"],
        lambda: _yaml_value(desc["yaml"]),
        default="",
    )
    return bool(value)


def _effective(desc: dict) -> Any:
    if desc["type"] == "secret":
        # Never return a secret's value to the UI — write-only.
        return ""
    tenant_id = _scoped_tenant(desc)
    if tenant_id:
        tenant_value = settings_service.get_tenant_setting(
            tenant_id, desc["key"], default=None
        )
        if tenant_value is not None:
            return tenant_value
    return settings_service.get_setting(
        desc["key"],
        lambda: _yaml_value(desc["yaml"]),
        default=desc["default"],
    )


def _coerce(value_type: str, value: Any) -> Any:
    if value_type == "int":
        return int(value)
    if value_type == "bool":
        return bool(value)
    return str(value) if value is not None else ""


class SettingItem(BaseModel):
    key: str
    group: str
    type: str
    value: Any
    # Only meaningful for secret-typed settings: whether a value is already
    # stored (so the UI can show "configured" without revealing the secret).
    configured: bool = False


class SettingsResponse(BaseModel):
    settings: List[SettingItem]


class UpdateSettingsRequest(BaseModel):
    settings: Dict[str, Any]


def _all_items() -> List[SettingItem]:
    items = []
    for d in _SETTINGS:
        is_secret = d["type"] == "secret"
        items.append(
            SettingItem(
                key=d["key"],
                group=d["group"],
                type=d["type"],
                value=_effective(d),
                configured=_secret_configured(d) if is_secret else False,
            )
        )
    return items


@router.get(
    "/api/settings",
    dependencies=[Depends(JWTBearer())],
)
async def get_settings(_user: str = Depends(get_current_user)) -> SettingsResponse:
    """Return the editable server settings with their current effective values."""
    return SettingsResponse(settings=_all_items())


def _store_secret(desc: dict, tenant_id, value: str) -> None:
    """Persist a secret setting to OpenBAO (tenant-scoped or server-global).

    A blank value is a no-op so the stored secret is left unchanged.
    """
    if not value:
        return
    if tenant_id:
        secrets_service.store_tenant_secrets(tenant_id, {desc["secret_name"]: value})
    else:
        secrets_service.store_config_secrets({desc["secret_name"]: value})


def _store_setting(desc: dict, tenant_id, key: str, value) -> None:
    """Persist a non-secret setting to the DB Settings table."""
    coerced = _coerce(desc["type"], value)
    if tenant_id:
        settings_service.set_tenant_setting(tenant_id, key, coerced)
    else:
        settings_service.set_setting(key, coerced)


@router.put(
    "/api/settings",
    dependencies=[Depends(JWTBearer())],
)
async def update_settings(
    payload: UpdateSettingsRequest,
    _user: str = Depends(get_current_user),
) -> SettingsResponse:
    """Persist provided settings (unknown keys ignored).

    Non-secret settings go to the DB Settings table; secrets (the SMTP
    password) go to OpenBAO.  A blank secret leaves the stored value unchanged.
    """
    for key, value in payload.settings.items():
        desc = _BY_KEY.get(key)
        if desc is None:
            continue
        tenant_id = _scoped_tenant(desc)
        if desc["type"] == "secret":
            _store_secret(desc, tenant_id, value)
        else:
            _store_setting(desc, tenant_id, key, value)
    return SettingsResponse(settings=_all_items())
