# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The canary's checks.  Each takes its section of the configuration and
returns a Result: pass or fail, and what it saw as a message key plus values
(rendered in the configured language by ``i18n``).  A check never raises:
anything unexpected is a failure that says what went wrong."""

import socket
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from sysmanage_canary.config import host_port


@dataclass
class Result:
    ok: bool
    key: str
    params: Dict[str, Any] = field(default_factory=dict)


def _ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _short(exc: BaseException) -> str:
    """An exception as one short line for an email."""
    reason = getattr(exc, "reason", None)
    text = str(reason if reason is not None else exc) or type(exc).__name__
    return text.splitlines()[0][:200]


def http_check(section: Dict[str, Any]) -> Result:
    """The URL answers 2xx/3xx, over a TLS handshake that verifies, within
    ``max_response_ms``.  Used for the web console and for /api/health."""
    context = ssl.create_default_context()
    if not section.get("verify_tls", True):
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    request = urllib.request.Request(
        section["url"], headers={"User-Agent": "sysmanage-canary"}
    )
    start = time.monotonic()
    try:
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        with urllib.request.urlopen(  # nosec B310 - the admin's own URL
            request, timeout=section["timeout_seconds"], context=context
        ) as response:
            response.read(65536)
            status = response.status
    except urllib.error.HTTPError as exc:
        exc.close()  # it holds the response
        return Result(False, "http.status", {"status": exc.code})
    except ssl.SSLError as exc:
        return Result(False, "http.tls", {"error": _short(exc)})
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, ssl.SSLError):
            return Result(False, "http.tls", {"error": _short(exc.reason)})
        return Result(False, "http.error", {"error": _short(exc)})
    except (OSError, ValueError) as exc:
        return Result(False, "http.error", {"error": _short(exc)})
    elapsed = _ms(start)
    if status >= 400:
        return Result(False, "http.status", {"status": status})
    if elapsed > section["max_response_ms"]:
        return Result(
            False, "http.slow", {"ms": elapsed, "limit": section["max_response_ms"]}
        )
    return Result(True, "http.ok", {"status": status, "ms": elapsed})


def _connect(dsn: str, timeout: int):
    try:
        import psycopg  # pylint: disable=import-outside-toplevel
    except ImportError:
        return None
    return psycopg.connect(dsn, connect_timeout=timeout, autocommit=True)


def database_check(section: Dict[str, Any], connect: Callable = _connect) -> Result:
    """Connect, ``SELECT 1`` within ``max_response_ms``, and connections in
    use below ``max_connections_percent`` of PostgreSQL's maximum (the pool
    exhaustion the Phase 22 harness found)."""
    start = time.monotonic()
    try:
        conn = connect(section["dsn"], section["timeout_seconds"])
        if conn is None:
            return Result(False, "db.driver")
        with conn:
            conn.execute("SELECT 1").fetchone()
            elapsed = _ms(start)
            used = conn.execute("SELECT count(*) FROM pg_stat_activity").fetchone()[0]
            maximum = int(conn.execute("SHOW max_connections").fetchone()[0])
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return Result(False, "db.error", {"error": _short(exc)})
    if elapsed > section["max_response_ms"]:
        return Result(
            False, "db.slow", {"ms": elapsed, "limit": section["max_response_ms"]}
        )
    percent = round(100 * used / maximum) if maximum else 0
    if percent > section["max_connections_percent"]:
        return Result(
            False,
            "db.connections",
            {
                "used": used,
                "max": maximum,
                "percent": percent,
                "limit": section["max_connections_percent"],
            },
        )
    return Result(True, "db.ok", {"ms": elapsed, "used": used, "max": maximum})


def network_check(section: Dict[str, Any]) -> Result:
    """Every name under ``resolve`` resolves and every ``connect`` target
    accepts a TCP connection: the server can still reach the outside (the
    license server, package mirrors, a public resolver)."""
    timeout = section["timeout_seconds"]
    for host in section["resolve"]:
        try:
            socket.getaddrinfo(str(host), None)
        except OSError as exc:
            return Result(False, "net.dns", {"host": host, "error": _short(exc)})
    for target in section["connect"]:
        host, port = host_port(target)
        try:
            with socket.create_connection((host, port), timeout=timeout):
                pass
        except OSError as exc:
            return Result(
                False, "net.connect", {"target": target, "error": _short(exc)}
            )
    return Result(
        True,
        "net.ok",
        {"resolved": len(section["resolve"]), "connected": len(section["connect"])},
    )


SILENCE_SQL = (
    "SELECT max(t) FROM ("
    " SELECT max(last_access) AS t FROM host"
    " UNION ALL SELECT max(created_at) FROM message_queue WHERE direction = 'inbound'"
    ") latest"
)


def newest_agent_contact(
    dsns: List[str], timeout: int, connect: Callable = _connect
) -> Optional[datetime]:
    """The newest agent contact across ``dsns`` (the main database and, with
    multi-tenancy, the tenant databases); None if no agent ever reported."""
    newest = None
    for dsn in dsns:
        conn = connect(dsn, timeout)
        if conn is None:
            raise RuntimeError("psycopg is not installed")
        with conn:
            value = conn.execute(SILENCE_SQL).fetchone()[0]
        if value is not None:
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            newest = value if newest is None or value > newest else newest
    return newest


def inbound_silence_check(
    section: Dict[str, Any],
    database_dsn: Optional[str],
    connect: Callable = _connect,
    now: Optional[datetime] = None,
) -> Result:
    """Agents are still reporting: the newest host contact or inbound
    message is younger than ``max_silence_minutes``.  Read from the database,
    so a dead listener, a broken firewall rule or a lapsed DNS record shows
    even when every local check passes."""
    dsns = [section.get("dsn") or database_dsn] + list(section.get("extra_dsns") or [])
    try:
        newest = newest_agent_contact(
            [d for d in dsns if d], section["timeout_seconds"], connect
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return Result(False, "db.error", {"error": _short(exc)})
    if newest is None:
        return Result(False, "silence.never")
    now = now or datetime.now(timezone.utc)
    minutes = int((now - newest).total_seconds() // 60)
    if minutes > section["max_silence_minutes"]:
        return Result(
            False,
            "silence.stale",
            {"minutes": minutes, "limit": section["max_silence_minutes"]},
        )
    return Result(True, "silence.ok", {"minutes": minutes})


def run(name: str, config: Dict[str, Any]) -> Result:
    """Run check ``name``; never raises."""
    section = config["checks"][name]
    try:
        if name in ("web_ui", "backend"):
            return http_check(section)
        if name == "database":
            return database_check(section)
        if name == "network":
            return network_check(section)
        return inbound_silence_check(section, config["checks"]["database"].get("dsn"))
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return Result(False, "check.crashed", {"error": _short(exc)})
