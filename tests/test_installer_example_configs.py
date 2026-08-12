# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Every shipped example config must be one the server can actually load.

Several installers copy their example STRAIGHT to the live config --
installer/opensuse/sysmanage.spec and installer/ubuntu/debian/postinst both do
``cp .../sysmanage.yaml.example /etc/sysmanage.yaml``, and the Alpine init
script and snap wrapper do the same -- so an example that does not match what
``backend/config/config.py`` reads produces a package that installs cleanly and
cannot start.

On 2026-08-12 six of the eight shipped examples were in that state, in three
distinct flavours of drift:

  * freebsd / macos / netbsd  -- a ``server:`` / ``auth:`` / ``openbao:``
    schema with ``database.username`` and ``database.database``
  * centos / opensuse         -- ``server:`` with ``database.url`` and
    connection-pool keys
  * windows                   -- entirely commented out, no keys at all

None of those key names appear anywhere in backend/.  They described a
configuration format the application has never had, so the connection details
a user filled in were simply never read.  Only the root example and
installer/ubuntu matched reality.

These tests pin the examples to the loader, which is the contract that was
silently broken.
"""

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

EXAMPLES = [REPO_ROOT / "sysmanage.yaml.example"] + sorted(
    REPO_ROOT.glob("installer/*/sysmanage.yaml.example")
)

# What backend/persistence/db.py needs to build a connection string.
REQUIRED_DB_KEYS = {"host", "port", "name", "user", "password"}

# Top-level keys from the three drifted schemas.  None of these is read
# anywhere in backend/; their presence means an example has drifted again.
FICTIONAL_SECTIONS = {"server", "auth", "openbao", "telemetry"}


def _ids(paths):
    return [str(p.relative_to(REPO_ROOT)) for p in paths]


def test_examples_are_discovered():
    """Guard against the glob silently matching nothing."""
    assert len(EXAMPLES) >= 8, _ids(EXAMPLES)


@pytest.mark.parametrize("path", EXAMPLES, ids=_ids(EXAMPLES))
def test_example_is_parseable_yaml_with_content(path):
    """An all-comments file loads as None and cannot configure anything."""
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict) and loaded, f"{path} has no usable content"


@pytest.mark.parametrize("path", EXAMPLES, ids=_ids(EXAMPLES))
def test_example_has_a_usable_database_connection(path):
    """registry: (or the legacy database: alias) with the keys db.py reads."""
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    section = config.get("registry") or config.get("database")
    assert section, f"{path} has neither 'registry:' nor 'database:'"
    missing = REQUIRED_DB_KEYS - set(section)
    assert not missing, f"{path} database section is missing {sorted(missing)}"


@pytest.mark.parametrize("path", EXAMPLES, ids=_ids(EXAMPLES))
def test_example_uses_no_fictional_sections(path):
    """Catch a re-drift toward a schema the code does not read."""
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    found = FICTIONAL_SECTIONS & set(config)
    assert not found, (
        f"{path} declares {sorted(found)}, which backend/ never reads "
        "(api:/security:/vault: are the real names)"
    )


@pytest.mark.parametrize("path", EXAMPLES, ids=_ids(EXAMPLES))
def test_example_admin_userid_can_actually_log_in(path):
    """admin_userid must be an email address.

    backend/api/auth.py declares ``userid: EmailStr``, so a bare "admin" is
    rejected with HTTP 422 before the password is compared -- the shipped
    default could never log in, on any platform.
    """
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    admin_userid = (config.get("security") or {}).get("admin_userid")
    if admin_userid is None:
        pytest.skip("example does not ship a bootstrap admin_userid")
    assert "@" in admin_userid, (
        f"{path} sets admin_userid={admin_userid!r}; the login endpoint "
        "validates it as an email address and rejects anything else with 422"
    )
