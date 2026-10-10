# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The --apply tools rewrite only a real SysManage configuration file."""

import os
import sys

import pytest

from backend.config import install_secrets
from backend.config.config_target import resolve_config_target
from backend.persistence import pool_sizing


@pytest.fixture(autouse=True)
def _tmp_is_a_config_dir(tmp_path, monkeypatch):
    """Tests write their config under tmp_path; let the path guard accept it."""
    from backend.config import config_target

    monkeypatch.setattr(
        config_target, "CONFIG_DIRS", config_target.CONFIG_DIRS + (str(tmp_path),)
    )


@pytest.mark.parametrize(
    "name", ["sysmanage.yaml", "sysmanage.yaml.example", "config.yaml"]
)
def test_the_installers_file_names_are_accepted(tmp_path, name):
    target = tmp_path / name
    target.write_text("x: 1\n", encoding="utf-8")
    assert resolve_config_target(str(target)) == os.path.realpath(target)


@pytest.mark.parametrize(
    "name", ["passwd", "authorized_keys", "sysmanage.yml", "notes.yaml"]
)
def test_any_other_file_is_refused(tmp_path, name):
    target = tmp_path / name
    target.write_text("x: 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not a SysManage configuration file"):
        resolve_config_target(str(target))


@pytest.mark.skipif(
    sys.platform == "win32", reason="symlinks need privileges on Windows"
)
def test_a_symlink_in_place_of_the_config_is_refused(tmp_path):
    victim = tmp_path / "victim"
    victim.write_text("keep me\n", encoding="utf-8")
    (tmp_path / "sysmanage.yaml").symlink_to(victim)
    with pytest.raises(ValueError, match="not a regular file"):
        resolve_config_target(str(tmp_path / "sysmanage.yaml"))
    assert install_secrets.main(["--apply", str(tmp_path / "sysmanage.yaml")]) == 1
    assert pool_sizing.main(["--apply", str(tmp_path / "sysmanage.yaml")]) == 1
    assert victim.read_text(encoding="utf-8") == "keep me\n"


def test_a_directory_is_refused(tmp_path):
    (tmp_path / "config.yaml").mkdir()
    with pytest.raises(ValueError, match="not a regular file"):
        resolve_config_target(str(tmp_path / "config.yaml"))


def test_the_tools_refuse_a_wrong_name_without_touching_it(tmp_path):
    other = tmp_path / "other.conf"
    other.write_text("password_salt: CHANGE_ME\n", encoding="utf-8")
    assert install_secrets.main(["--apply", str(other)]) == 1
    assert pool_sizing.main(["--apply", str(other)]) == 1
    assert other.read_text(encoding="utf-8") == "password_salt: CHANGE_ME\n"


def test_a_config_name_outside_the_config_directories_is_refused(tmp_path, monkeypatch):
    # The right file NAME in the wrong place is still refused: the tools run as
    # root, and "/tmp/x/sysmanage.yaml" is not the server's configuration.
    from backend.config import config_target

    monkeypatch.setattr(config_target, "CONFIG_DIRS", ("/etc",))
    (tmp_path / "sysmanage.yaml").write_text("api: {}\n")
    with pytest.raises(ValueError, match="configuration directory"):
        resolve_config_target(str(tmp_path / "sysmanage.yaml"))
