"""
This module encapsulates the reading and processing of the config file
/etc/sysmanage.yaml and provides callers with a mechanism to access the
various properties specified therein.
"""

import os
import sys

import yaml

# Read/validate the configuration file
# Check environment variable first (for snap/containers), then system config
CONFIG_PATH = os.environ.get("SYSMANAGE_CONFIG_PATH")
if not CONFIG_PATH:
    # Check for system config first (security), then fall back to development config
    if os.name == "nt":  # Windows
        CONFIG_PATH = r"C:\ProgramData\SysManage\sysmanage.yaml"
    else:  # Unix-like (Linux, macOS, BSD)
        CONFIG_PATH = "/etc/sysmanage.yaml"

# Fallback to development config if system config doesn't exist
# Check for sysmanage-dev.yaml first (user's local config), then .example
if not os.path.exists(CONFIG_PATH):
    if os.path.exists("sysmanage-dev.yaml"):
        CONFIG_PATH = "sysmanage-dev.yaml"
    elif os.path.exists("sysmanage-dev.yaml.example"):
        CONFIG_PATH = "sysmanage-dev.yaml.example"
    # Using development configuration as fallback

try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)
        # Handle empty/comments-only YAML files
        if config is None:
            print(
                f"ERROR: Configuration file {CONFIG_PATH} is empty or contains only comments"
            )
            print("Please configure the file with valid YAML settings")
            sys.exit(1)
        if "host" not in config["api"]:
            config["api"]["host"] = "localhost"
        if "port" not in config["api"]:
            config["api"]["port"] = 8443
        if "host" not in config["webui"]:
            config["webui"]["host"] = "localhost"
        if "port" not in config["webui"]:
            config["webui"]["port"] = 8080
        if "monitoring" not in config:
            config["monitoring"] = {}
        if "heartbeat_timeout" not in config["monitoring"]:
            config["monitoring"]["heartbeat_timeout"] = 5
        # Security settings for account locking
        if "max_failed_logins" not in config["security"]:
            config["security"]["max_failed_logins"] = 5
        if "account_lockout_duration" not in config["security"]:
            config["security"]["account_lockout_duration"] = 15
        if "jwt_algorithm" not in config["security"]:
            config["security"]["jwt_algorithm"] = "HS256"
        # JWT lifetimes were previously required keys (KeyError if absent);
        # give them sane defaults so a minimal config still works.
        if "jwt_auth_timeout" not in config["security"]:
            config["security"]["jwt_auth_timeout"] = 3600
        if "jwt_refresh_timeout" not in config["security"]:
            config["security"]["jwt_refresh_timeout"] = 86400
        # Logging settings
        if "logging" not in config:
            config["logging"] = {}
        if "level" not in config["logging"]:
            config["logging"]["level"] = "INFO|WARNING|ERROR|CRITICAL"
        if "format" not in config["logging"]:
            config["logging"][
                "format"
            ] = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        # Message queue settings
        if "message_queue" not in config:
            config["message_queue"] = {}
        if "expiration_timeout_minutes" not in config["message_queue"]:
            config["message_queue"]["expiration_timeout_minutes"] = 60
        if "cleanup_interval_minutes" not in config["message_queue"]:
            config["message_queue"]["cleanup_interval_minutes"] = 30

        # Vault (OpenBAO) settings
        if "vault" not in config:
            config["vault"] = {}
        if "enabled" not in config["vault"]:
            config["vault"]["enabled"] = False
        if "url" not in config["vault"]:
            config["vault"]["url"] = "http://localhost:8200"
        if "token" not in config["vault"]:
            config["vault"]["token"] = ""  # nosec B105
        if "mount_path" not in config["vault"]:
            config["vault"]["mount_path"] = "secret"
        # Phase 13.1.C: mount of OpenBAO's database secrets engine, which
        # brokers dynamic per-tenant DB credentials.
        if "database_mount_path" not in config["vault"]:
            config["vault"]["database_mount_path"] = "database"
        if "timeout" not in config["vault"]:
            config["vault"]["timeout"] = 30
        if "verify_ssl" not in config["vault"]:
            config["vault"]["verify_ssl"] = True
        if "dev_mode" not in config["vault"]:
            config["vault"]["dev_mode"] = False

        # Multi-tenancy (Phase 13.1) + registry config alias.
        #
        # Two normalizations, both designed so existing single-tenant /
        # homelab configs keep working untouched:
        #
        #   1. ``registry:`` is the new name for the ``database:`` block
        #      (it now means "how do I reach the registry / bootstrap
        #      DB?", not "the one app database").  v3.0 accepts BOTH:
        #      whichever the operator wrote, we mirror it onto the other
        #      key so callers reading either see the same connection.
        #      An old ``database:``-only config gets a deprecation
        #      warning nudging the rename; the alias is dropped in a
        #      later major.  In collapsed (homelab) mode they are the
        #      same connection anyway.
        #   2. ``multitenancy.enabled`` (default False) gates the whole
        #      feature.  When false the control-plane API does not mount,
        #      the partition resolver is hardwired to the one engine, and
        #      behavior is identical to today.
        if "registry" in config and "database" not in config:
            # New-style config: back-fill ``database`` so the existing
            # db.py / tooling that reads ``config["database"]`` keeps
            # working with zero changes.
            config["database"] = config["registry"]
        elif "database" in config and "registry" not in config:
            # Legacy config: honor it, mirror onto ``registry``, warn.
            config["registry"] = config["database"]
            print(
                "WARNING: the 'database:' config key is deprecated; rename it to "
                "'registry:' (the registry/bootstrap database). 'database:' is "
                "still honored for now and will be removed in a future major."
            )

        if "multitenancy" not in config:
            config["multitenancy"] = {}
        if "enabled" not in config["multitenancy"]:
            config["multitenancy"]["enabled"] = False
        # Self-service provisioning (Phase 13.1): lets the control-plane UI
        # create the tenant database + OpenBAO role itself, instead of an
        # operator running CLI steps.  OFF by default — it requires the server
        # to hold a scoped provisioning identity (see scripts/provision_bootstrap.py),
        # so security-strict deployments keep provisioning operator/CLI-only.
        if "self_service_provisioning" not in config["multitenancy"]:
            config["multitenancy"]["self_service_provisioning"] = False

        # Email settings
        if "email" not in config:
            config["email"] = {}
        if "enabled" not in config["email"]:
            config["email"]["enabled"] = False
        if "smtp" not in config["email"]:
            config["email"]["smtp"] = {}
        if "host" not in config["email"]["smtp"]:
            config["email"]["smtp"]["host"] = "localhost"
        if "port" not in config["email"]["smtp"]:
            config["email"]["smtp"]["port"] = 587
        if "use_tls" not in config["email"]["smtp"]:
            config["email"]["smtp"]["use_tls"] = True
        if "use_ssl" not in config["email"]["smtp"]:
            config["email"]["smtp"]["use_ssl"] = False
        if "username" not in config["email"]["smtp"]:
            config["email"]["smtp"]["username"] = ""
        if "password" not in config["email"]["smtp"]:
            config["email"]["smtp"]["password"] = ""  # nosec B105
        if "timeout" not in config["email"]["smtp"]:
            config["email"]["smtp"]["timeout"] = 30
        if "from_address" not in config["email"]:
            config["email"]["from_address"] = "noreply@localhost"
        if "from_name" not in config["email"]:
            config["email"]["from_name"] = "SysManage System"
        if "templates" not in config["email"]:
            config["email"]["templates"] = {}
        if "subject_prefix" not in config["email"]["templates"]:
            config["email"]["templates"]["subject_prefix"] = "[SysManage]"

        # Server role (Phase 12) is no longer read from YAML — it lives
        # in the ``server_configuration`` DB singleton and is set via
        # Settings → Server Role in the web UI.  Any leftover ``role:``
        # key in an old YAML file is harmlessly ignored.  See
        # ``backend/services/server_config_service.py`` and
        # ``get_server_role()`` below.

        # License (Pro+) settings
        if "license" not in config:
            config["license"] = {}
        if "key" not in config["license"]:
            config["license"]["key"] = ""  # No license by default (Community Edition)
        if "phone_home_url" not in config["license"]:
            config["license"]["phone_home_url"] = "https://license.sysmanage.org"
        if "phone_home_interval_hours" not in config["license"]:
            config["license"]["phone_home_interval_hours"] = 24
        if "modules_path" not in config["license"]:
            config["license"]["modules_path"] = "/var/lib/sysmanage/modules"

        # Phase 12: Air-gap manifest signing/verification key locations.
        #
        # Zero-touch by default: the collector auto-generates an ed25519
        # keypair at ``signing_key_file`` the first time the role is set
        # to ``collector``; the air-gap server bundle embeds the public
        # half so the repository side gets it for free.  All keys are
        # optional config overrides — the defaults below "just work" so
        # operators never have to set them.
        #
        #   signing_key_file          collector's ed25519 private PEM
        #   collector_public_key_dir  repository's keyring of trusted
        #                             collector public PEMs (a DIRECTORY,
        #                             not a file, so multiple collectors
        #                             / key rotation work — verify tries
        #                             each pubkey, matched by fingerprint)
        #   verify_strict             repository rejects unsigned / HMAC-
        #                             fallback envelopes when True
        if "airgap" not in config:
            config["airgap"] = {}
        if "signing_key_file" not in config["airgap"]:
            config["airgap"][
                "signing_key_file"
            ] = "/var/lib/sysmanage/airgap/collector-ed25519.pem"
        if "collector_public_key_dir" not in config["airgap"]:
            config["airgap"][
                "collector_public_key_dir"
            ] = "/var/lib/sysmanage/airgap/trusted-collectors"
        if "verify_strict" not in config["airgap"]:
            config["airgap"]["verify_strict"] = True

        # Phase 12.7: Host geo-location settings.
        #
        # The agent reports its public IP via heartbeat and the server
        # resolves it to (country, subdivision, city, lat/lon) via a
        # bundled MaxMind GeoLite2 database, with an ipapi.co fallback
        # only when the local DB misses.  Operators must supply a free
        # MaxMind license key for the GeoLite2 download — without one,
        # all lookups fall back to ipapi.co's 1k/day free tier.
        #
        # Defaults below are tuned for "works out of the box on a
        # standard internet-connected deployment, harmless on airgap":
        # enabled=True turns on the lookup chain; missing license_key
        # means GeoLite2 is skipped and ipapi.co serves all queries
        # (which silently degrades to country=unknown when the free
        # tier is exhausted).
        if "geo_lookup" not in config:
            config["geo_lookup"] = {}
        if "enabled" not in config["geo_lookup"]:
            config["geo_lookup"]["enabled"] = True
        if "database_path" not in config["geo_lookup"]:
            config["geo_lookup"][
                "database_path"
            ] = "/var/lib/sysmanage/geoip/GeoLite2-City.mmdb"
        if "maxmind_license_key" not in config["geo_lookup"]:
            # Empty by default — sites that haven't registered with
            # MaxMind get ipapi.co fallback only.  Set this to the
            # license key from https://www.maxmind.com/en/accounts/
            # to enable weekly GeoLite2 refresh.
            config["geo_lookup"]["maxmind_license_key"] = ""
        if "refresh_interval_hours" not in config["geo_lookup"]:
            # MaxMind publishes the GeoLite2 City DB on Tuesdays and
            # Fridays.  168 hours (7d) keeps us reasonably current
            # without thrashing their download endpoint.
            config["geo_lookup"]["refresh_interval_hours"] = 168
        if "ipapi_fallback_enabled" not in config["geo_lookup"]:
            # Operators who want pure local-only lookups (e.g.
            # privacy-conscious deployments or airgapped fleets)
            # can set this to False to disable the ipapi.co fallback.
            config["geo_lookup"]["ipapi_fallback_enabled"] = True
