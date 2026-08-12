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


def apply_defaults(config: dict, config_path: str) -> dict:
    """Normalise ``config`` in place and return it.

    Args:
        config: the parsed YAML mapping.
        config_path: only used in error messages, so the operator is told
            WHICH file is wrong -- they are usually looking at a config a
            package wrote, not one they authored.
    """
    # Default the SECTIONS, not just the keys inside them.
    #
    # Every key below already has a default, so the clear intent is that a
    # partial config works.  But the sections themselves were subscripted
    # directly, so a config that simply omitted one died at import with a
    # bare "KeyError: 'api'" -- no file name, no section name, no hint.
    # Six of the seven shipped installer/*/sysmanage.yaml.example files
    # omit api: and webui:, so the CentOS, openSUSE, macOS, Windows,
    # NetBSD and FreeBSD packages installed cleanly and then died on first
    # start.  Found 2026-08-10 by installing the FreeBSD package.
    #
    # ``monitoring``, ``logging``, ``message_queue`` and ``vault`` further
    # down already did exactly this; api/webui/security were the omissions.
    for _optional_section in ("api", "webui", "security"):
        if _optional_section not in config or config[_optional_section] is None:
            config[_optional_section] = {}

    if "host" not in config["api"]:
        config["api"]["host"] = "localhost"
    if "port" not in config["api"]:
        # 8080/3000, matching every shipped example, the nginx sample
        # (proxy_pass http://127.0.0.1:8080) and the rc.d default.  These
        # defaults used to be 8443/8080, which agreed with nothing else in
        # the tree -- harmless while omitting the section was fatal, but
        # now that a partial config loads, a wrong default would silently
        # produce a server the bundled reverse proxy cannot reach.
        config["api"]["port"] = 8080
    if "host" not in config["webui"]:
        config["webui"]["host"] = "localhost"
    if "port" not in config["webui"]:
        config["webui"]["port"] = 3000
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

    return config
