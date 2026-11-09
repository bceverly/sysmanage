# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""restate-proxy: how hosts reach a target's storage (ROADMAP 25.5).

A target's ``transport`` is ``nfs`` (every target until now, unchanged) or
``proxy``: ``restate-proxy`` runs on the storage host and hosts reach their
repositories at ``https://<proxy_host>:<proxy_port>/v1/<client>``.  The
repositories stay where they are on disk, so a target switches either way.

* **Clients and grants.**  A host's client name is its host id, and
  ``<host id>.previous`` reads the repository before Pro+ encryption.  The
  storage host's agent writes one grant file per client from what
  ``storage_proxy`` sends, and removes the ones it no longer gets.
* **Tokens are the host's own.**  The backed-up host makes each token
  itself, keeps it root's alone, and reports only its SHA-256; the grant
  names that hash.  No token is ever in a command, the queue or a database.
  A new hash keeps the one before it in the grant for one more configure,
  so a job started with the old token still finishes.
* **Reading first.**  restate 3.1.0.0 reads through the proxy (snapshots,
  list, diff, status, check, restore); capture through it is restate
  3.2.0.0.  So a host is told about the proxy only once its restate reports
  ``remote_repository``, it reads through it from then on, and it captures
  over NFS until capture through the proxy ships.
"""

import ipaddress
import json
import re
from typing import Any, Dict, List, Optional

from cryptography import x509
from sqlalchemy.orm import Session

from backend.persistence import models

NFS = "nfs"
PROXY = "proxy"
TRANSPORTS = (NFS, PROXY)
DEFAULT_PORT = 8443
# The host's restate can read a repository through the proxy (3.1.0.0).
REMOTE_ABILITY = "remote_repository"
PREVIOUS_SUFFIX = ".previous"
# Grants: the current repository is appended to and read; the one before
# Pro+ encryption only read.
CURRENT_OPERATIONS = ["append", "read"]
PREVIOUS_OPERATIONS = ["read"]
MAX_CA_BYTES = 64 * 1024

_HOSTNAME = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CERT = "-----BEGIN CERTIFICATE-----"


class ProxySettingsRefused(ValueError):
    """A transport setting that cannot be used; the message says why."""


def check_host(value: Any) -> str:
    """The proxy's name or address, as hosts will reach it."""
    text = (value or "").strip() if isinstance(value, str) else ""
    try:
        return str(ipaddress.ip_address(text.strip("[]")))
    except ValueError:
        pass
    if not _HOSTNAME.match(text):
        raise ProxySettingsRefused("The proxy address is not a host name or IP address")
    return text.lower()