except yaml.YAMLError as exc:
    if hasattr(exc, "problem_mark"):
        mark = exc.problem_mark
        # Error reading configuration file
        sys.exit(1)
    else:
        sys.exit(1)


def get_config():
    """
    This function allows a caller to retrieve the config object.
    """
    return config


def _server_setting(key, yaml_getter, default=None):
    """Resolve a server-scoped operational setting (Phase 13.1.H).

    Reads the DB-backed Settings table first (via settings_service), falling
    back to the legacy ``sysmanage.yaml`` value with a one-time deprecation
    warning.  Late import keeps config.py free of a DB dependency at import
    time and avoids a cycle.  Best-effort: any failure yields the YAML value.
    """
    try:
        from backend.config import settings_service  # noqa: PLC0415

        return settings_service.get_setting(key, yaml_getter, default=default)
    except Exception:  # noqa: BLE001
        try:
            return yaml_getter()
        except Exception:  # noqa: BLE001
            return default


def _config_secret(name, yaml_getter, default=""):
    """Resolve a server-scoped secret (Phase 13.1.H, B-bucket).

    Reads the value from OpenBAO first (via secrets_service), falling back to the
    legacy ``sysmanage.yaml`` value with a one-time deprecation warning.  Late
    import keeps config.py DB/vault-free at import time.  Best-effort: any
    failure yields the YAML value.
    """
    try:
        from backend.config import secrets_service  # noqa: PLC0415

        return secrets_service.get_secret(name, yaml_getter, default=default)
    except Exception:  # noqa: BLE001
        try:
            return yaml_getter()
        except Exception:  # noqa: BLE001
            return default


