# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Install-time secrets (Lucky 13 #12, CWE-259).

The examples used to ship ``admin_password: "admin"`` and published
``CHANGE_ME`` secrets that installers copied into place.  Installers now
generate this install's values in the config they just created; only
placeholders are ever replaced, so a live config is never touched.
"""

import os
import stat

import pytest
import yaml

from backend.config import install_secrets as inst


@pytest.fixture(autouse=True)
def _tmp_is_a_config_dir(tmp_path, monkeypatch):
    """Tests write their config under tmp_path; let the path guard accept it."""
    from backend.config import config_target

    monkeypatch.setattr(
        config_target, "CONFIG_DIRS", config_target.CONFIG_DIRS + (str(tmp_path),)
    )


EXAMPLE = """\
# my notes
security:
  password_salt: "CHANGE_ME_IN_PRODUCTION_USE_RANDOM_STRING"   # the installer writes a random one
  admin_userid: "admin@example.com"
  admin_password: "CHANGE_ME_GENERATED_AT_INSTALL"   # a placeholder never signs in
  jwt_secret: CHANGE_ME_IN_PRODUCTION_USE_RANDOM_SECRET
  jwt_algorithm: "HS256"
"""


def test_placeholders_and_well_known_passwords_are_recognized():
    for value in ("admin", "Password", "CHANGE_ME_IN_PRODUCTION_USE_RANDOM_SECRET",
                  "change_me_generated_at_install", " root "):  # fmt: skip
        assert inst.is_placeholder(value), value
    for value in (None, "", "Xk3-real-secret", "admin2025!"):
        assert not inst.is_placeholder(value), value


def test_every_placeholder_is_replaced_and_the_rest_kept():
    new, replaced = inst.generate(EXAMPLE)
    assert sorted(replaced) == ["admin_password", "jwt_secret", "password_salt"]
    security = yaml.safe_load(new)["security"]
    for key in replaced:
        assert not inst.is_placeholder(security[key])
        assert len(security[key]) >= 24
    assert security["admin_userid"] == "admin@example.com"
    assert security["jwt_algorithm"] == "HS256"
    assert new.startswith("# my notes\n")


def test_values_differ_between_installs():
    first = yaml.safe_load(inst.generate(EXAMPLE)[0])["security"]
    second = yaml.safe_load(inst.generate(EXAMPLE)[0])["security"]
    assert first["jwt_secret"] != second["jwt_secret"]
    assert first["admin_password"] != second["admin_password"]


def test_an_administrators_own_values_are_never_touched():
    own = EXAMPLE.replace('"CHANGE_ME_IN_PRODUCTION_USE_RANDOM_STRING"', '"my-salt"')
    own = own.replace('"CHANGE_ME_GENERATED_AT_INSTALL"', '"my-recovery-pw"')
    own = own.replace("CHANGE_ME_IN_PRODUCTION_USE_RANDOM_SECRET", "my-jwt-secret")
    assert inst.generate(own) == (own, [])


def test_apply_writes_once_and_never_prints_the_password(tmp_path, capsys):
    config = tmp_path / "sysmanage.yaml"
    config.write_text(EXAMPLE, encoding="utf-8")
    os.chmod(config, 0o640)
    assert inst.main(["--apply", str(config)]) == 0
    out = capsys.readouterr().out
    password = yaml.safe_load(config.read_text(encoding="utf-8"))["security"][
        "admin_password"
    ]
    assert password not in out and "generated" in out
    if os.name != "nt":  # POSIX permission bits; Windows has none to keep
        assert stat.S_IMODE(config.stat().st_mode) == 0o640  # permissions kept
    text = config.read_text(encoding="utf-8")
    assert "left unchanged" in inst.apply_to_file(str(config))
    assert config.read_text(encoding="utf-8") == text


def test_a_missing_file_is_an_error_not_a_crash(tmp_path, capsys):
    assert inst.main(["--apply", str(tmp_path / "absent.yaml")]) == 1
    assert "could not update" in capsys.readouterr().err
