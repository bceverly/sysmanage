# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.9: the canary's command line, and its 14 message catalogs."""

import json
import os
import re
from unittest.mock import patch

import yaml

from sysmanage_canary import __main__ as cli
from sysmanage_canary import i18n
from sysmanage_canary.config import LANGUAGES

LOCALES = os.path.join(os.path.dirname(i18n.__file__), "locales")


def _write(tmp_path, data):
    path = tmp_path / "canary.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    os.chmod(path, 0o600)
    return str(path)


GOOD = {"email": {"host": "smtp.x", "from": "a@x", "to": ["b@x"]},
        "checks": {"network": {"enabled": True, "resolve": ["localhost"]}}}  # fmt: skip


def test_check_config_accepts_a_good_file(tmp_path, capsys):
    assert cli.main(["--config", _write(tmp_path, GOOD), "--check-config"]) == 0
    assert "1 check(s) enabled" in capsys.readouterr().out


def test_check_config_refuses_a_bad_file_listing_every_problem(tmp_path, capsys):
    bad = {"email": {"host": "smtp.x"}, "checks": {"nope": {}}}
    assert cli.main(["--config", _write(tmp_path, bad), "--check-config"]) == 2
    err = capsys.readouterr().err
    assert "email.from: required" in err and "checks.nope: unknown check" in err


def test_test_email_sends_one(tmp_path, capsys):
    with patch("sysmanage_canary.alerts.send") as send:
        assert cli.main(["--config", _write(tmp_path, GOOD), "--test-email"]) == 0
    subject = send.call_args[0][1]
    assert subject == "[SysManage] sysmanage-canary test message"
    assert "b@x" in capsys.readouterr().out


def test_test_email_failure_is_reported(tmp_path, capsys):
    with patch("sysmanage_canary.alerts.send", side_effect=OSError("auth failed")):
        assert cli.main(["--config", _write(tmp_path, GOOD), "--test-email"]) == 1
    assert "auth failed" in capsys.readouterr().err


def test_once_runs_every_enabled_check(tmp_path, capsys):
    assert cli.main(["--config", _write(tmp_path, GOOD), "--once"]) == 0
    assert "[ok  ] Network" in capsys.readouterr().out


def _catalog(language):
    with open(os.path.join(LOCALES, f"{language}.json"), encoding="utf-8") as handle:
        return json.load(handle)


def test_every_language_has_every_message_with_its_placeholders():
    english = _catalog("en")
    for language in LANGUAGES:
        catalog = _catalog(language)
        assert set(catalog) == set(english), language
        for key, text in catalog.items():
            assert set(re.findall(r"\{\w+\}", text)) == set(
                re.findall(r"\{\w+\}", english[key])
            ), (language, key)
            if key.endswith(".subject"):
                assert text.startswith("[{server}]"), (language, key)


def test_a_missing_placeholder_value_never_breaks_a_message():
    assert "{status}" in i18n.t("en", "http.status")
    assert i18n.t("en", "no.such.key") == "no.such.key"