def get_heartbeat_timeout_minutes():
    """
    Get the heartbeat timeout in minutes after which a host is considered down.
    """
    return _server_setting(
        "heartbeat_timeout",
        lambda: config["monitoring"]["heartbeat_timeout"],
        default=5,
    )


def get_max_failed_logins():
    """
    Get the maximum number of failed login attempts before account lockout.
    """
    return _server_setting(
        "max_failed_logins", lambda: config["security"]["max_failed_logins"], default=5
    )


def get_account_lockout_duration():
    """
    Get the account lockout duration in minutes.
    """
    return _server_setting(
        "account_lockout_duration",
        lambda: config["security"]["account_lockout_duration"],
        default=15,
    )


def _rate_limit_cfg():
    """Return the ``api.rate_limit`` config sub-dict (or empty)."""
    try:
        return config.get("api", {}).get("rate_limit", {}) or {}
    except Exception:  # noqa: BLE001 — never let config shape break the limiter
        return {}


def get_rate_limit_enabled() -> bool:
    """Whether the request rate-limiter is active (Phase 13.2).

    Read from the in-memory config (NOT the DB) so it adds no per-request query.
    Disabled by default: per-IP limiting can throttle all users behind a shared
    reverse-proxy IP, so operators opt in and tune limits per deployment.  The
    ``SYSMANAGE_RATE_LIMIT_ENABLED`` env var overrides config (handy for e2e).
    """
    env = os.getenv("SYSMANAGE_RATE_LIMIT_ENABLED")
    if env is not None:
        return env.strip().lower() in ("1", "true", "yes", "on")
    return bool(_rate_limit_cfg().get("enabled", False))


