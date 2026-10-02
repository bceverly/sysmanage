# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Lucky 13 source checks: #2 XSS (CWE-79), #4 remote file inclusion
(CWE-98), #6 world-writable files (CWE-276), #9 grow-your-own crypto
(CWE-327), #10 privilege escalation via Help (CWE-271), #11 symlink
following (CWE-61) and #12 hard-coded / default passwords (CWE-259).

These are patterns a reviewer can see in five minutes, so a scan can too.
A hit is either fixed or added to ``ALLOWED`` below with the reason it is
safe -- the allow-list is the reviewed record, so keep the reasons honest.
"""

import re

import yaml

from tests.lucky13.conftest import REPO

# (check, repo-relative path) -> why this occurrence is safe.
ALLOWED = {
    ("4", "backend/licensing/module_loader.py"): (
        "loads Pro+ engines only from the local modules directory, after the "
        "bundle's signature is verified (module_signature.verify_module_dir)"
    ),
    ("2", "backend/api/reports/endpoints.py"): (
        "report HTML comes from the reporting engine, which escapes every "
        "interpolated value (escape_html); the endpoint requires a login"
    ),
    ("4", "scripts/translation-service/i18n_backfill.py"): (
        "developer translation tool loading this repository's own i18n_strict.py"
    ),
    ("4", "scripts/render_nginx_configs.py"): (
        "build-time generator loading this repository's own "
        "backend/security/tls_policy.py so nginx and uvicorn share one cipher list"
    ),
    ("10", "scripts/migrate-security-config.py"): (
        "ShellExecuteW 'runas' re-launches this same script elevated (UAC); it "
        "opens no help viewer, browser or shell UI"
    ),
    ("11", "backend/services/script_plan_builder.py"): (
        "names the script /tmp/sysmanage_script_<uuid4>.sh on the agent host: "
        "122 random bits, so the path cannot be pre-created as a symlink"
    ),
}

SKIP_DIRS = {"node_modules", "__pycache__", "tests", ".venv", "dist", "build"}


def _files(roots, suffixes):
    for root in roots:
        base = REPO / root
        paths = [base] if base.is_file() else base.rglob("*")
        for path in paths:
            if not path.is_file() or SKIP_DIRS & set(path.relative_to(REPO).parts):
                continue
            if suffixes is None or path.suffix in suffixes or path.name in suffixes:
                yield path


def _hits(check, roots, suffixes, pattern, line_ok=None):
    regex = re.compile(pattern)
    found = []
    for path in _files(roots, suffixes):
        rel = str(path.relative_to(REPO))
        if (check, rel) in ALLOWED:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if regex.search(line) and not (line_ok and line_ok(line)):
                found.append(f"{rel}:{number}: {line.strip()[:120]}")
    return found


def _report(found, what):
    return f"{what} -- fix, or allow in test_source_hygiene.ALLOWED with the reason:\n  " + "\n  ".join(found)  # fmt: skip


PY = {".py", ".pyx", ".pxi"}
SHELL = {".sh", ".ps1", ".spec", ".bat", "postinst", "postrm", "preinst", "prerm",
         "Makefile", "+INSTALL", "+DEINSTALL", "+MANIFEST", "postinstall", "preinstall"}  # fmt: skip


def test_2_no_raw_html_sinks_in_the_frontend():
    found = _hits("2", ["frontend/src"], {".ts", ".tsx"},
                  r"dangerouslySetInnerHTML|\.(inner|outer)HTML\s*=|insertAdjacentHTML"
                  r"|document\.write|\beval\(|new Function\(",
                  line_ok=lambda line: "__tests__" in line)  # fmt: skip
    assert not found, _report(found, "#2 raw HTML sinks (XSS)")


def test_2_html_responses_are_reviewed():
    found = _hits("2", ["backend"], PY, r"\bHTMLResponse\(")
    assert not found, _report(found, "#2 HTML built on the server (XSS)")


def test_4_no_code_loaded_from_request_data():
    found = _hits("4", ["backend", "scripts"], PY,
                  r"(^|[^.\w])(eval|exec)\(|__import__\(|import_module\("
                  r"|spec_from_file_location|SourceFileLoader")  # fmt: skip
    assert not found, _report(found, "#4 dynamic code loading (file inclusion)")


def test_6_nothing_is_made_world_writable():
    octal = r"[0-7]?[0-7][0-7][2367]\b"
    found = _hits("6", ["backend", "scripts", "installer", "Makefile"], PY | SHELL,
                  rf"chmod\s+(-\w+\s+)*{octal}|chmod\s+(-\w+\s+)*[ugoa]*[oa][ugoa]*\+[rxX]*w"
                  rf"|0o{octal}|S_IWOTH|os\.umask\(0\)")  # fmt: skip
    assert not found, _report(found, "#6 world-writable files")


def test_9_no_home_grown_or_broken_crypto():
    found = _hits("9", ["backend", "scripts"], PY,
                  r"hashlib\.(md5|sha1)\(|hashlib\.new\(['\"](md5|sha1)|\bfrom Crypto\b"
                  r"|\bimport Crypto\b|\bARC4\b|\bBlowfish\b|TripleDES|modes\.ECB|rot13",
                  line_ok=lambda line: "usedforsecurity=False" in line)  # fmt: skip
    assert not found, _report(found, "#9 weak or home-grown crypto")


def test_9_security_code_uses_secrets_not_random():
    found = _hits("9", ["backend/security", "backend/auth"], PY,
                  r"^\s*(import random\b|from random import)")  # fmt: skip
    assert not found, _report(found, "#9 predictable randomness in security code")


def test_10_the_privileged_server_never_launches_a_ui():
    found = _hits("10", ["backend", "scripts"], PY,
                  r"\bwebbrowser\b|os\.startfile|xdg-open|ShellExecute|\bhh\.exe|winhlp32")  # fmt: skip
    assert not found, _report(found, "#10 launching a browser/help viewer")


def test_11_no_predictable_temporary_files():
    found = _hits("11", ["backend", "scripts"], PY,
                  r"tempfile\.mktemp\(|['\"]/(var/)?tmp/")  # fmt: skip
    assert not found, _report(found, "#11 predictable /tmp paths (symlink following)")


# -- #12 -----------------------------------------------------------------------

WELL_KNOWN = {"admin", "password", "changeme", "change_me", "administrator",
              "sysmanage", "root", "toor", "default", "123456", "letmein"}  # fmt: skip


def _example_configs():
    return [p for p in REPO.rglob("sysmanage*.yaml.example")
            if not SKIP_DIRS & set(p.relative_to(REPO).parts)]  # fmt: skip


def test_12_example_configs_exist():
    assert _example_configs(), "no sysmanage.yaml.example found -- scan is blind"


def test_12_no_live_credential_in_the_example_configs():
    """Installers copy these to /etc/sysmanage.yaml when there is none, so a
    usable value here is a default password on every fresh install.

    Fixed 2026-10-02 (Bryan: generate at install time): the examples ship
    placeholders, installers write random values into the config they create
    (``backend/config/install_secrets.py``), and the recovery login refuses
    any placeholder or well-known password (next test).
    """
    found = []
    for path in _example_configs():
        security = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("security") or {}  # fmt: skip
        password = str(security.get("admin_password") or "")
        # Only a placeholder belongs here: anything else is a password every
        # install from this file shares.  (sysmanage-dev.yaml.example is the
        # developer stack's own config, never installed.)
        if path.name == "sysmanage-dev.yaml.example":
            continue
        if password and not password.upper().startswith("CHANGE_ME"):
            found.append(f"{path.relative_to(REPO)}: admin_password {password!r}")
    assert not found, "\n".join(found)


def test_12_a_placeholder_or_well_known_password_never_signs_in():
    """The recovery login, fed what an attacker would try first."""
    from unittest.mock import (
        MagicMock,
        patch,
    )  # pylint: disable=import-outside-toplevel

    from backend.api.auth import (
        UserLogin,
        _try_admin_login,
    )  # pylint: disable=import-outside-toplevel

    for shipped in ("admin", "password", "CHANGE_ME_GENERATED_AT_INSTALL"):
        the_config = {"security": {"admin_userid": "admin@example.com",
                                   "admin_password": shipped}}  # fmt: skip
        with (
            patch("backend.api.auth.config.get_admin_password", return_value=shipped),
            patch("backend.api.auth.sign_jwt") as sign,
        ):
            result = _try_admin_login(
                UserLogin(userid="admin@example.com", password=shipped), the_config,
                MagicMock(), "203.0.113.9", "attacker", MagicMock(), 3600, True,
            )  # fmt: skip
        assert result is None, shipped
        sign.assert_not_called()
