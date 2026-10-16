# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The "read from sysmanage.yaml" deprecation warning names only what the
operator actually wrote.

apply_defaults() merges built-in defaults into the loaded config, so every
setting looked YAML-sourced and the production server logged ~20 warnings per
start for keys nobody had put in the file (2026-10-16).  Values are unchanged:
a default is still returned as before -- only the warning is gated."""

import logging
from unittest.mock import patch

import pytest

from backend.config import config as config_module
from backend.config import settings_service


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(settings_service, "_warned", set())
    monkeypatch.setattr(settings_service, "_get_cached_settings_bag", lambda: {})
    monkeypatch.setattr(
        config_module, "_FILE_CONFIG", {"security": {"jwt_auth_timeout": 7200}}
    )


def _warnings(caplog):
    return [
        r
        for r in caplog.records
        if "is being read from sysmanage.yaml" in r.getMessage()
    ]


def test_file_has_sees_only_what_the_file_wrote():
    assert config_module.file_has("security", "jwt_auth_timeout")
    assert not config_module.file_has("security", "jwt_refresh_timeout")
    assert not config_module.file_has("monitoring", "heartbeat_timeout")


def test_a_value_the_file_sets_still_warns(caplog):
    with caplog.at_level(logging.WARNING):
        value = settings_service.get_setting(
            "jwt_auth_timeout",
            lambda: 7200,
            default=3600,
            yaml_path=("security", "jwt_auth_timeout"),
        )
    assert value == 7200
    assert len(_warnings(caplog)) == 1


def test_a_built_in_default_is_returned_without_a_warning(caplog):
    with caplog.at_level(logging.WARNING):
        value = settings_service.get_setting(
            "heartbeat_timeout",
            lambda: 5,  # what the defaults-merged config yields
            default=5,
            yaml_path=("monitoring", "heartbeat_timeout"),
        )
    assert value == 5
    assert _warnings(caplog) == []


def test_a_database_value_wins_silently(caplog, monkeypatch):
    monkeypatch.setattr(
        settings_service, "_get_cached_settings_bag", lambda: {"jwt_auth_timeout": 900}
    )
    with caplog.at_level(logging.WARNING):
        value = settings_service.get_setting(
            "jwt_auth_timeout",
            lambda: 7200,
            default=3600,
            yaml_path=("security", "jwt_auth_timeout"),
        )
    assert value == 900
    assert _warnings(caplog) == []


def test_callers_without_a_path_keep_the_old_warning(caplog):
    with caplog.at_level(logging.WARNING):
        settings_service.get_setting("legacy_thing", lambda: "x", default=None)
    assert len(_warnings(caplog)) == 1


def test_the_real_accessors_pass_their_paths(caplog):
    with patch.object(config_module, "_FILE_CONFIG", {}), caplog.at_level(
        logging.WARNING
    ):
        assert (
            config_module.get_heartbeat_timeout_minutes()
            == config_module.config["monitoring"]["heartbeat_timeout"]
        )
        config_module.get_jwt_auth_timeout()
        config_module.get_jwt_refresh_timeout()
        config_module.is_geo_lookup_enabled()
    assert _warnings(caplog) == []