def get_rate_limit_requests() -> int:
    """Max requests allowed per client per window (Phase 13.2). Default 1000."""
    try:
        return int(_rate_limit_cfg().get("requests", 1000))
    except (TypeError, ValueError):
        return 1000


def get_rate_limit_window_seconds() -> int:
    """Length of the rate-limit window in seconds (Phase 13.2). Default 60."""
    try:
        return int(_rate_limit_cfg().get("window_seconds", 60))
    except (TypeError, ValueError):
        return 60


def get_jwt_auth_timeout():
    """
    Get the JWT auth-token lifetime in seconds.  Phase 13.1.H: server setting
    (DB-backed, editable in Settings → Configuration), with a one-release
    ``sysmanage.yaml`` fallback.
    """
    return int(
        _server_setting(
            "jwt_auth_timeout",
            lambda: config["security"]["jwt_auth_timeout"],
            default=3600,
        )
    )


def get_jwt_refresh_timeout():
    """
    Get the JWT refresh-token lifetime in seconds.  Phase 13.1.H: server setting
    (DB-backed), with a one-release ``sysmanage.yaml`` fallback.
    """
    return int(
        _server_setting(
            "jwt_refresh_timeout",
            lambda: config["security"]["jwt_refresh_timeout"],
            default=86400,
        )
    )


