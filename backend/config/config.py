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
            config["vault"][
                "token"
            ] = ""
        if "mount_path" not in config["vault"]:
            config["vault"]["mount_path"] = "secret"
        if "timeout" not in config["vault"]:
            config["vault"]["timeout"] = 30
        if "verify_ssl" not in config["vault"]:
            config["vault"]["verify_ssl"] = True
        if "dev_mode" not in config["vault"]:
            config["vault"]["dev_mode"] = False

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
            config["email"]["smtp"][
                "password"
            ] = ""
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

        # License (Pro+) settings
        if "license" not in config:
            config["license"] = {}
        if "key" not in config["license"]:
            config["license"]["key"] = ""  # No license by default (Community Edition)
        if "phone_home_url" not in config["license"]:
            config["license"]["phone_home_url"] = "https://license.sysmanage.io"
        if "phone_home_interval_hours" not in config["license"]:
            config["license"]["phone_home_interval_hours"] = 24
        if "modules_path" not in config["license"]:
            config["license"]["modules_path"] = "/var/lib/sysmanage/modules"
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


def get_heartbeat_timeout_minutes():
    """
    Get the heartbeat timeout in minutes after which a host is considered down.
    """
    return config["monitoring"]["heartbeat_timeout"]


def get_max_failed_logins():
    """
    Get the maximum number of failed login attempts before account lockout.
    """
    return config["security"]["max_failed_logins"]


def get_account_lockout_duration():
    """
    Get the account lockout duration in minutes.
    """
    return config["security"]["account_lockout_duration"]


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


def get_email_config():
    """
    Get the complete email configuration.
    """
    return config["email"]


def is_email_enabled():
    """
    Check if email functionality is enabled.
    """
    return config["email"]["enabled"]


def get_smtp_config():
    """
    Get SMTP server configuration.
    """
    return config["email"]["smtp"]


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
    Get the Pro+ license key.
    """
    return config["license"]["key"]


def is_license_configured():
    """
    Check if a license key is configured.
    """
    return bool(config["license"]["key"])


def get_license_phone_home_url():
    """
    Get the license phone-home URL.
    """
    return config["license"]["phone_home_url"]


def get_license_phone_home_interval():
    """
    Get the license phone-home interval in hours.
    """
    return config["license"]["phone_home_interval_hours"]


def get_license_modules_path():
    """
    Get the path for storing downloaded Pro+ modules.
    """
    return config["license"]["modules_path"]
