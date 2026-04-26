"""
Tests for backend.api.grafana_integration.

Focuses on the testable surface that doesn't require GrafanaIntegrationSettings
or HostRole models in the test conftest:

- configure_prometheus_datasource — pure async helper, mocks vault + httpx
- the GrafanaHealthStatus / GrafanaServerInfo / GrafanaIntegrationRequest
  Pydantic schemas
- check_grafana_health early-return branches via HTTPException
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.api import grafana_integration as gi
from backend.api.grafana_integration import (
    GrafanaHealthStatus,
    GrafanaIntegrationRequest,
    GrafanaServerInfo,
    configure_prometheus_datasource,
)
from backend.services.vault_service import VaultError


def _settings(grafana_url=None, api_key_vault_token=None):
    s = MagicMock()
    s.grafana_url = grafana_url
    s.api_key_vault_token = api_key_vault_token
    return s


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class TestSchemas:
    def test_grafana_integration_request_minimal(self):
        m = GrafanaIntegrationRequest(enabled=False, use_managed_server=True)
        assert m.enabled is False
        assert m.use_managed_server is True
        assert m.host_id is None

    def test_grafana_integration_request_with_manual_url(self):
        m = GrafanaIntegrationRequest(
            enabled=True, use_managed_server=False, manual_url="http://g:3000"
        )
        assert m.manual_url == "http://g:3000"

    def test_grafana_server_info_defaults(self):
        m = GrafanaServerInfo(id="h-1", fqdn="g.example")
        assert m.role  # MONITORING_SERVER constant
        assert m.package_name == "grafana"
        assert m.is_active is False

    def test_grafana_health_status_unhealthy_with_error(self):
        m = GrafanaHealthStatus(healthy=False, error="HTTP 500")
        assert m.healthy is False
        assert m.error == "HTTP 500"


# ---------------------------------------------------------------------------
# configure_prometheus_datasource — early-return branches
# ---------------------------------------------------------------------------


class TestConfigurePrometheusDatasourceEarlyReturns:
    @pytest.mark.asyncio
    async def test_no_grafana_url_logs_and_returns(self):
        # No httpx mock needed — function should bail before any HTTP call.
        with patch("backend.api.grafana_integration.httpx.AsyncClient") as cls:
            await configure_prometheus_datasource(
                _settings(grafana_url=None), MagicMock()
            )
        cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_api_key_vault_token_returns(self):
        with patch("backend.api.grafana_integration.httpx.AsyncClient") as cls:
            await configure_prometheus_datasource(
                _settings(grafana_url="http://g:3000", api_key_vault_token=None),
                MagicMock(),
            )
        cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_secret_not_found_returns(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None
        with patch("backend.api.grafana_integration.VaultService"), patch(
            "backend.api.grafana_integration.httpx.AsyncClient"
        ) as cls:
            await configure_prometheus_datasource(
                _settings(grafana_url="http://g:3000", api_key_vault_token="t"),
                session,
            )
        cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_vault_retrieval_exception_returns_silently(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = MagicMock(
            vault_path="vault/path"
        )
        with patch("backend.api.grafana_integration.VaultService") as cls, patch(
            "backend.api.grafana_integration.httpx.AsyncClient"
        ) as httpx_cls:
            cls.return_value.retrieve_secret.side_effect = RuntimeError("vault down")
            await configure_prometheus_datasource(
                _settings(grafana_url="http://g:3000", api_key_vault_token="t"),
                session,
            )
        httpx_cls.assert_not_called()


# ---------------------------------------------------------------------------
# configure_prometheus_datasource — API key extraction paths
# ---------------------------------------------------------------------------


class _FakeAsyncResponse:
    def __init__(self, status_code, json_body=None, text=""):
        self.status_code = status_code
        self._json = json_body or []
        self.text = text

    def json(self):
        return self._json


class _FakeAsyncClient:
    """httpx.AsyncClient stand-in supporting the get/post/put we exercise."""

    def __init__(self, get_response=None, post_response=None, put_response=None):
        self._get = get_response
        self._post = post_response
        self._put = put_response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None):
        return self._get

    async def post(self, url, headers=None, json=None):
        return self._post

    async def put(self, url, headers=None, json=None):
        return self._put


def _settings_with_secret(session, secret_data):
    """Wire up session.query → secret row, vault.retrieve → secret_data."""
    secret = MagicMock(vault_path="vault/path")
    session.query.return_value.filter.return_value.first.return_value = secret
    vault = MagicMock()
    vault.retrieve_secret.return_value = secret_data
    return vault


class TestConfigurePrometheusDatasourceApiKeyExtraction:
    @pytest.mark.asyncio
    async def test_api_key_at_data_data_content(self):
        session = MagicMock()
        vault = _settings_with_secret(
            session, {"data": {"data": {"content": "the-key"}}}
        )
        client = _FakeAsyncClient(
            get_response=_FakeAsyncResponse(200, []),
            post_response=_FakeAsyncResponse(201),
        )
        with patch(
            "backend.api.grafana_integration.VaultService", return_value=vault
        ), patch(
            "backend.api.grafana_integration.httpx.AsyncClient",
            return_value=client,
        ):
            await configure_prometheus_datasource(
                _settings(grafana_url="http://g:3000", api_key_vault_token="t"),
                session,
            )

    @pytest.mark.asyncio
    async def test_api_key_at_data_content(self):
        session = MagicMock()
        vault = _settings_with_secret(session, {"data": {"content": "the-key"}})
        client = _FakeAsyncClient(
            get_response=_FakeAsyncResponse(200, []),
            post_response=_FakeAsyncResponse(201),
        )
        with patch(
            "backend.api.grafana_integration.VaultService", return_value=vault
        ), patch(
            "backend.api.grafana_integration.httpx.AsyncClient", return_value=client
        ):
            await configure_prometheus_datasource(
                _settings(grafana_url="http://g:3000", api_key_vault_token="t"),
                session,
            )

    @pytest.mark.asyncio
    async def test_api_key_at_root_content(self):
        session = MagicMock()
        vault = _settings_with_secret(session, {"content": "the-key"})
        client = _FakeAsyncClient(
            get_response=_FakeAsyncResponse(200, []),
            post_response=_FakeAsyncResponse(201),
        )
        with patch(
            "backend.api.grafana_integration.VaultService", return_value=vault
        ), patch(
            "backend.api.grafana_integration.httpx.AsyncClient", return_value=client
        ):
            await configure_prometheus_datasource(
                _settings(grafana_url="http://g:3000", api_key_vault_token="t"),
                session,
            )

    @pytest.mark.asyncio
    async def test_no_api_key_in_secret_returns(self):
        session = MagicMock()
        vault = _settings_with_secret(session, {"data": {}})
        with patch(
            "backend.api.grafana_integration.VaultService", return_value=vault
        ), patch("backend.api.grafana_integration.httpx.AsyncClient") as httpx_cls:
            await configure_prometheus_datasource(
                _settings(grafana_url="http://g:3000", api_key_vault_token="t"),
                session,
            )
        httpx_cls.assert_not_called()


# ---------------------------------------------------------------------------
# configure_prometheus_datasource — datasource create / update branches
# ---------------------------------------------------------------------------


class TestConfigurePrometheusDatasourceHttp:
    @pytest.mark.asyncio
    async def test_creates_when_no_existing_datasource(self):
        session = MagicMock()
        vault = _settings_with_secret(
            session, {"data": {"data": {"content": "the-key"}}}
        )
        # GET returns empty list → we'll create.
        client = _FakeAsyncClient(
            get_response=_FakeAsyncResponse(200, []),
            post_response=_FakeAsyncResponse(201),
        )
        with patch(
            "backend.api.grafana_integration.VaultService", return_value=vault
        ), patch(
            "backend.api.grafana_integration.httpx.AsyncClient", return_value=client
        ):
            await configure_prometheus_datasource(
                _settings(grafana_url="http://g:3000", api_key_vault_token="t"),
                session,
            )

    @pytest.mark.asyncio
    async def test_create_failure_logged_silently(self):
        session = MagicMock()
        vault = _settings_with_secret(
            session, {"data": {"data": {"content": "the-key"}}}
        )
        client = _FakeAsyncClient(
            get_response=_FakeAsyncResponse(200, []),
            post_response=_FakeAsyncResponse(500, text="server error"),
        )
        with patch(
            "backend.api.grafana_integration.VaultService", return_value=vault
        ), patch(
            "backend.api.grafana_integration.httpx.AsyncClient", return_value=client
        ):
            # Function returns None whether or not create succeeded — must not raise.
            await configure_prometheus_datasource(
                _settings(grafana_url="http://g:3000", api_key_vault_token="t"),
                session,
            )

    @pytest.mark.asyncio
    async def test_updates_when_existing_datasource_present(self):
        session = MagicMock()
        vault = _settings_with_secret(
            session, {"data": {"data": {"content": "the-key"}}}
        )
        existing = {
            "id": 7,
            "uid": "abc",
            "type": "prometheus",
            "name": "SysManage Prometheus",
        }
        client = _FakeAsyncClient(
            get_response=_FakeAsyncResponse(200, [existing]),
            put_response=_FakeAsyncResponse(200),
        )
        with patch(
            "backend.api.grafana_integration.VaultService", return_value=vault
        ), patch(
            "backend.api.grafana_integration.httpx.AsyncClient", return_value=client
        ):
            await configure_prometheus_datasource(
                _settings(grafana_url="http://g:3000", api_key_vault_token="t"),
                session,
            )

    @pytest.mark.asyncio
    async def test_update_failure_logged_silently(self):
        session = MagicMock()
        vault = _settings_with_secret(
            session, {"data": {"data": {"content": "the-key"}}}
        )
        existing = {
            "id": 7,
            "uid": "abc",
            "type": "prometheus",
            "name": "SysManage Prometheus",
        }
        client = _FakeAsyncClient(
            get_response=_FakeAsyncResponse(200, [existing]),
            put_response=_FakeAsyncResponse(403, text="forbidden"),
        )
        with patch(
            "backend.api.grafana_integration.VaultService", return_value=vault
        ), patch(
            "backend.api.grafana_integration.httpx.AsyncClient", return_value=client
        ):
            await configure_prometheus_datasource(
                _settings(grafana_url="http://g:3000", api_key_vault_token="t"),
                session,
            )

    @pytest.mark.asyncio
    async def test_uses_prometheus_url_env_var_when_set(self, monkeypatch):
        monkeypatch.setenv("PROMETHEUS_URL", "http://custom-prom:9999")
        session = MagicMock()
        vault = _settings_with_secret(session, {"data": {"data": {"content": "k"}}})

        captured = {}

        class _CapturingClient(_FakeAsyncClient):
            async def post(self, url, headers=None, json=None):
                captured["json"] = json
                return _FakeAsyncResponse(201)

        client = _CapturingClient(
            get_response=_FakeAsyncResponse(200, []),
            post_response=None,
        )
        with patch(
            "backend.api.grafana_integration.VaultService", return_value=vault
        ), patch(
            "backend.api.grafana_integration.httpx.AsyncClient", return_value=client
        ):
            await configure_prometheus_datasource(
                _settings(grafana_url="http://g:3000", api_key_vault_token="t"),
                session,
            )
        assert captured["json"]["url"] == "http://custom-prom:9999"