def get_cookie_domain():
    """
    Get the refresh-cookie ``Domain`` attribute, or ``None`` to scope the cookie
    to the serving host (RFC 6265 default — what most deployments want).  Phase
    13.1.H: server setting (DB-backed), with a one-release ``sysmanage.yaml``
    fallback.  An empty value is normalized to ``None``.
    """
    value = _server_setting(
        "cookie_domain",
        lambda: config["security"].get("cookie_domain"),
        default=None,
    )
    return value or None


def get_admin_password():
    """
    Get the recovery-account password.  Phase 13.1.H: B-bucket secret read from
    OpenBAO, with a one-release ``sysmanage.yaml`` fallback.  The recovery
    account (see ``backend/api/auth.py``) still authenticates against this value;
    sourcing it from OpenBAO keeps the recovery credential out of plaintext YAML.
    The recovery-account *userid* stays in YAML — it is a bootstrap identifier
    that must resolve even when the DB/vault is unavailable.
    """
    return _config_secret(
        "admin_password",
        lambda: config["security"].get("admin_password"),
        default="",
    )


def get_log_levels():
    """
    Get the pipe-separated logging levels configuration.
    """
    return config["logging"]["level"]


def get_log_format():
    """
    Get the logging format string.
    """
    return config["logging"]["format"]


def get_log_file():
    """
    Get the log file path if specified.
    """
    return config["logging"].get("file")


def _active_tenant():
    """Return the active tenant id for this request/context, or None.

    Set by the active-tenant middleware from the JWT when multi-tenancy is
    enabled; ``None`` in single-tenant / collapsed mode (the default).
    Best-effort: never raises.
    """
    try:
        from backend.persistence.tenant_context import (
            get_active_tenant,
        )  # noqa: PLC0415

        return get_active_tenant()
    except Exception:  # noqa: BLE001
        return None


def _smtp_password():
    """Resolve the SMTP password from OpenBAO, falling back to YAML.

    Phase 13.1.H / 13.1: the SMTP password is a secret (B-bucket) and a
    per-tenant concern; it moves to OpenBAO.  When a tenant is active, the
    tenant's secret takes precedence over the server/YAML fallback.
    """
    try:
        from backend.config import secrets_service  # noqa: PLC0415

        tenant_id = _active_tenant()
        if tenant_id:
            value = secrets_service.get_tenant_secret(
                tenant_id, "smtp_password", default=None
            )
            if value:
                return value
        return secrets_service.get_secret(
            "smtp_password",
            lambda: config.get("email", {}).get("smtp", {}).get("password", ""),
            default="",
        )
    except Exception:  # noqa: BLE001
        return config.get("email", {}).get("smtp", {}).get("password", "")


def _db_setting(key):
    """Return a setting's DB value, or None if unset/unavailable.

    Phase 13.1: when a tenant is active, the tenant-scoped value (in
    ``registry_tenant.settings``) takes precedence over the server-scoped
    value.  DB-only (no YAML fallback) so callers overlay it onto the existing
    config dict *only when an operator has set it* — leaving the structure
    untouched otherwise.
    """
    try:
        from backend.config import settings_service  # noqa: PLC0415

        tenant_id = _active_tenant()
        if tenant_id:
            value = settings_service.get_tenant_setting(tenant_id, key, default=None)
            if value is not None:
                return value
        return settings_service.get_setting(key, default=None)
    except Exception:  # noqa: BLE001
        return None


# (smtp key, settings key) pairs that the Configuration UI can override.
_EMAIL_SMTP_OVERLAYS = (
    ("host", "email_host"),
    ("port", "email_port"),
    ("use_tls", "email_use_tls"),
    ("use_ssl", "email_use_ssl"),
    ("username", "email_username"),
)
_EMAIL_TOP_OVERLAYS = (
    ("from_address", "email_from_address"),
    ("from_name", "email_from_name"),
)


def _overlay_smtp(smtp: dict) -> dict:
    """Overlay DB-stored SMTP fields + the OpenBAO password onto ``smtp``."""
    for smtp_key, db_key in _EMAIL_SMTP_OVERLAYS:
        value = _db_setting(db_key)
        if value is not None:
            smtp[smtp_key] = value
    password = _smtp_password()
    if password:
        smtp["password"] = password
    return smtp


