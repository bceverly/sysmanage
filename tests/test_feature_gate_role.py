# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A licensed federation engine whose role this server does not have answers
409 with the role it needs -- never the 503 that says an engine is missing."""

from unittest.mock import patch

import pytest

from backend.licensing import feature_gate


@pytest.mark.parametrize(
    "module, role",
    [
        ("federation_controller_engine", "coordinator"),
        ("federation_site_engine", "site"),
    ],
)
def test_loaded_but_another_role_is_409(module, role):
    with patch.object(feature_gate, "license_service") as lic, patch.object(
        feature_gate, "_engine_loaded", return_value=True
    ):
        lic.has_module.return_value = True
        exc = feature_gate.refuse_unlicensed(module)
    assert exc.status_code == 409
    assert exc.detail["error"] == "federation_role"
    assert exc.detail["role_needed"] == role


def test_licensed_but_not_loaded_is_still_503():
    with patch.object(feature_gate, "license_service") as lic, patch.object(
        feature_gate, "_engine_loaded", return_value=False
    ):
        lic.has_module.return_value = True
        exc = feature_gate.refuse_unlicensed("federation_controller_engine")
    assert exc.status_code == 503


def test_unlicensed_is_still_402():
    with patch.object(feature_gate, "license_service") as lic:
        lic.has_module.return_value = False
        exc = feature_gate.refuse_unlicensed("federation_controller_engine")
    assert exc.status_code == 402


def test_other_engines_are_unchanged():
    with patch.object(feature_gate, "license_service") as lic, patch.object(
        feature_gate, "_engine_loaded", return_value=True
    ):
        lic.has_module.return_value = True
        exc = feature_gate.refuse_unlicensed("automation_engine")
    assert exc.status_code == 503
