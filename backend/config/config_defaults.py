# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Fill in every configuration default, in one place.

Split out of ``backend/config/config.py`` on 2026-08-12: that module reached
the repository's 1000-line ceiling, and this block -- "take whatever the admin
wrote and make it complete" -- is the one self-contained thing in it.

The rule the whole file follows: a partial config must work.  Every optional
section is created when absent and every key inside it defaulted, so an
operator only writes what they want to change.  The single exception is the
database connection, which cannot be guessed and therefore fails loudly.
"""

import sys

DEFAULTS = {
    "api": {"host": "localhost", "port": 8080},
    "webui": {"host": "localhost", "port": 3000},
    "monitoring": {"heartbeat_timeout": 5},
    "security": {
        "max_failed_logins": 5,
        "account_lockout_duration": 15,
        "jwt_algorithm": "HS256",
        # Previously REQUIRED keys (KeyError if absent); defaulted so a
        # minimal config still starts.
        "jwt_auth_timeout": 3600,
        "jwt_refresh_timeout": 86400,
    },
    "logging": {
        "level": "INFO|WARNING|ERROR|CRITICAL",
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    },
    "message_queue": {
        "expiration_timeout_minutes": 60,
        "cleanup_interval_minutes": 30,
    },
    "vault": {
        "enabled": False,
        "url": "http://localhost:8200",
        "token": "",  # nosec B105
        "mount_path": "secret",
        # Phase 13.1.C: OpenBAO's database secrets engine, which brokers
        # dynamic per-tenant DB credentials.
        "database_mount_path": "database",
        "timeout": 30,
        "verify_ssl": True,
        "dev_mode": False,
    },
    "multitenancy": {
        "enabled": False,
        # Phase 13.1: lets the control-plane UI create the tenant database +
        # OpenBAO role itself.  OFF by default -- it requires the server to
        # hold a scoped provisioning identity, so security-strict deployments
        # keep provisioning operator/CLI-only.
        "self_service_provisioning": False,
    },
    "email": {
        "enabled": False,
        "smtp": {
            "host": "localhost",
            "port": 587,
            "use_tls": True,
            "use_ssl": False,
            "username": "",
            "password": "",  # nosec B105
            "timeout": 30,
        },
        "from_address": "noreply@localhost",
        "from_name": "SysManage System",
        "templates": {"subject_prefix": "[SysManage]"},
    },
    "license": {
        "key": "",
        "phone_home_url": "https://license.sysmanage.org",
        "phone_home_interval_hours": 24,
        "modules_path": "/var/lib/sysmanage/modules",
    },
    # Phase 12 air-gap manifest signing/verification key locations.  Zero-touch
    # by default: the collector auto-generates an ed25519 key here on first use.
    "airgap": {
        "signing_key_file": "/var/lib/sysmanage/airgap/collector-ed25519.pem",
        "collector_public_key_dir": "/var/lib/sysmanage/airgap/trusted-collectors",
        "verify_strict": True,
    },
    "geo_lookup": {
        "enabled": True,
        "database_path": "/var/lib/sysmanage/geoip/GeoLite2-City.mmdb",
        "maxmind_license_key": "",
        "refresh_interval_hours": 168,
        "ipapi_fallback_enabled": True,
    },
}


def _fill(section: dict, defaults: dict) -> None:
    """Recursively add missing keys WITHOUT overwriting what the operator set.

    Only absent keys are filled: a value the operator wrote -- including a
    falsy one like ``0``, ``""`` or ``False`` -- always wins.  That is why this
    tests membership rather than truthiness.
    """
    for key, value in defaults.items():
        if isinstance(value, dict):
            if not isinstance(section.get(key), dict):
                section[key] = {}
            _fill(section[key], value)
        elif key not in section:
            section[key] = value


def apply_defaults(config: dict, config_path: str) -> dict:
    """Normalise ``config`` in place and return it.

    The defaults themselves live in the ``DEFAULTS`` table above rather than in
    a chain of ``if key not in section`` branches -- there were roughly forty of
    them, which is data wearing control flow, and every new setting added one
    more branch to a function nobody could read.

    Args:
        config: the parsed YAML mapping.
        config_path: only used in error messages, so the operator is told
            WHICH file is wrong -- they are usually looking at a config a
            package wrote, not one they authored.
    """
    _fill(config, DEFAULTS)

    # The connection is the one thing with no sensible default -- guessing
    # a database password is not a kindness.  Say which file and which
    # section, because the reader is looking at a package's config they did
    # not write.
    if "registry" not in config and "database" not in config:
        print(
            f"ERROR: {config_path} has no 'registry:' section "
            "(or the deprecated 'database:' alias)."
        )
        print(
            "The server needs the bootstrap database connection: host, "
            "port, name, user, password."
        )
        sys.exit(1)

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

    if "registry" in config and "database" not in config:
        # New-style config: back-fill ``database`` so existing db.py / tooling
        # that reads ``config["database"]`` keeps working with zero changes.
        config["database"] = config["registry"]
    elif "database" in config and "registry" not in config:
        config["registry"] = config["database"]

    return config