def get_email_config():
    """
    Get the complete email configuration.

    Phase 13.1.H: SMTP server fields configured in Settings → Configuration
    override ``sysmanage.yaml``; the SMTP password resolves from OpenBAO.
    """
    cfg = dict(config["email"])
    smtp = _overlay_smtp(dict(cfg.get("smtp", {})))
    cfg["smtp"] = smtp
    for top_key, db_key in _EMAIL_TOP_OVERLAYS:
        value = _db_setting(db_key)
        if value is not None:
            cfg[top_key] = value
    return cfg


def is_email_enabled():
    """
    Check if email functionality is enabled.

    Phase 13.1.H / 13.1: email config is operational/tenant-scoped.  When a
    tenant is active its value wins; otherwise read the server Settings DB,
    then fall back to ``sysmanage.yaml``.
    """
    tenant_value = _db_setting("email_enabled")
    if tenant_value is not None:
        return bool(tenant_value)
    return bool(
        _server_setting(
            "email_enabled", lambda: config["email"]["enabled"], default=False
        )
    )


def get_smtp_config():
    """
    Get SMTP server configuration.

    Phase 13.1.H: server fields set in Settings → Configuration override
    ``sysmanage.yaml``; the password resolves from OpenBAO.
    """
    return _overlay_smtp(dict(config["email"]["smtp"]))


def get_registry_config():
    """Return the registry / bootstrap database connection config.

    Phase 13.1: prefers the ``registry:`` block, falling back to the
    deprecated ``database:`` alias.  In collapsed (homelab) mode these
    are the same connection.  This is the single bootstrap pointer — all
    per-tenant placement lives in the registry database as data, never
    in YAML.
    """
    return config.get("registry") or config.get("database")


def is_multitenancy_enabled() -> bool:
    """True when the multi-tenancy control plane is enabled (default False).

    When False (the default for homelab / on-prem / federated installs),
    the control-plane API does not mount and the partition resolver is
    hardwired to the single engine — behavior is identical to today.

    The ``SYSMANAGE_MULTITENANCY`` env var, when set, overrides
    ``sysmanage.yaml`` entirely — any explicit value wins. This is the escape
    hatch the e2e harness uses to force single-tenant mode
    (``SYSMANAGE_MULTITENANCY=false``) regardless of the box's config, so the
    Playwright suite never needs OpenBAO or provisioned tenant DBs. Mirrors the
    ``SYSMANAGE_DISABLE_EMAIL`` override used by the same harness.
    """
    override = os.environ.get("SYSMANAGE_MULTITENANCY")
    if override is not None:
        return override.strip().lower() in ("1", "true", "yes", "on")
    return bool(config.get("multitenancy", {}).get("enabled", False))


def is_self_service_provisioning_enabled() -> bool:
    """True when the control plane may provision tenant DBs itself (default False).

    Requires multi-tenancy to be enabled too.  When False, the auto-provision
    endpoint is refused and provisioning stays an operator/CLI task.
    """
    if not is_multitenancy_enabled():
        return False
    return bool(config.get("multitenancy", {}).get("self_service_provisioning", False))


def get_multitenancy_config():
    """Return the complete multitenancy configuration dict."""
    return config.get("multitenancy", {})


def get_vault_config():
    """
    Get the complete vault configuration.
    """
    return config["vault"]


def is_vault_enabled():
    """
    Check if vault functionality is enabled.
    """
    return config["vault"]["enabled"]


def get_vault_url():
    """
    Get the vault server URL.
    """
    return config["vault"]["url"]


def get_vault_token():
    """
    Get the vault authentication token.
    """
    return config["vault"]["token"]


def get_vault_mount_path():
    """
    Get the vault KV secrets engine mount path.
    """
    return config["vault"]["mount_path"]


def get_vault_database_mount_path():
    """
    Get the OpenBAO database-secrets-engine mount path (Phase 13.1.C).
    """
    return config.get("vault", {}).get("database_mount_path", "database")


def get_vault_timeout():
    """
    Get the vault connection timeout in seconds.
    """
    return config["vault"]["timeout"]


def is_vault_ssl_verification_enabled():
    """
    Check if SSL certificate verification is enabled for vault connections.
    """
    return config["vault"]["verify_ssl"]


