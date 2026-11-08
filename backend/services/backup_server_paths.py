# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""What the SysManage server's own backup keeps and leaves out (ROADMAP 25.9).

Its policy is the server host's own ``backup_policy`` row with
``server_preset`` set, and starts from :func:`preset`:

* kept, worst to lose first: the agents' CA and the server identity (lose
  them and every agent must enroll again), OpenBAO's data, PostgreSQL's,
  ``/etc/sysmanage.yaml``, the TLS certificates and the license;
* left out as re-created on demand: downloaded Pro+ engine bundles, the
  GeoIP database, package mirrors on this host and the server's logs.

Whatever the operator then changes, a marked policy always pauses the
databases for the capture (:func:`quiesce`) and always leaves out
:func:`never_paths`: OpenBAO's init material (its unseal or recovery key and
root token) and the server's OpenBAO token.  They go to the operator's
escrow, so a stolen backup cannot unseal the OpenBAO snapshot inside it.
The agent writes keep rules before skip rules and restate's last matching
rule wins, so a kept ``/var/lib/openbao`` still leaves ``init.json`` out.

These are the server's own paths, read from its own configuration -- which
is the right host's, because the marked host is this server.
"""

import os
from pathlib import Path
from typing import Iterable, List, Optional

from backend.config import config

# Packaged installs (installer/openbao): the unseal or recovery key and root
# token, root-only.  Source installs keep them in .vault_credentials.
OPENBAO_INIT = "/var/lib/openbao/init.json"
OPENBAO_DATA = "/var/lib/openbao"
POSTGRESQL_DATA = "/var/lib/postgresql"
DEFAULT_TOKEN_FILE = "/etc/sysmanage/openbao-token"
DEFAULT_CERT_DIR = "/etc/sysmanage/certs"
# nginx's certificate and key on packaged installs (installer/*/sysmanage-nginx.conf).
NGINX_TLS_DIR = "/etc/sysmanage/tls"
SERVER_STATE = "/var/lib/sysmanage"
LETSENCRYPT = "/etc/letsencrypt"
SERVER_LOGS = "/var/log/sysmanage"
_SOURCE_ROOT = Path(__file__).resolve().parents[2]

# restate's hook for OpenBAO (a raft snapshot, or a stopped copy of the file
# backend's data); asked for only once the host's restate reports it.
OPENBAO_HOOK = "openbao"


def _literal(path: str) -> str:
    """``path`` as a restate pattern that matches only itself."""
    out = path
    for special in ("\\", "*", "?"):
        out = out.replace(special, "\\" + special)
    return out


def _absolute(paths: Iterable[Optional[str]]) -> List[str]:
    found: List[str] = []
    for path in paths:
        if not path or not os.path.isabs(path):
            continue
        rule = _literal(os.path.normpath(path))
        if rule not in found:
            found.append(rule)
    return found


def never_paths() -> List[str]:
    """Secret material that is escrowed, never backed up."""
    vault = config.get_vault_config() or {}
    return _absolute(
        [
            OPENBAO_INIT,
            vault.get("token_file") or DEFAULT_TOKEN_FILE,
            str(_SOURCE_ROOT / ".vault_credentials"),
        ]
    )


def _keep() -> List[str]:
    cfg = config.get_config() or {}
    api = cfg.get("api") or {}
    certificates = cfg.get("certificates") or {}
    return _absolute(
        [
            os.environ.get("SYSMANAGE_CERT_PATH")
            or certificates.get("path")
            or DEFAULT_CERT_DIR,
            os.path.abspath(config.CONFIG_PATH),
            api.get("certFile"),
            api.get("keyFile"),
            api.get("chainFile"),
            NGINX_TLS_DIR,
            LETSENCRYPT,
            SERVER_STATE,
            OPENBAO_DATA,
            POSTGRESQL_DATA,
        ]
    )


def _skip(mirror_roots: Iterable[str]) -> List[str]:
    geoip = (config.get_config() or {}).get("geo_lookup") or {}
    database = geoip.get("database_path")
    return _absolute(
        [
            config.get_license_modules_path(),
            os.path.dirname(database) if database else None,
            SERVER_LOGS,
            *mirror_roots,
        ]
    )


def preset(mirror_roots: Iterable[str] = ()) -> dict:
    """The policy fields a new server policy starts from."""
    return {
        "quiesce": True,
        "keep_paths": _keep(),
        "skip_paths": _skip(mirror_roots),
        "never_paths": never_paths(),
    }


def server_policy(policy) -> bool:
    return bool(getattr(policy, "server_preset", False))


def skip_rules(policy, stored: List[str]) -> List[str]:
    """``stored`` plus, for the server's policy, the never-backed-up paths
    last -- so no keep rule can bring them back."""
    if not server_policy(policy):
        return stored
    never = never_paths()
    return [p for p in stored if p not in never] + never


def quiesce(policy) -> bool:
    """The server's databases are always paused for its own capture."""
    return bool(policy.quiesce) or server_policy(policy)


def hooks(policy, stored: List[str], available: Optional[List[str]]) -> List[str]:
    """``stored`` plus, for the server's policy, the ``openbao`` hook once the
    host's restate has it."""
    if not server_policy(policy) or OPENBAO_HOOK not in (available or []):
        return stored
    return stored if OPENBAO_HOOK in stored else stored + [OPENBAO_HOOK]
