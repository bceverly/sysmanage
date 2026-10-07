# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.9: each canary check against a working, failing, slow and
refusing target."""

import socket
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from sysmanage_canary import checks

HTTP = {"timeout_seconds": 5, "max_response_ms": 2000, "verify_tls": True}


@contextmanager
def _server(status=200, delay=0.0):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            time.sleep(delay)
            try:
                self.send_response(status)
                self.end_headers()
                self.wfile.write(b'{"status": "healthy"}')
            except (BrokenPipeError, ConnectionResetError):
                pass  # the client gave up first (the timeout test)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/api/health"
    finally:
        server.shutdown()
        server.server_close()


def _closed_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class TestHttp:
    def test_working(self):
        with _server() as url:
            result = checks.http_check({**HTTP, "url": url})
        assert result.ok and result.key == "http.ok" and result.params["status"] == 200

    def test_an_error_status_fails(self):
        with _server(status=503) as url:
            result = checks.http_check({**HTTP, "url": url})
        assert (
            not result.ok
            and result.key == "http.status"
            and result.params["status"] == 503
        )

    def test_slow_fails(self):
        with _server(delay=0.3) as url:
            result = checks.http_check({**HTTP, "url": url, "max_response_ms": 100})
        assert not result.ok and result.key == "http.slow"

    def test_a_timeout_fails(self):
        with _server(delay=2) as url:
            result = checks.http_check({**HTTP, "url": url, "timeout_seconds": 1})
        assert not result.ok and result.key == "http.error"

    def test_refused_fails(self):
        result = checks.http_check(
            {**HTTP, "url": f"http://127.0.0.1:{_closed_port()}/"}
        )
        assert not result.ok and result.key == "http.error"

    def test_a_tls_handshake_failure_says_so(self):
        # TLS spoken to a plain-HTTP listener: the handshake cannot succeed.
        with _server() as url:
            result = checks.http_check(
                {**HTTP, "url": url.replace("http://", "https://")}
            )
        assert not result.ok and result.key in ("http.tls", "http.error")


class _Conn:
    def __init__(self, answers, delay=0.0):
        self.answers = list(answers)
        self.delay = delay

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, _sql):
        time.sleep(self.delay)
        value = self.answers.pop(0)
        cursor = type("C", (), {"fetchone": lambda _self: (value,)})()
        return cursor


DB = {"dsn": "postgresql://x/y", "timeout_seconds": 5, "max_response_ms": 1000,
      "max_connections_percent": 85}  # fmt: skip


class TestDatabase:
    def test_working(self):
        result = checks.database_check(DB, connect=lambda *_: _Conn([1, 20, "100"]))
        assert result.ok and result.params == {
            "ms": result.params["ms"],
            "used": 20,
            "max": 100,
        }

    def test_connections_near_the_maximum_fail(self):
        result = checks.database_check(DB, connect=lambda *_: _Conn([1, 95, "100"]))
        assert (
            not result.ok
            and result.key == "db.connections"
            and result.params["percent"] == 95
        )

    def test_slow_fails(self):
        result = checks.database_check({**DB, "max_response_ms": 10},
                                       connect=lambda *_: _Conn([1, 1, "100"], delay=0.05))  # fmt: skip
        assert not result.ok and result.key == "db.slow"

    def test_unreachable_fails_with_the_error(self):
        def refuse(*_):
            raise OSError("connection refused")

        result = checks.database_check(DB, connect=refuse)
        assert not result.ok and result.key == "db.error"
        assert "connection refused" in result.params["error"]

    def test_no_driver_says_so(self):
        result = checks.database_check(DB, connect=lambda *_: None)
        assert not result.ok and result.key == "db.driver"


class TestNetwork:
    BASE = {"timeout_seconds": 2}

    def test_working(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            result = checks.network_check({**self.BASE, "resolve": ["localhost"],
                                           "connect": [f"127.0.0.1:{port}"]})  # fmt: skip
        assert result.ok and result.params == {"resolved": 1, "connected": 1}

    def test_an_unresolvable_name_fails(self):
        result = checks.network_check({**self.BASE, "resolve": ["no-such-host.invalid"],
                                       "connect": []})  # fmt: skip
        assert not result.ok and result.key == "net.dns"
        assert result.params["host"] == "no-such-host.invalid"

    def test_a_refusing_target_fails(self):
        target = f"127.0.0.1:{_closed_port()}"
        result = checks.network_check({**self.BASE, "resolve": [], "connect": [target]})
        assert (
            not result.ok
            and result.key == "net.connect"
            and result.params["target"] == target
        )


class TestInboundSilence:
    SECTION = {
        "dsn": None,
        "extra_dsns": [],
        "timeout_seconds": 5,
        "max_silence_minutes": 30,
    }
    NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)

    def _run(self, newest_per_db, section=None):
        answers = iter(newest_per_db)
        return checks.inbound_silence_check(
            {**self.SECTION, **(section or {})},
            "postgresql://main",
            connect=lambda *_: _Conn([next(answers)]),
            now=self.NOW,
        )

    def test_recent_contact_passes(self):
        result = self._run([self.NOW - timedelta(minutes=5)])
        assert result.ok and result.params["minutes"] == 5

    def test_silence_fails(self):
        result = self._run([self.NOW - timedelta(minutes=45)])
        assert (
            not result.ok
            and result.key == "silence.stale"
            and result.params["minutes"] == 45
        )

    def test_the_newest_of_every_tenant_database_counts(self):
        result = self._run([self.NOW - timedelta(hours=5), self.NOW - timedelta(minutes=2)],
                           {"extra_dsns": ["postgresql://tenant"]})  # fmt: skip
        assert result.ok and result.params["minutes"] == 2

    def test_a_naive_timestamp_is_read_as_utc(self):
        result = self._run([(self.NOW - timedelta(minutes=3)).replace(tzinfo=None)])
        assert result.ok and result.params["minutes"] == 3

    def test_never_reported(self):
        result = self._run([None])
        assert not result.ok and result.key == "silence.never"


def test_run_never_raises():
    config = {
        "checks": {"network": {"resolve": None, "connect": [], "timeout_seconds": 1}}
    }
    result = checks.run("network", config)
    assert not result.ok and result.key == "check.crashed"