def is_vault_dev_mode():
    """
    Check if vault is running in development mode.
    """
    return config["vault"]["dev_mode"]


def get_license_config():
    """
    Get the complete license configuration.
    """
    return config["license"]


def get_license_key():
    """
    Get the Pro+ license key.  Phase 13.1.H: secret — OpenBAO first, YAML fallback.
    """
    return _config_secret(
        "license_key", lambda: config.get("license", {}).get("key", ""), default=""
    )


def is_license_configured():
    """
    Check if a license key is configured.
    """
    return bool(get_license_key())


def get_license_phone_home_url():
    """
    Get the license phone-home URL.  Phase 13.1.H: server setting (DB), YAML fallback.
    """
    return _server_setting(
        "license_phone_home_url",
        lambda: config["license"]["phone_home_url"],
        default="https://license.sysmanage.io",
    )


def get_license_phone_home_interval():
    """
    Get the license phone-home interval in hours.  Phase 13.1.H: server setting.
    """
    return _server_setting(
        "license_phone_home_interval_hours",
        lambda: config["license"]["phone_home_interval_hours"],
        default=24,
    )


def get_license_modules_path():
    """
    Get the path for storing downloaded Pro+ modules.
    """
    return config["license"]["modules_path"]


def get_server_role():
    """
    Return the server role: ``standard``, ``collector``, or ``repository``.

    Phase 11 air-gap topology — same binary runs as either half of an
    air-gap pair, or as a standalone (``standard``) deployment.

    Phase 12: the role moved from ``sysmanage.yaml`` into the
    ``server_configuration`` DB singleton (set via Settings → Server
    Role).  We read it through the service, which defaults to
    ``standard`` if the DB isn't reachable yet.  Late import keeps the
    config module free of a DB dependency at import time.
    """
    from backend.services.server_config_service import (
        get_server_role as _db_get_server_role,
    )  # pylint: disable=import-outside-toplevel

    return _db_get_server_role()


def get_federation_role():
    """Return the federation role: ``none``, ``coordinator``, or ``site``.

    Phase 12 multi-site federation.  Independent of :func:`get_server_role`
    (a server can be an air-gap collector AND a federation site).  Lives in
    the ``server_configuration`` DB singleton (set via Settings → Server
    Role); defaults to ``none`` if the DB isn't reachable yet.
    """
    from backend.services.server_config_service import (
        get_federation_role as _db_get_federation_role,
    )  # pylint: disable=import-outside-toplevel

    return _db_get_federation_role()


def is_federation_coordinator() -> bool:
    """True when this server is a federation coordinator."""
    return get_federation_role() == "coordinator"


def is_federation_site() -> bool:
    """True when this server is a federation subordinate site."""
    return get_federation_role() == "site"


# Phase 12.7: Host geo-location config accessors.
#
# These intentionally return individual values rather than the dict
# so callers can't accidentally mutate the loaded config; matches the
# vault/license accessor pattern above.


def get_geo_lookup_config():
    """Return the complete geo_lookup configuration dict."""
    return config.get("geo_lookup", {})


def is_geo_lookup_enabled() -> bool:
    """Check if geo-location lookup is enabled.  Phase 13.1.H: server setting."""
    return bool(
        _server_setting(
            "geo_lookup_enabled",
            lambda: config.get("geo_lookup", {}).get("enabled", False),
            default=False,
        )
    )


def get_geo_lookup_database_path() -> str:
    """Filesystem path to the bundled GeoLite2-City.mmdb (bootstrap path — YAML)."""
    return config.get("geo_lookup", {}).get(
        "database_path", "/var/lib/sysmanage/geoip/GeoLite2-City.mmdb"
    )


def get_geo_lookup_maxmind_license_key() -> str:
    """MaxMind license key for GeoLite2 downloads.  Empty -> ipapi.co only.

    Phase 13.1.H: secret — OpenBAO first, YAML fallback.
    """
    return _config_secret(
        "maxmind_license_key",
        lambda: config.get("geo_lookup", {}).get("maxmind_license_key", ""),
        default="",
    )