def check_settings(
    transport: str,
    host: Optional[str],
    port: Optional[int],
    pin: Optional[str],
    ca_pem: Optional[str],
) -> Dict[str, Any]:
    """The target's transport columns, checked; NFS clears the rest."""
    if transport not in TRANSPORTS:
        raise ProxySettingsRefused("Unknown transport")
    if transport == NFS:
        return {"transport": NFS, "proxy_host": None, "proxy_port": None,
                "proxy_pin_sha256": None, "proxy_ca_pem": None}  # fmt: skip
    port = DEFAULT_PORT if port is None else port
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ProxySettingsRefused("The proxy port must be between 1 and 65535")
    pin = (pin or "").strip().lower() or None
    if pin is not None and not _SHA256.match(pin):
        raise ProxySettingsRefused(
            "The pinned key must be a SHA-256 in hex (64 characters)"
        )
    ca_pem = (ca_pem or "").strip() or None
    if ca_pem is not None:
        if len(ca_pem) > MAX_CA_BYTES or not ca_pem.startswith(_CERT):
            raise ProxySettingsRefused("The proxy's CA must be a PEM certificate")
        try:
            x509.load_pem_x509_certificate(ca_pem.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as error:
            raise ProxySettingsRefused(
                "The proxy's CA must be a PEM certificate"
            ) from error
        ca_pem += "\n"
    return {"transport": PROXY, "proxy_host": check_host(host), "proxy_port": port,
            "proxy_pin_sha256": pin, "proxy_ca_pem": ca_pem}  # fmt: skip


def uses_proxy(target: Optional[models.BackupTarget]) -> bool:
    return (
        target is not None
        and getattr(target, "transport", None) == PROXY
        and bool(getattr(target, "proxy_host", None))
    )


def base_url(target: models.BackupTarget) -> str:
    host = target.proxy_host
    if ":" in host:  # an IPv6 address
        host = f"[{host}]"
    return f"https://{host}:{target.proxy_port or DEFAULT_PORT}"


def client_name(host: models.Host) -> str:
    return str(host.id)


def _abilities(policy: models.BackupPolicy) -> List[str]:
    try:
        found = json.loads(policy.host_abilities or "[]")
    except ValueError:
        return []
    return found if isinstance(found, list) else []


def host_reads_through_proxy(policy: models.BackupPolicy) -> bool:
    """The host's restate reported it can read through the proxy."""
    return REMOTE_ABILITY in _abilities(policy)


def _trust(target: models.BackupTarget) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if target.proxy_pin_sha256:
        out["pin_sha256"] = target.proxy_pin_sha256
    if target.proxy_ca_pem:
        out["ca"] = target.proxy_ca_pem
    return out


def host_proxy(
    policy: models.BackupPolicy, target: models.BackupTarget, host: models.Host
) -> Dict[str, Any]:
    """``{"proxy": {...}}`` for the host's target, or ``{}``: where it reads
    its repository through the proxy, and whether the one before Pro+
    encryption is there too.  Nothing until the host's restate can."""
    if not uses_proxy(target) or not host_reads_through_proxy(policy):
        return {}
    url = f"{base_url(target)}/v1/{client_name(host)}"
    out: Dict[str, Any] = {"url": url, **_trust(target)}
    if policy.previous_repository_dir:
        out["previous_url"] = url + PREVIOUS_SUFFIX
    return {"proxy": out}


def _grants(policy: models.BackupPolicy, host: models.Host) -> List[Dict[str, Any]]:
    """This host's grants: the current repository's, and the one before Pro+
    encryption's (named by its directory) -- each once the host has made
    its token."""
    current = [h for h in (policy.proxy_token_sha256, policy.proxy_token_sha256_old)
               if h]  # fmt: skip
    if not current:
        return []
    client = client_name(host)
    grants: List[Dict[str, Any]] = [
        {"client": client, "token_sha256": current, "operations": CURRENT_OPERATIONS}
    ]
    if policy.previous_repository_dir and policy.proxy_previous_token_sha256:
        grants.append({
            "client": client + PREVIOUS_SUFFIX,
            "token_sha256": [policy.proxy_previous_token_sha256],
            "operations": PREVIOUS_OPERATIONS,
            "repo_dir": policy.previous_repository_dir,
        })  # fmt: skip
    return grants


def target_clients(db: Session, target: models.BackupTarget) -> List[str]:
    """Every client the target's storage host may keep a grant for: each
    backed-up host there is (a deleted host's policy goes with it), and its
    previous repository's."""
    if not uses_proxy(target):
        return []
    clients = set()
    rows = (
        db.query(models.BackupPolicy, models.Host)
        .join(models.Host, models.Host.id == models.BackupPolicy.host_id)
        .filter(models.BackupPolicy.target_id == target.id)
        .all()
    )
    for policy, host in rows:
        clients.add(client_name(host))
        if policy.previous_repository_dir:
            clients.add(client_name(host) + PREVIOUS_SUFFIX)
    return sorted(clients)


def sync_clients(db: Session, target: models.BackupTarget) -> bool:
    """Re-send the storage host's grants when the target's clients changed
    since it was last told -- a host joined, left or was deleted -- so a
    grant never outlives its host.  True when they were re-sent."""
    clients = json.dumps(target_clients(db, target))
    if (target.proxy_clients or "[]") == clients:
        return False
    target.proxy_clients = clients
    for policy in (
        db.query(models.BackupPolicy)
        .filter(models.BackupPolicy.target_id == target.id)
        .all()
    ):
        policy.config_version += 1
    return True


def storage_proxy(
    db: Session,
    policy: models.BackupPolicy,
    target: models.BackupTarget,
    host: models.Host,
) -> Dict[str, Any]:
    """``{"proxy": {...}}`` for the storage side of one host's repository,
    sent whatever the transport: the grants its agent writes for this host,
    and every client the target has, so the agent removes the grants it
    wrote for any other (none at all when the target is back on NFS)."""
    enabled = uses_proxy(target)
    return {
        "proxy": {
            "target_id": str(target.id),
            "enabled": enabled,
            "grants": _grants(policy, host) if enabled else [],
            "clients": target_clients(db, target),
        }
    }


def store_tokens(policy: Optional[models.BackupPolicy], reply: Any) -> bool:
    """Keep the token hashes the host reported in its configure reply
    (``proxy_tokens``: ``current`` and ``previous``).  A new current hash
    keeps the one it replaces in the grant until the host reports the new
    one again; True when the storage side needs its grants again."""
    tokens = reply.get("proxy_tokens") if isinstance(reply, dict) else None
    if policy is None or not isinstance(tokens, dict):
        return False
    current = tokens.get("current")
    previous = tokens.get("previous")
    current = current if isinstance(current, str) and _SHA256.match(current) else None
    previous = (
        previous if isinstance(previous, str) and _SHA256.match(previous) else None
    )
    before = (policy.proxy_token_sha256, policy.proxy_token_sha256_old,
              policy.proxy_previous_token_sha256)  # fmt: skip
    if current != policy.proxy_token_sha256:
        policy.proxy_token_sha256_old = policy.proxy_token_sha256
        policy.proxy_token_sha256 = current
    else:
        policy.proxy_token_sha256_old = None  # the host kept the new token
    policy.proxy_previous_token_sha256 = previous
    return before != (policy.proxy_token_sha256, policy.proxy_token_sha256_old,
                      policy.proxy_previous_token_sha256)  # fmt: skip


def target_view(target: models.BackupTarget) -> Dict[str, Any]:
    """The transport, for the Backups page."""
    if not uses_proxy(target):
        return {"transport": NFS}
    return {
        "transport": PROXY,
        "proxy_host": target.proxy_host,
        "proxy_port": target.proxy_port or DEFAULT_PORT,
        "proxy_pin_sha256": target.proxy_pin_sha256,
        "proxy_ca": bool(target.proxy_ca_pem),
        "url": base_url(target),
    }
