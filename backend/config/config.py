"""
This module encapsulates the reading and processing of the config file
/etc/sysmanage.yaml and provides callers with a mechanism to access the
various properties specified therein.
"""

import os
import sys

import yaml

# Read/validate the configuration file
# Check for development config first, then fall back to system config
CONFIG_PATH = "/etc/sysmanage.yaml"
if os.path.exists("sysmanage-dev.yaml"):
    CONFIG_PATH = "sysmanage-dev.yaml"
    print(f"Using development config: {CONFIG_PATH}")

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
except yaml.YAMLError as exc:
    if hasattr(exc, "problem_mark"):
        mark = exc.problem_mark
        print(
            f"Error reading sysmanage.yaml on line {mark.line+1} in column {mark.column+1}"
        )
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
