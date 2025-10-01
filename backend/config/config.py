"""
This module encapsulates the reading and processing of the config file
/etc/sysmanage.yaml and provides callers with a mechanism to access the
various properties specified therein.
"""

import os
import sys

import yaml

# Read/validate the configuration file
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
        if not "host" in config["api"].keys():
            config["api"]["host"] = "localhost"
        if not "port" in config["api"].keys():
            config["api"]["port"] = 8443
        if not "host" in config["webui"].keys():
            config["webui"]["host"] = "localhost"
        if not "port" in config["webui"].keys():
            config["webui"]["port"] = 8080
        if not "monitoring" in config.keys():
            config["monitoring"] = {}
        if not "heartbeat_timeout" in config["monitoring"].keys():
            config["monitoring"]["heartbeat_timeout"] = 5
        # Security settings for account locking
        if not "max_failed_logins" in config["security"].keys():
            config["security"]["max_failed_logins"] = 5
        if not "account_lockout_duration" in config["security"].keys():
            config["security"]["account_lockout_duration"] = 15
        # Logging settings
        if not "logging" in config.keys():
            config["logging"] = {}
        if not "level" in config["logging"].keys():
            config["logging"]["level"] = "INFO|WARNING|ERROR|CRITICAL"
        if not "format" in config["logging"].keys():
            config["logging"][
                "format"
            ] = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        # Message queue settings
        if not "message_queue" in config.keys():
            config["message_queue"] = {}
        if not "expiration_timeout_minutes" in config["message_queue"].keys():
            config["message_queue"]["expiration_timeout_minutes"] = 60
        if not "cleanup_interval_minutes" in config["message_queue"].keys():
            config["message_queue"]["cleanup_interval_minutes"] = 30

        # Vault (OpenBAO) settings
        if not "vault" in config.keys():
            config["vault"] = {}
        if not "enabled" in config["vault"].keys():
            config["vault"]["enabled"] = False
        if not "url" in config["vault"].keys():
            config["vault"]["url"] = "http://localhost:8200"
        if not "token" in config["vault"].keys():
            config["vault"][
                "token"
            ] = ""  # nosec B105 - empty default, not a hardcoded token
        if not "mount_path" in config["vault"].keys():
            config["vault"]["mount_path"] = "secret"
        if not "timeout" in config["vault"].keys():
            config["vault"]["timeout"] = 30
        if not "verify_ssl" in config["vault"].keys():
            config["vault"]["verify_ssl"] = True
        if not "dev_mode" in config["vault"].keys():
            config["vault"]["dev_mode"] = False

        # Email settings
        if not "email" in config.keys():
            config["email"] = {}
        if not "enabled" in config["email"].keys():
            config["email"]["enabled"] = False
        if not "smtp" in config["email"].keys():
            config["email"]["smtp"] = {}
        if not "host" in config["email"]["smtp"].keys():
            config["email"]["smtp"]["host"] = "localhost"
        if not "port" in config["email"]["smtp"].keys():
            config["email"]["smtp"]["port"] = 587
        if not "use_tls" in config["email"]["smtp"].keys():
            config["email"]["smtp"]["use_tls"] = True
        if not "use_ssl" in config["email"]["smtp"].keys():
            config["email"]["smtp"]["use_ssl"] = False
        if not "username" in config["email"]["smtp"].keys():
            config["email"]["smtp"]["username"] = ""
        if not "password" in config["email"]["smtp"].keys():
            config["email"]["smtp"][
                "password"
            ] = ""  # nosec B105 - empty default, not a hardcoded password
        if not "timeout" in config["email"]["smtp"].keys():
            config["email"]["smtp"]["timeout"] = 30
        if not "from_address" in config["email"].keys():
            config["email"]["from_address"] = "noreply@localhost"
        if not "from_name" in config["email"].keys():
            config["email"]["from_name"] = "SysManage System"
        if not "templates" in config["email"].keys():
            config["email"]["templates"] = {}
        if not "subject_prefix" in config["email"]["templates"].keys():
            config["email"]["templates"]["subject_prefix"] = "[SysManage]"
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