def get_geo_lookup_refresh_interval_hours() -> int:
    """Hours between background-task GeoLite2 refresh runs (default 168 = 7d).

    Phase 13.1.H: server setting (DB), YAML fallback.
    """
    return int(
        _server_setting(
            "geo_lookup_refresh_interval_hours",
            lambda: config.get("geo_lookup", {}).get("refresh_interval_hours", 168),
            default=168,
        )
    )


def is_geo_lookup_ipapi_fallback_enabled() -> bool:
    """Whether to query ipapi.co when the local GeoLite2 DB misses.

    Phase 13.1.H: server setting (DB), YAML fallback.
    """
    return bool(
        _server_setting(
            "geo_lookup_ipapi_fallback_enabled",
            lambda: config.get("geo_lookup", {}).get("ipapi_fallback_enabled", True),
            default=True,
        )
    )


def is_collector():
    """True when this server is the public-side of an air-gap pair."""
    return get_server_role() == "collector"


def is_repository():
    """True when this server is the private-side of an air-gap pair."""
    return get_server_role() == "repository"


# Phase 12: air-gap manifest signing/verification key locations.


def get_airgap_signing_key_file() -> str:
    """Filesystem path to the collector's ed25519 private signing PEM."""
    return config.get("airgap", {}).get(
        "signing_key_file", "/var/lib/sysmanage/airgap/collector-ed25519.pem"
    )


def get_airgap_collector_public_key_dir() -> str:
    """Directory of trusted collector public-key PEMs (repository side).

    A directory rather than a single file so multiple collectors and
    key rotation work: the repository verifies a manifest against each
    pubkey in the dir, matched by the envelope's signer_fingerprint.
    """
    return config.get("airgap", {}).get(
        "collector_public_key_dir", "/var/lib/sysmanage/airgap/trusted-collectors"
    )


def get_federation_identity_key_file() -> str:
    """Filesystem path to this server's ed25519 federation identity PEM."""
    return config.get("federation", {}).get(
        "identity_key_file", "/var/lib/sysmanage/federation/identity-ed25519.pem"
    )


def get_federation_peer_public_key_dir() -> str:
    """Directory of trusted federation peer public-key PEMs.

    A directory (not a single file) so a coordinator can hold several
    sites' keys and vice versa, and key rotation just adds a new file.
    """
    return config.get("federation", {}).get(
        "peer_public_key_dir", "/var/lib/sysmanage/federation/trusted-peers"
    )


def get_federation_tls_cert_file() -> str:
    """Filesystem path to this server's federation TLS certificate PEM.

    A self-signed X.509 cert the enrollment handshake presents for mutual-TLS
    pinning (the private key sits next to it as ``<stem>-key.pem``).  Auto-
    generated on demand so the operator never has to mint or paste a cert.
    """
    return config.get("federation", {}).get(
        "tls_cert_file", "/var/lib/sysmanage/federation/identity-cert.pem"
    )


def is_https_enabled() -> bool:
    """True when the API is configured to serve HTTPS.

    The server runs TLS only when BOTH ``api.certFile`` and ``api.keyFile``
    are set (see ``backend/main.py``); otherwise it serves plain HTTP.
    """
    api = config.get("api", {}) or {}
    return bool(api.get("certFile") and api.get("keyFile"))


def is_dev_mode() -> bool:
    """True when this deployment is plain HTTP (no TLS) — treated as dev.

    Security checks that would impede local testing (e.g. federation
    certificate-pin enforcement) auto-relax in dev mode, so an operator
    running over HTTP never has to flip a switch.  Configure
    ``api.certFile`` + ``api.keyFile`` (i.e. run HTTPS) and the same checks
    enforce automatically.
    """
    return not is_https_enabled()


def federation_enforce_cert_pinning() -> bool:
    """Whether to ENFORCE federation cert/identity pinning on the wire.

    Auto-derived from the deployment posture: warn-only in dev (plain HTTP),
    enforced once the server runs HTTPS.  No dedicated config flag — HTTPS
    *is* the signal that this is a real deployment.
    """
    return is_https_enabled()


def is_airgap_verify_strict() -> bool:
    """When True, the repository rejects unsigned / HMAC-fallback manifests."""
    return bool(config.get("airgap", {}).get("verify_strict", True))
