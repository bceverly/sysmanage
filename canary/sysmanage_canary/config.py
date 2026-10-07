# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The canary's configuration: loaded, checked and defaulted in one place.

A bad file is refused as a whole, with every problem listed -- never
half-applied (``sysmanage-canary --check-config`` prints the same list).
"""

import os
import stat
import sys
from typing import Any, Dict, List, Optional, Tuple

import yaml

if sys.platform == "win32":
    DEFAULT_PATH = os.path.join(
        os.environ.get("ProgramData", r"C:\ProgramData"),
        "SysManage",
        "sysmanage-canary.yaml",
    )
elif sys.platform == "darwin":
    DEFAULT_PATH = "/usr/local/etc/sysmanage-canary.yaml"
else:
    DEFAULT_PATH = "/etc/sysmanage-canary.yaml"

LANGUAGES = ("en", "de", "es", "fr", "it", "nl", "pt", "ru", "ja", "ko", "zh_CN", "zh_TW",
             "hi", "ar")  # fmt: skip
CHECKS = ("web_ui", "backend", "database", "network", "inbound_silence")


class ConfigError(Exception):
    """The configuration is unusable; ``problems`` lists every reason."""

    def __init__(self, problems: List[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


# key -> (type, default); a default of REQUIRED means the key must be given.
REQUIRED = object()
_COMMON = {
    "enabled": (bool, False),
    "interval_seconds": (int, 60),
    "timeout_seconds": (int, 10),
    "failures_before_alert": (int, 3),
}
_SCHEMA: Dict[str, Dict[str, Tuple[Any, Any]]] = {
    "web_ui": {**_COMMON, "url": (str, REQUIRED), "max_response_ms": (int, 5000),
               "verify_tls": (bool, True)},
    "backend": {**_COMMON, "url": (str, REQUIRED), "max_response_ms": (int, 2000),
                "verify_tls": (bool, True)},
    "database": {**_COMMON, "dsn": (str, REQUIRED), "max_response_ms": (int, 1000),
                 "max_connections_percent": (int, 85)},
    "network": {**_COMMON, "resolve": (list, []), "connect": (list, [])},
    "inbound_silence": {**_COMMON, "dsn": (str, None), "extra_dsns": (list, []),
                        "max_silence_minutes": (int, 30)},
}  # fmt: skip
_EMAIL = {
    "host": (str, REQUIRED), "port": (int, 587), "security": (str, "starttls"),
    "username": (str, None), "password": (str, None), "from": (str, REQUIRED),
    "to": (list, REQUIRED), "reminder_minutes": (int, 60), "timeout_seconds": (int, 30),
}  # fmt: skip
_HEARTBEAT = {"url": (str, None), "interval_seconds": (int, 300),
              "daily_email_hour": (int, None)}  # fmt: skip
_TOP = {"language", "server_name", "email", "heartbeat", "checks"}


def _section(name: str, raw: Any, schema: Dict[str, Tuple[Any, Any]],problems: List[str]) -> Dict[str, Any]:  # fmt: skip
    """``raw`` checked against ``schema``, defaults filled in."""
    out: Dict[str, Any] = {}
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        problems.append(f"{name}: must be a mapping")
        return out
    for key in sorted(set(raw) - set(schema)):
        problems.append(f"{name}.{key}: unknown setting")
    for key, (kind, default) in schema.items():
        if key not in raw or raw[key] is None:
            if default is REQUIRED:
                problems.append(f"{name}.{key}: required")
            out[key] = None if default is REQUIRED else default
            continue
        value = raw[key]
        # bool is an int in Python: refuse true/false where a number belongs.
        if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
            problems.append(
                f"{name}.{key}: must be {kind.__name__}, got {type(value).__name__}"
            )
            out[key] = None if default is REQUIRED else default
            continue
        out[key] = value
    return out


def _check_ranges(config: Dict[str, Any], problems: List[str]) -> None:
    email = config["email"]
    if email.get("security") not in ("starttls", "tls", "none"):
        problems.append("email.security: must be starttls, tls or none")
    if not 1 <= int(email.get("port") or 0) <= 65535:
        problems.append("email.port: must be 1-65535")
    if not email.get("to"):
        problems.append("email.to: list at least one recipient")
    hour = config["heartbeat"].get("daily_email_hour")
    if hour is not None and not 0 <= hour <= 23:
        problems.append("heartbeat.daily_email_hour: must be 0-23")
    for name, check in config["checks"].items():
        if not check.get("enabled"):
            continue
        if check["interval_seconds"] < 10:
            problems.append(f"checks.{name}.interval_seconds: at least 10")
        if not 1 <= check["timeout_seconds"] <= 300:
            problems.append(f"checks.{name}.timeout_seconds: must be 1-300")
        if check["failures_before_alert"] < 1:
            problems.append(f"checks.{name}.failures_before_alert: at least 1")
    network = config["checks"]["network"]
    if network.get("enabled"):
        if not network["resolve"] and not network["connect"]:
            problems.append("checks.network: list hosts under resolve and/or connect")
        for target in network["connect"]:
            if not _host_port(target):
                problems.append(f"checks.network.connect: {target!r} is not host:port")
    silence = config["checks"]["inbound_silence"]
    if silence.get("enabled") and not (
        silence["dsn"] or config["checks"]["database"]["dsn"]
    ):
        problems.append(
            "checks.inbound_silence.dsn: required (or set checks.database.dsn)"
        )
    if not any(c.get("enabled") for c in config["checks"].values()):
        problems.append("checks: enable at least one check")


def _host_port(target: Any) -> Optional[Tuple[str, int]]:
    """``"host:port"`` (or ``"[v6]:port"``) split, or None."""
    if not isinstance(target, str) or ":" not in target:
        return None
    host, _, port = target.rpartition(":")
    host = host.strip("[]")
    if not host or not port.isdigit() or not 1 <= int(port) <= 65535:
        return None
    return host, int(port)


def host_port(target: str) -> Tuple[str, int]:
    """The (host, port) of a validated ``connect`` target."""
    parsed = _host_port(target)
    if parsed is None:
        raise ValueError(target)
    return parsed


def validate(raw: Any) -> Dict[str, Any]:
    """The usable configuration from parsed YAML, or ConfigError."""
    problems: List[str] = []
    if not isinstance(raw, dict):
        raise ConfigError(["the file must be a YAML mapping"])
    for key in sorted(set(raw) - _TOP):
        problems.append(f"{key}: unknown setting")
    config: Dict[str, Any] = {
        "language": raw.get("language") or "en",
        "server_name": raw.get("server_name") or "SysManage",
    }
    if config["language"] not in LANGUAGES:
        problems.append(f"language: must be one of {', '.join(LANGUAGES)}")
    if not isinstance(config["server_name"], str):
        problems.append("server_name: must be str")
    config["email"] = _section("email", raw.get("email"), _EMAIL, problems)
    config["heartbeat"] = _section(
        "heartbeat", raw.get("heartbeat"), _HEARTBEAT, problems
    )
    checks_raw = raw.get("checks") or {}
    if not isinstance(checks_raw, dict):
        problems.append("checks: must be a mapping")
        checks_raw = {}
    for key in sorted(set(checks_raw) - set(CHECKS)):
        problems.append(f"checks.{key}: unknown check")
    config["checks"] = {}
    for name in CHECKS:
        section = checks_raw.get(name)
        enabled = isinstance(section, dict) and section.get("enabled") is True
        # A disabled check's required fields are not required.
        schema = (
            _SCHEMA[name]
            if enabled
            else {
                k: (t, None if d is REQUIRED else d)
                for k, (t, d) in _SCHEMA[name].items()
            }
        )
        config["checks"][name] = _section(f"checks.{name}", section, schema, problems)
    if not problems:
        _check_ranges(config, problems)
    if problems:
        raise ConfigError(problems)
    return config


def load(path: str = DEFAULT_PATH) -> Dict[str, Any]:
    """Read and validate the file at ``path``; ConfigError on any problem."""
    try:
        with open(path, encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
    except OSError as exc:
        raise ConfigError([f"cannot read {path}: {exc.strerror or exc}"]) from exc
    except yaml.YAMLError as exc:
        raise ConfigError([f"{path} is not valid YAML: {exc}"]) from exc
    return validate(raw)


def permission_warning(path: str) -> Optional[str]:
    """A warning when the file (it holds passwords) is readable by others."""
    if sys.platform == "win32":
        return None
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return None
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        return f"{path} is readable by other users (mode {oct(mode & 0o777)}); it should be 0600"
    return None
