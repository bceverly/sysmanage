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
if not os.path.exists(CONFIG_PATH) and os.path.exists("sysmanage-dev.yaml"):
    CONFIG_PATH = "sysmanage-dev.yaml"
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
