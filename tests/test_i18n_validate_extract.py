# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Key extraction in scripts/i18n_validate.py ignores test files.

Tests call ``t()`` with made-up keys; walking them seeded ``[MISSING:greeting]``
and three others into every shipped catalog.
"""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "i18n_validate.py"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("i18n_validate", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "path",
    [
        "src/i18n/__tests__/lateCatalog.test.tsx",
        "src/__tests__/Components/Nav.tsx",
        "src/Components/Nav.test.tsx",
        "src/Pages/Hosts.spec.ts",
    ],
)
def test_test_files_are_skipped(mod, path):
    assert mod._is_test_file(Path(path)) is True


@pytest.mark.parametrize(
    "path", ["src/Pages/Hosts.tsx", "src/Services/testConnection.ts"]
)
def test_application_files_are_read(mod, path):
    assert mod._is_test_file(Path(path)) is False


def test_no_test_only_key_is_extracted(mod):
    keys = mod.extract_keys()
    for leaked in ("greeting", "pluginOnlyKey", "nav.gated", "nav.plain"):
        assert leaked not in keys
