# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Install-time secrets for a freshly created ``sysmanage.yaml`` (Phase 22.10).

WHY
---
MITRE "Lucky 13" #12 (CWE-259, default passwords), found 2026-10-02: every
installer's example config shipped ``admin_password: "admin"`` beside
``admin@example.com``, and ``jwt_secret`` / ``password_salt`` as published
``CHANGE_ME...`` strings.  Installers copy the example into place when there
is no config, so every fresh install could be signed into as the recovery
admin with ``admin``, and anyone who read the example could sign their own
tokens.  Bryan's decision: generate them at install time.

SAFETY
------
Only ever run on a config the installer has JUST created from the example
(the installers call this inside their "no config yet" branch), and even
then only a value that is still a shipped placeholder is replaced:

* ``jwt_secret`` also keys the encryption of stored MFA secrets
  (``security/mfa_crypto.py``) and ``password_salt`` takes part in password
  hashing -- replacing either on a LIVE install would lock users out;
* an administrator's own value is never a placeholder, so it is never
  touched.

The file is edited as text, line by line, so its comments and layout
survive.  The generated recovery password is written to the file (root /
service-group readable, like every other secret in it) and never printed.

Usage:  python -m backend.config.install_secrets --apply /etc/sysmanage.yaml
"""

import argparse
import re
import secrets
import sys
from typing import Callable, Dict, Optional

# Values the examples have shipped, or ever could: never a real secret.
WELL_KNOWN_PASSWORDS = frozenset(
    {"admin", "password", "changeme", "change_me", "administrator", "sysmanage",
     "root", "toor", "default", "123456", "letmein"}
)  # fmt: skip


def is_placeholder(value: Optional[str]) -> bool:
    """True for a value no installation should keep: a ``CHANGE_ME...``
    marker or a well-known password."""
    if value is None:
        return False
    text = str(value).strip()
    return text.upper().startswith("CHANGE_ME") or text.lower() in WELL_KNOWN_PASSWORDS


GENERATORS: Dict[str, Callable[[], str]] = {
    "jwt_secret": lambda: secrets.token_urlsafe(48),
    "password_salt": lambda: secrets.token_hex(32),
    "admin_password": lambda: secrets.token_urlsafe(18),
}

# ``  key: "value"   # comment`` -- quoted or bare value, optional comment.
_LINE = re.compile(
    r"^(?P<indent>\s+)(?P<key>jwt_secret|password_salt|admin_password):\s*"
    r"(?P<value>\"[^\"]*\"|'[^']*'|[^\s#]+)\s*(?P<comment>#.*)?$"
)


def generate(text: str) -> tuple:
    """Return ``(new_text, replaced_keys)`` with placeholders replaced."""
    replaced = []
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        ending = "\n" if line.endswith("\n") else ""
        match = _LINE.match(line.rstrip("\r\n"))
        if not match:
            continue
        key = match.group("key")
        if not is_placeholder(match.group("value").strip("\"'")):
            continue
        lines[index] = (
            f'{match.group("indent")}{key}: "{GENERATORS[key]()}"'
            f"   # generated at install time{ending}"
        )
        replaced.append(key)
    return "".join(lines), replaced


def apply_to_file(path: str) -> str:
    """Replace the placeholders in ``path``; returns what was done."""
    with open(path, encoding="utf-8") as handle:
        original = handle.read()
    updated, replaced = generate(original)
    if not replaced:
        return f"{path}: no placeholder secrets; left unchanged"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(updated)
    message = f"{path}: generated {', '.join(sorted(replaced))}"
    if "admin_password" in replaced:
        message += (
            " (the recovery admin password is security.admin_password in this "
            "file; sign in as security.admin_userid)"
        )
    return message


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate install-time secrets in a new sysmanage.yaml"
    )
    parser.add_argument(
        "--apply", metavar="CONFIG", required=True, help="the config just created"
    )
    args = parser.parse_args(argv)
    try:
        print(apply_to_file(args.apply))
    except OSError as exc:
        print(f"could not update {args.apply}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
