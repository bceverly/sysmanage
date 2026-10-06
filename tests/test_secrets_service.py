# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for the config secrets accessor (Phase 13.1.H config classification).

Verifies OpenBAO-first resolution, YAML fallback with deprecation, and the
best-effort/never-raise behavior when vault is disabled or unreachable.
"""

from unittest.mock import patch

from backend.config import secrets_service


def _reset_warned():
    secrets_service._warned.clear()
    secrets_service.invalidate_cache()


def test_prefers_openbao_over_yaml():
    _reset_warned()
    with patch.object(
        secrets_service.config, "is_vault_enabled", return_value=True
    ), patch.object(
        secrets_service.config, "get_vault_mount_path", return_value="secret"
    ), patch(
        "backend.services.vault_service.VaultService"
    ) as vs:
        vs.return_value.retrieve_secret.return_value = {"jwt_secret": "from-bao"}
        val = secrets_service.get_secret("jwt_secret", lambda: "from-yaml")
    assert val == "from-bao"


def test_falls_back_to_yaml_when_vault_disabled():
    _reset_warned()
    with patch.object(secrets_service.config, "is_vault_enabled", return_value=False):
        val = secrets_service.get_secret("jwt_secret", lambda: "from-yaml")
    assert val == "from-yaml"


def test_falls_back_to_yaml_when_secret_absent_in_bao():
    _reset_warned()
    with patch.object(
        secrets_service.config, "is_vault_enabled", return_value=True
    ), patch.object(
        secrets_service.config, "get_vault_mount_path", return_value="secret"
    ), patch(
        "backend.services.vault_service.VaultService"
    ) as vs:
        vs.return_value.retrieve_secret.return_value = {"other": "x"}
        val = secrets_service.get_secret("jwt_secret", lambda: "from-yaml")
    assert val == "from-yaml"


def test_never_raises_when_vault_unreachable():
    _reset_warned()
    with patch.object(
        secrets_service.config, "is_vault_enabled", return_value=True
    ), patch.object(
        secrets_service.config, "get_vault_mount_path", return_value="secret"
    ), patch(
        "backend.services.vault_service.VaultService"
    ) as vs:
        vs.return_value.retrieve_secret.side_effect = RuntimeError("boom")
        val = secrets_service.get_secret("jwt_secret", lambda: "from-yaml")
    assert val == "from-yaml"


def test_returns_default_when_nothing_available():
    _reset_warned()
    with patch.object(secrets_service.config, "is_vault_enabled", return_value=False):
        val = secrets_service.get_secret("missing", lambda: None, default="d")
    assert val == "d"


def test_deprecation_warning_logged_once(caplog):
    _reset_warned()
    with patch.object(secrets_service.config, "is_vault_enabled", return_value=False):
        import logging

        with caplog.at_level(logging.WARNING):
            secrets_service.get_secret("jwt_secret", lambda: "y")
            secrets_service.get_secret("jwt_secret", lambda: "y")
    # The deprecation warning is key-agnostic (the secret name is treated as
    # sensitive and not logged), but the ``_warned`` dedup set still emits it
    # exactly once per distinct key across the two calls.
    warnings = [r for r in caplog.records if "sysmanage.yaml" in r.message]
    assert len(warnings) == 1


# --- Tenant-scoped secrets (Phase 13.1) ------------------------------------


def test_tenant_secret_path_includes_tenant_id():
    with patch.object(
        secrets_service.config, "get_vault_mount_path", return_value="secret"
    ):
        path = secrets_service._tenant_secret_path("t-123")
    assert path == "secret/data/sysmanage/tenant/t-123/config"


def test_get_tenant_secret_from_openbao():
    with patch.object(
        secrets_service.config, "is_vault_enabled", return_value=True
    ), patch.object(
        secrets_service.config, "get_vault_mount_path", return_value="secret"
    ), patch(
        "backend.services.vault_service.VaultService"
    ) as vs:
        vs.return_value.retrieve_secret.return_value = {"smtp_password": "pw"}
        val = secrets_service.get_tenant_secret("t-1", "smtp_password", default="d")
    assert val == "pw"


def test_get_tenant_secret_default_when_disabled():
    with patch.object(secrets_service.config, "is_vault_enabled", return_value=False):
        val = secrets_service.get_tenant_secret("t-1", "smtp_password", default="d")
    assert val == "d"


def test_get_tenant_secret_default_when_absent():
    with patch.object(
        secrets_service.config, "is_vault_enabled", return_value=True
    ), patch.object(
        secrets_service.config, "get_vault_mount_path", return_value="secret"
    ), patch(
        "backend.services.vault_service.VaultService"
    ) as vs:
        vs.return_value.retrieve_secret.return_value = {"other": "x"}
        val = secrets_service.get_tenant_secret("t-1", "smtp_password", default="d")
    assert val == "d"


def test_get_tenant_secret_never_raises():
    with patch.object(
        secrets_service.config, "is_vault_enabled", return_value=True
    ), patch.object(
        secrets_service.config, "get_vault_mount_path", return_value="secret"
    ), patch(
        "backend.services.vault_service.VaultService"
    ) as vs:
        vs.return_value.retrieve_secret.side_effect = RuntimeError("boom")
        val = secrets_service.get_tenant_secret("t-1", "smtp_password", default="d")
    assert val == "d"


def test_store_tenant_secrets_merges_and_writes():
    with patch.object(
        secrets_service.config, "is_vault_enabled", return_value=True
    ), patch.object(
        secrets_service.config, "get_vault_mount_path", return_value="secret"
    ), patch(
        "backend.services.vault_service.VaultService"
    ) as vs:
        svc = vs.return_value
        svc.retrieve_secret.return_value = {"existing": "keep"}
        ok = secrets_service.store_tenant_secrets("t-1", {"smtp_password": "pw"})
    assert ok is True
    # Wrote the merged bag (existing preserved, new added) to the tenant path.
    args, _ = svc._make_request.call_args
    assert args[0] == "POST"
    assert args[1] == "secret/data/sysmanage/tenant/t-1/config"
    assert args[2] == {"data": {"existing": "keep", "smtp_password": "pw"}}


def test_store_tenant_secrets_disabled_returns_false():
    with patch.object(secrets_service.config, "is_vault_enabled", return_value=False):
        assert secrets_service.store_tenant_secrets("t-1", {"x": "y"}) is False


def test_single_flight_refresh():
    """Phase 22.2: when the cache expires, threads asking at once share ONE
    OpenBAO read instead of each making their own."""
    import threading
    import time

    _reset_warned()
    calls = []
    started = threading.Event()

    def slow_read():
        calls.append(1)
        started.set()
        time.sleep(0.2)  # OpenBAO answering slowly
        return {"jwt_secret": "from-bao"}

    results = []
    with patch.object(
        secrets_service.config, "is_vault_enabled", return_value=True
    ), patch.object(secrets_service, "_read_bag_from_openbao", side_effect=slow_read):
        threads = [
            threading.Thread(
                target=lambda: results.append(secrets_service.get_config_secret_bag())
            )
            for _ in range(8)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert len(calls) == 1
    assert results == [{"jwt_secret": "from-bao"}] * 8


def test_cache_ttl_is_jittered():
    """Worker processes must not all refresh at the same moment."""
    expiries = set()
    with patch.object(
        secrets_service.config, "is_vault_enabled", return_value=True
    ), patch.object(secrets_service, "_read_bag_from_openbao", return_value={}):
        for _ in range(30):
            secrets_service.invalidate_cache()
            before = secrets_service.time.time()
            secrets_service.get_config_secret_bag()
            expiries.add(round(secrets_service._cache_expiry - before, 3))
    ttl = secrets_service._CACHE_TTL_SECONDS
    spread = secrets_service._CACHE_TTL_SPREAD
    assert all(
        ttl * (1 - spread) - 0.1 <= e <= ttl * (1 + spread) + 0.1 for e in expiries
    )
    assert len(expiries) > 10
