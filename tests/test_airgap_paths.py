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


def _plain_http_server(config: str) -> str:
    """The ``listen 80`` server block of a rendered config."""
    start = config.index("listen 80;")
    start = config.rindex("server {", 0, start)
    depth, i = 0, start
    while True:
        if config[i] == "{":
            depth += 1
        elif config[i] == "}":
            depth -= 1
            if depth == 0:
                return config[start : i + 1]
        i += 1


@pytest.mark.parametrize("name", sorted(SYSTEMS) + ["snap"])
def test_plain_http_serves_only_the_package_trees(name):
    """2026-11-13: port 80 redirected everything, so no air-gapped host's
    package manager could fetch the repository it was pointed at."""
    path = REPO / "scripts" / "render_nginx_configs.py"
    spec = importlib.util.spec_from_file_location("_render_nginx", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    block = _plain_http_server(module.render(name))
    paths = module.PLATFORMS[name]
    assert f"alias {paths['AIRGAP_ROOT']};" in block
    assert f"alias {paths['AIRGAP_TOOLS_ROOT']};" in block
    assert block.count("location") == 3  # the two trees, and the redirect
    assert "return 301 https://$host$request_uri;" in block
    assert "proxy_pass" not in block  # nothing of the application in clear


def test_the_repository_url_is_port_80_never_the_backend_port(monkeypatch):
    from backend.services import airgap_ingest_tick as tick

    monkeypatch.setattr(tick.socket, "getfqdn", lambda: "repo.example.com")
    assert tick._mirror_base_url() == "http://repo.example.com/airgap-repo"
