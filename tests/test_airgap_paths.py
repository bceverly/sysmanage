# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The air-gap repository is written where that platform's nginx serves it
(2026-11-13): FreeBSD, OpenBSD and Windows served an empty tree."""

import importlib.util
from pathlib import Path

import pytest

from backend.services import airgap_paths, airgap_tools

REPO = Path(__file__).resolve().parents[1]

# render_nginx_configs.py platform -> what platform.system() says there.
SYSTEMS = {
    "alpine": "Linux",
    "centos": "Linux",
    "opensuse": "Linux",
    "ubuntu": "Linux",
    "freebsd": "FreeBSD",
    "openbsd": "OpenBSD",
    "netbsd": "NetBSD",
    "macos": "Darwin",
    "windows": "Windows",
}


def _nginx_table():
    path = REPO / "scripts" / "render_nginx_configs.py"
    spec = importlib.util.spec_from_file_location("_render_nginx", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PLATFORMS


def _alias(value):
    return value.strip('"').rstrip("/")


@pytest.mark.parametrize("name", sorted(SYSTEMS))
def test_the_repository_is_written_where_nginx_serves_it(name):
    paths = _nginx_table()[name]
    root = airgap_paths.repo_root(system=SYSTEMS[name], environ={})
    assert root == _alias(paths["AIRGAP_ROOT"])
    assert airgap_tools.tools_root(root) == _alias(paths["AIRGAP_TOOLS_ROOT"])


def test_the_snap_writes_under_its_own_data_directory():
    snap = _nginx_table()["snap"]
    data = "/var/snap/sysmanage/42"
    root = airgap_paths.repo_root(
        system="Linux", environ={"SNAP_DATA": data, "SNAP_NAME": "sysmanage"}
    )
    assert root == _alias(snap["AIRGAP_ROOT"]).replace("%%SNAP_DATA%%", data)
    assert airgap_tools.tools_root(root) == _alias(snap["AIRGAP_TOOLS_ROOT"]).replace(
        "%%SNAP_DATA%%", data
    )


def test_every_nginx_platform_is_covered():
    assert set(_nginx_table()) == set(SYSTEMS) | {"snap"}
