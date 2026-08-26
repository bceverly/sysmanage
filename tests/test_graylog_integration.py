# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Graylog integration settings + health.

Two behaviours here are load-bearing and neither is obvious from the route
signatures.  The settings POST treats a literal ``"***"`` api_token as "the UI
re-sent the mask, keep what's stored" -- if that guard regressed, every save
from the settings screen would overwrite the real token with three asterisks
and log shipping would break with a valid-looking configuration on screen.
And the health check writes the detected input ports back to the settings row,
so the port-probe results are persisted state, not just a response body.

Everything outside the module -- the vault, httpx, raw sockets -- is faked;
these tests must never open a socket or reach a Graylog.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.api import graylog_integration as gl

MOD = "backend.api.graylog_integration"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def options(self, *_args, **_kwargs):
        return self

    def join(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, join_rows=(), **by_model):
        self._by_model = {k: list(v) for k, v in by_model.items()}
        self._join_rows = list(join_rows)
        self.added = []
        self.deleted = []
        self.commits = 0
        self.closed = False

    def query(self, *models):
        if len(models) > 1:
            return _FakeQuery(self._join_rows)
        return _FakeQuery(self._by_model.get(models[0].__name__, []))

    def add(self, row):
        self.added.append(row)
        if getattr(row, "id", None) is None:
            row.id = f"row-{len(self.added)}"

    def delete(self, row):
        self.deleted.append(row)

    def commit(self):
        self.commits += 1

    def refresh(self, _row):
        pass

    def close(self):
        self.closed = True

    def __call__(self, *_a, **_k):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _bound(session):
    """Patch the module's sessionmaker + engine so routes get ``session``."""
    return (
        patch(f"{MOD}.sessionmaker", return_value=session),
        patch(f"{MOD}.db.get_engine"),
    )


def _user(has_role=True):
    user = SimpleNamespace(
        id="u1", userid="admin@invalid", _role_cache={}, load_role_cache=lambda s: None
    )
    user.has_role = lambda role: has_role
    return user


def _settings_row(**overrides):
    row = SimpleNamespace(
        id="s1",
        enabled=True,
        use_managed_server=True,
        host_id="host-1",
        manual_url=None,
        api_token_vault_token=None,
        graylog_url="http://graylog.invalid:9000",
        to_dict=lambda: {"enabled": True},
    )
    for name in (
        "has_gelf_tcp",
        "gelf_tcp_port",
        "has_syslog_tcp",
        "syslog_tcp_port",
        "has_syslog_udp",
        "syslog_udp_port",
        "has_windows_sidecar",
        "windows_sidecar_port",
        "inputs_last_checked",
    ):
        setattr(row, name, None)
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def _request(**overrides):
    payload = {"enabled": True, "use_managed_server": True, "host_id": "host-1"}
    payload.update(overrides)
    return gl.GraylogIntegrationRequest(**payload)


def _http_request(username="admin@invalid"):
    return SimpleNamespace(state=SimpleNamespace(user={"username": username}))


class _Response:
    def __init__(self, status_code=200, text="ALIVE", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data or {}

    def json(self):
        return self._json


def _client(responses):
    """Fake httpx.AsyncClient returning ``responses`` in order."""
    calls = []

    class _Client:
        async def get(self, url, headers=None):
            calls.append(url)
            return responses[len(calls) - 1]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

    return patch(f"{MOD}.httpx.AsyncClient", return_value=_Client()), calls


def _sockets(open_ports=()):
    """Patch socket.socket so connect_ex succeeds only for ``open_ports``."""

    def _factory(*_args, **_kwargs):
        state = {}

        def _connect_ex(addr):
            state["port"] = addr[1]
            return 0 if addr[1] in open_ports else 1

        return SimpleNamespace(
            settimeout=lambda t: None, connect_ex=_connect_ex, close=lambda: None
        )

    return patch("socket.socket", side_effect=_factory)


# ---------------------------------------------------------------------------
# Server listing
# ---------------------------------------------------------------------------


class TestGetGraylogServers:
    @pytest.mark.asyncio
    async def test_servers_are_gathered_across_every_host_database(self):
        def _row(host_id, fqdn):
            return (
                SimpleNamespace(id=host_id, fqdn=fqdn),
                SimpleNamespace(package_version="6.0", is_active=True),
            )

        a = _FakeSession(join_rows=[_row("h1", "a.invalid")])
        b = _FakeSession(join_rows=[_row("h2", "b.invalid")])
        with patch(
            f"{MOD}.iter_host_databases",
            return_value=[("bootstrap", None, a), ("tenant", "t", b)],
        ):
            out = await gl.get_graylog_servers()
        # A tenant-bound host's HostRole lives in the tenant DB; a bootstrap-
        # only query would silently show an empty server list.
        assert [s.fqdn for s in out["graylog_servers"]] == ["a.invalid", "b.invalid"]
        assert a.closed and b.closed

    @pytest.mark.asyncio
    async def test_one_bad_database_is_skipped_not_fatal(self):
        bad = _FakeSession()
        bad.query = MagicMock(side_effect=RuntimeError("db gone"))
        good = _FakeSession(
            join_rows=[
                (
                    SimpleNamespace(id="h2", fqdn="b.invalid"),
                    SimpleNamespace(package_version="6.0", is_active=True),
                )
            ]
        )
        with patch(
            f"{MOD}.iter_host_databases",
            return_value=[("bad", None, bad), ("good", None, good)],
        ):
            out = await gl.get_graylog_servers()
        assert len(out["graylog_servers"]) == 1
        assert bad.closed and good.closed

    @pytest.mark.asyncio
    async def test_no_graylog_hosts_yields_an_empty_list(self):
        session = _FakeSession()
        with patch(
            f"{MOD}.iter_host_databases", return_value=[("bootstrap", None, session)]
        ):
            assert await gl.get_graylog_servers() == {"graylog_servers": []}


# ---------------------------------------------------------------------------
# Settings GET
# ---------------------------------------------------------------------------


class TestGetSettings:
    @pytest.mark.asyncio
    async def test_a_stored_row_is_serialized(self):
        session = _FakeSession(GraylogIntegrationSettings=[_settings_row()])
        maker, engine = _bound(session)
        with maker, engine:
            assert await gl.get_graylog_integration_settings() == {"enabled": True}

    @pytest.mark.asyncio
    async def test_an_unconfigured_server_reports_safe_defaults(self):
        maker, engine = _bound(_FakeSession())
        with maker, engine:
            out = await gl.get_graylog_integration_settings()
        # Defaults must be disabled: a default-on integration would start
        # shipping logs to nowhere.
        assert out["enabled"] is False
        assert out["use_managed_server"] is True
        assert out["api_token"] is None


# ---------------------------------------------------------------------------
# Settings POST
# ---------------------------------------------------------------------------


class TestUpdateSettings:
    async def _post(self, session, request=None, user=None, vault=None):
        maker, engine = _bound(session)
        vault_patch = patch(
            f"{MOD}.VaultService",
            return_value=vault
            or SimpleNamespace(
                store_secret=lambda **kw: {"vault_token": "vt", "vault_path": "vp"}
            ),
        )
        with maker, engine, vault_patch:
            with patch(f"{MOD}.validate_host_approval_status"):
                with patch(f"{MOD}.AuditService.log_update") as audit:
                    out = await gl.update_graylog_integration_settings(
                        request or _request(),
                        _http_request(),
                        current_user="admin@invalid",
                    )
        return out, audit

    def _session(self, **overrides):
        defaults = {
            "User": [_user()],
            "Host": [SimpleNamespace(id="host-1")],
            "HostRole": [SimpleNamespace(role="log_aggregation_server")],
            "GraylogIntegrationSettings": [_settings_row()],
            "Secret": [],
        }
        defaults.update(overrides)
        return _FakeSession(**defaults)

    @pytest.mark.asyncio
    async def test_a_valid_update_commits_and_audits(self):
        session = self._session()
        out, audit = await self._post(session)
        assert out["result"] is True
        assert session.commits == 1
        audit.assert_called_once()

    @pytest.mark.asyncio
    async def test_an_unknown_user_is_a_401(self):
        with pytest.raises(HTTPException) as exc:
            await self._post(self._session(User=[]))
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_a_user_without_the_role_is_a_403(self):
        with pytest.raises(HTTPException) as exc:
            await self._post(self._session(User=[_user(has_role=False)]))
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_an_uncached_role_set_is_loaded_before_the_check(self):
        user = _user()
        user._role_cache = None
        loaded = []
        user.load_role_cache = loaded.append
        # Without the load a cold cache would deny every caller.
        await self._post(self._session(User=[user]))
        assert loaded

    @pytest.mark.asyncio
    async def test_an_unknown_managed_host_is_a_404(self):
        with pytest.raises(HTTPException) as exc:
            await self._post(self._session(Host=[]))
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_a_host_without_the_graylog_role_is_a_400(self):
        with pytest.raises(HTTPException) as exc:
            await self._post(self._session(HostRole=[]))
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_a_manual_url_skips_the_host_checks_entirely(self):
        session = self._session(Host=[], HostRole=[])
        out, _ = await self._post(
            session,
            _request(
                use_managed_server=False,
                host_id=None,
                manual_url="http://graylog.invalid:9000",
            ),
        )
        assert out["result"] is True

    @pytest.mark.asyncio
    async def test_the_two_modes_are_mutually_exclusive_on_the_row(self):
        row = _settings_row()
        session = self._session(GraylogIntegrationSettings=[row])
        await self._post(
            session,
            _request(
                use_managed_server=False, host_id="host-1", manual_url="http://x:9000"
            ),
        )
        # Leaving host_id set alongside a manual URL makes graylog_url
        # ambiguous, and the property picks one silently.
        assert row.host_id is None
        assert row.manual_url == "http://x:9000"

    @pytest.mark.asyncio
    async def test_a_missing_settings_row_is_created(self):
        session = self._session(GraylogIntegrationSettings=[])
        await self._post(session)
        assert session.added

    @pytest.mark.asyncio
    async def test_a_new_token_is_vaulted_and_the_old_secret_removed(self):
        old = SimpleNamespace(name="graylog-api-token")
        row = _settings_row()
        session = self._session(GraylogIntegrationSettings=[row], Secret=[old])
        await self._post(session, _request(api_token="abc123"))
        assert session.deleted == [old]
        assert row.api_token_vault_token == "vt"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("token", ["***", "", "   ", None])
    async def test_the_masked_placeholder_never_overwrites_the_stored_token(
        self, token
    ):
        row = _settings_row(api_token_vault_token="original")
        session = self._session(GraylogIntegrationSettings=[row])
        vault = MagicMock()
        with patch(f"{MOD}.VaultService", return_value=vault) as vault_cls:
            maker, engine = _bound(session)
            with maker, engine:
                with patch(f"{MOD}.validate_host_approval_status"):
                    with patch(f"{MOD}.AuditService.log_update"):
                        await gl.update_graylog_integration_settings(
                            _request(api_token=token),
                            _http_request(),
                            current_user="admin@invalid",
                        )
        # Storing "***" would replace a working token with three asterisks and
        # break shipping while the screen still looks configured.
        vault_cls.assert_not_called()
        assert row.api_token_vault_token == "original"

    @pytest.mark.asyncio
    async def test_a_vault_failure_is_a_500_rather_than_a_silent_save(self):
        vault = SimpleNamespace(
            store_secret=MagicMock(side_effect=gl.VaultError("sealed"))
        )
        with pytest.raises(HTTPException) as exc:
            await self._post(self._session(), _request(api_token="abc"), vault=vault)
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestCheckHealth:
    async def _health(self, session, responses=None, open_ports=(), secret=None):
        maker, engine = _bound(session)
        client_patch, calls = _client(responses or [_Response()])
        vault = SimpleNamespace(retrieve_secret=lambda path, token: secret)
        with maker, engine, client_patch, _sockets(open_ports):
            with patch(f"{MOD}.VaultService", return_value=vault):
                out = await gl.check_graylog_health()
        return out, calls

    def _session(self, settings=None, secrets=()):
        return _FakeSession(
            GraylogIntegrationSettings=[settings] if settings else [],
            Secret=list(secrets),
        )

    @pytest.mark.asyncio
    async def test_an_unconfigured_integration_reports_why(self):
        out, _ = await self._health(self._session())
        assert out == {
            "healthy": False,
            "error": "Graylog integration has not been configured",
        }

    @pytest.mark.asyncio
    async def test_a_disabled_integration_reports_why(self):
        out, _ = await self._health(self._session(_settings_row(enabled=False)))
        assert out["healthy"] is False
        assert "not enabled" in out["error"]

    @pytest.mark.asyncio
    async def test_a_configured_but_urlless_integration_reports_why(self):
        out, _ = await self._health(self._session(_settings_row(graylog_url=None)))
        assert "URL is not configured" in out["error"]

    @pytest.mark.asyncio
    async def test_an_alive_server_is_healthy(self):
        out, calls = await self._health(self._session(_settings_row()))
        assert out.healthy is True
        assert calls == ["http://graylog.invalid:9000/api/system/lbstatus"]

    @pytest.mark.asyncio
    async def test_a_non_alive_body_is_unhealthy_despite_the_200(self):
        # Graylog answers 200 on lbstatus while draining; the body is the
        # actual signal.
        out, _ = await self._health(
            self._session(_settings_row()), [_Response(text="DEAD")]
        )
        assert out.healthy is False

    @pytest.mark.asyncio
    async def test_a_non_200_reports_the_status_and_body(self):
        out, _ = await self._health(
            self._session(_settings_row()), [_Response(status_code=503, text="down")]
        )
        assert out.healthy is False
        assert "503" in out.error and "down" in out.error

    @pytest.mark.asyncio
    async def test_detected_ports_are_returned_and_persisted(self):
        row = _settings_row()
        out, _ = await self._health(self._session(row), open_ports=(12201, 1514, 5044))
        assert (out.has_gelf_tcp, out.gelf_tcp_port) == (True, 12201)
        assert (out.has_syslog_tcp, out.syslog_tcp_port) == (True, 1514)
        assert (out.has_windows_sidecar, out.windows_sidecar_port) == (True, 5044)
        # Persisted, not just reported: the attach-host screen reads these off
        # the row rather than re-probing.
        assert row.has_gelf_tcp is True
        assert row.gelf_tcp_port == 12201
        assert row.inputs_last_checked is not None

    @pytest.mark.asyncio
    async def test_the_legacy_syslog_port_is_the_fallback(self):
        out, _ = await self._health(self._session(_settings_row()), open_ports=(514,))
        assert out.syslog_tcp_port == 514

    @pytest.mark.asyncio
    async def test_a_server_with_no_inputs_reports_all_absent(self):
        out, _ = await self._health(self._session(_settings_row()))
        assert out.has_gelf_tcp is False
        assert out.syslog_tcp_port is None
        assert out.has_windows_sidecar is False

    @pytest.mark.asyncio
    async def test_a_token_unlocks_the_detailed_system_info(self):
        row = _settings_row(api_token_vault_token="vt")
        secret_row = SimpleNamespace(vault_path="vp")
        out, calls = await self._health(
            self._session(row, [secret_row]),
            [
                _Response(),
                _Response(
                    json_data={
                        "version": "6.0.1",
                        "cluster_id": "c1",
                        "node_id": "n1",
                    }
                ),
            ],
            secret={"data": {"data": {"content": "tok"}}},
        )
        assert out.version == "6.0.1"
        assert out.cluster_id == "c1"
        assert calls[1].endswith("/api/system")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "secret_data",
        [
            {"data": {"data": {"content": "tok"}}},
            {"data": {"content": "tok"}},
            {"content": "tok"},
            {"content": "  tok  "},
        ],
        ids=["nested", "one-level", "direct", "padded"],
    )
    async def test_every_vault_payload_shape_yields_the_token(self, secret_data):
        # The three shapes are real: they come from different vault backends
        # and versions, and a missed one silently drops to unauthenticated.
        row = _settings_row(api_token_vault_token="vt")
        out, _ = await self._health(
            self._session(row, [SimpleNamespace(vault_path="vp")]),
            [_Response(), _Response(json_data={"version": "6.0.1"})],
            secret=secret_data,
        )
        assert out.version == "6.0.1"

    @pytest.mark.asyncio
    async def test_an_unreadable_vault_degrades_to_the_unauthenticated_check(self):
        row = _settings_row(api_token_vault_token="vt")
        maker, engine = _bound(self._session(row, [SimpleNamespace(vault_path="vp")]))
        client_patch, calls = _client([_Response()])
        vault = SimpleNamespace(
            retrieve_secret=MagicMock(side_effect=gl.VaultError("sealed"))
        )
        with maker, engine, client_patch, _sockets():
            with patch(f"{MOD}.VaultService", return_value=vault):
                out = await gl.check_graylog_health()
        # Health is still useful without the token; failing the whole check
        # would hide a server that is up.
        assert out.healthy is True
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_a_missing_secret_row_skips_the_detailed_call(self):
        row = _settings_row(api_token_vault_token="vt")
        out, calls = await self._health(self._session(row, []))
        assert out.healthy is True
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_a_detailed_call_that_fails_still_reports_liveness(self):
        row = _settings_row(api_token_vault_token="vt")
        out, _ = await self._health(
            self._session(row, [SimpleNamespace(vault_path="vp")]),
            [_Response(), _Response(status_code=401)],
            secret={"content": "tok"},
        )
        assert out.healthy is True
        assert out.version is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "error,fragment",
        [
            (gl.httpx.ReadTimeout("slow"), "timeout"),
            (gl.httpx.ConnectTimeout("slow"), "timeout"),
            (gl.httpx.ConnectError("refused"), "Connection failed"),
            (RuntimeError("boom"), "Unexpected error"),
        ],
    )
    async def test_each_transport_failure_gets_its_own_message(self, error, fragment):
        class _Client:
            async def get(self, url, headers=None):
                raise error

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_exc):
                return False

        maker, engine = _bound(self._session(_settings_row()))
        with maker, engine, patch(f"{MOD}.httpx.AsyncClient", return_value=_Client()):
            out = await gl.check_graylog_health()
        assert out.healthy is False
        assert fragment in out.error

    @pytest.mark.asyncio
    async def test_an_unreadable_url_property_is_a_500(self):
        # graylog_url is a computed property over host/manual_url; a broken
        # relationship makes it raise, and the operator needs that surfaced
        # rather than folded into a generic "unhealthy".
        class _Exploding:
            enabled = True

            @property
            def graylog_url(self):
                raise RuntimeError("bad column")

        maker, engine = _bound(self._session(_Exploding()))
        with maker, engine:
            with pytest.raises(HTTPException) as exc:
                await gl.check_graylog_health()
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_a_socket_layer_failure_reports_no_inputs_rather_than_failing(self):
        # No IPv4 stack, a sandbox that blocks raw sockets, a DNS failure on
        # the Graylog host: none of those mean the server is down, so the
        # probe degrades to "inputs unknown" and liveness still stands.
        maker, engine = _bound(self._session(_settings_row()))
        client_patch, _calls = _client([_Response()])
        with maker, engine, client_patch:
            with patch("socket.socket", side_effect=OSError("no sockets")):
                out = await gl.check_graylog_health()
        assert out.healthy is True
        assert out.has_gelf_tcp is False
        assert out.has_syslog_tcp is False
        assert out.has_windows_sidecar is False

    @pytest.mark.asyncio
    async def test_an_unexpected_vault_error_also_degrades_to_unauthenticated(self):
        # VaultError is caught explicitly; this covers everything else the
        # vault client can raise (connection resets, JSON decode errors).
        row = _settings_row(api_token_vault_token="vt")
        maker, engine = _bound(self._session(row, [SimpleNamespace(vault_path="vp")]))
        client_patch, calls = _client([_Response()])
        vault = SimpleNamespace(
            retrieve_secret=MagicMock(side_effect=RuntimeError("connection reset"))
        )
        with maker, engine, client_patch, _sockets():
            with patch(f"{MOD}.VaultService", return_value=vault):
                out = await gl.check_graylog_health()
        assert out.healthy is True
        assert len(calls) == 1
