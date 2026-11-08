#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Idempotent OpenBAO initialize + unseal for a single-node SysManage appliance.

OpenBAO boots **sealed** and must be initialized once and unsealed on every
start before it can serve secrets.  This script makes that hands-off:

  * waits for the local OpenBAO listener to come up;
  * if OpenBAO is **uninitialized**, initializes it (1 key share / threshold
    1 -- a single-node local appliance, auto-unsealed from local material)
    and writes the root token + unseal key(s) to a **root-owned, 0600** file;
  * if OpenBAO is **sealed**, reads that file and unseals it;
  * if OpenBAO is already **unsealed**, does nothing.

Designed to run as a systemd/rc oneshot ordered after the OpenBAO service and
before the SysManage service, AND to be safe to re-run at any time.  Uses only
the Python standard library (urllib) so it works with the system interpreter
during package post-install, before the SysManage venv exists.

Seal-key handling rationale: storing the unseal material locally (locked-down
perms) is the documented shipping mechanism -- it is what makes air-gapped
deployments (where cloud-KMS auto-unseal is unreachable) come up cleanly, and
an air-gapped network is hardened by design.  See
docs/planning/openbao-deployment-and-airgap.md §6.

The key file is never ``sysmanage.yaml``: the config is read by the service
user and travels with every copy of the config, so the unseal key there would
open OpenBAO for anyone holding a copy (ROADMAP 25.9).

Auto-unseal (optional): when ``openbao.hcl`` carries a ``seal`` stanza
(``transit`` against another OpenBAO / Vault, or a cloud KMS), OpenBAO
unseals itself on start.  This script then initializes with *recovery* keys
instead of unseal keys, never submits a key, and waits for the seal to unseal
it -- saying plainly if the key service cannot be reached.  The recovery key
and root token still go to the same root-only key file.
"""

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

DEFAULT_ADDR = "http://127.0.0.1:8200"
DEFAULT_KEYFILE = "/var/lib/openbao/init.json"
# How long an auto-unseal seal gets to reach its key service and unseal.
AUTO_UNSEAL_WAIT_SECONDS = 60


def _api(
    addr: str,
    path: str,
    method: str = "GET",
    payload=None,
    timeout: int = 5,
    token: str = None,
):
    """Call the OpenBAO HTTP API; return (status_code, parsed_json|None)."""
    url = f"{addr.rstrip('/')}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Vault-Token", token)
    try:
        # URL is the local OpenBAO admin endpoint (loopback); not user input.
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
            body = resp.read().decode() or "{}"
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode() or "{}"
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, None


def _wait_for_listener(addr: str, attempts: int = 30, delay: float = 1.0) -> bool:
    """Poll the seal-status endpoint until OpenBAO answers."""
    for _ in range(attempts):
        try:
            status, body = _api(addr, "/v1/sys/seal-status")
            if status == 200 and body is not None:
                return True
        except (urllib.error.URLError, OSError) as exc:
            # Listener not up yet -- retry after the sleep below.
            logger.debug("OpenBAO listener not ready yet: %s", exc)
        time.sleep(delay)
    return False


def _write_keyfile(keyfile: str, payload: dict) -> None:
    """Write init material with restrictive perms (root-owned, 0600)."""
    directory = os.path.dirname(keyfile) or "."
    os.makedirs(directory, exist_ok=True)
    # Create with 0600 from the start (umask-independent) so the secret is
    # never briefly world-readable between create and chmod.
    fd = os.open(keyfile, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(payload, handle)
    finally:
        try:
            os.chmod(keyfile, 0o600)
        except OSError as exc:
            # Best-effort: the file was already created with 0o600 above.
            logger.debug("chmod on keyfile failed (already 0600): %s", exc)


def _unseal(addr: str, keys) -> bool:
    """Submit unseal keys until OpenBAO reports unsealed."""
    for key in keys:
        status, body = _api(addr, "/v1/sys/unseal", "PUT", {"key": key})
        if status == 200 and body is not None and not body.get("sealed", True):
            return True
    _, body = _api(addr, "/v1/sys/seal-status")
    return bool(body) and not body.get("sealed", True)


def _root_token(keyfile: str):
    """Read the root token from the init keyfile, or None."""
    try:
        with open(keyfile, encoding="utf-8") as handle:
            return json.load(handle).get("root_token")
    except (OSError, ValueError):
        return None


def _write_app_token(app_token_file: str, owner, token: str) -> None:
    """Write an app-readable OpenBAO token file (0640, optionally chowned).

    Phase 13.1.H bootstrap: the data-plane app (running as the service user,
    not root) reads this to authenticate to the local OpenBAO, so no token
    lives in sysmanage.yaml.  Single-node appliance: the app token is the root
    token; scoping it to a least-privilege policy is a hardening follow-up.
    """
    directory = os.path.dirname(app_token_file) or "."
    os.makedirs(directory, exist_ok=True)
    fd = os.open(app_token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
    with os.fdopen(fd, "w") as handle:
        handle.write(token)
    if owner:
        try:
            import grp  # noqa: PLC0415
            import pwd  # noqa: PLC0415

            uid = pwd.getpwnam(owner).pw_uid
            gid = grp.getgrnam(owner).gr_gid
            os.chown(app_token_file, uid, gid)
        except (KeyError, OSError, ImportError) as exc:
            # Best-effort chown (owner may not exist / not permitted); the file
            # is still written 0640 and usable by root.
            # Logs only the chown failure (a filesystem error) -- no token value.
            # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
            logger.debug("chown on app token file failed: %s", exc)
    print(f"App OpenBAO token written to {app_token_file} (0640).")


def _ensure_kv_mount(addr: str, token: str, mount: str) -> bool:
    """Enable a kv-v2 secrets engine at ``mount`` unless one is there.

    The app stores secrets under ``<mount>/data/...`` and tenant provisioning
    writes there too; a fresh non-dev OpenBAO has no ``secret/`` mount, so
    without this every write fails with "no handler for route".
    """
    status, mounts = _api(addr, "/v1/sys/mounts", token=token)
    if status != 200 or mounts is None:
        print(f"ERROR: listing secrets engines failed: {status}", file=sys.stderr)
        return False
    existing = (mounts.get("data") or mounts).get(f"{mount}/")
    if existing:
        version = (existing.get("options") or {}).get("version")
        if existing.get("type") != "kv" or version != "2":
            print(
                f"WARNING: '{mount}/' is mounted as {existing.get('type')} "
                f"(version {version}), not kv-v2; leaving it alone",
                file=sys.stderr,
            )
        return True
    status, _ = _api(
        addr,
        f"/v1/sys/mounts/{mount}",
        "POST",
        {"type": "kv", "options": {"version": "2"}},
        token=token,
    )
    if status not in (200, 204):
        print(f"ERROR: enabling kv-v2 at '{mount}/' failed: {status}", file=sys.stderr)
        return False
    print(f"Enabled kv-v2 secrets engine at '{mount}/'.")
    return True


def _auto_unseal(seal: dict) -> bool:
    """True when OpenBAO unseals itself (a transit or KMS ``seal`` stanza)."""
    return bool(seal.get("recovery_seal")) or seal.get("type", "shamir") != "shamir"


def _wait_unsealed(addr: str, seconds: float, delay: float = 1.0) -> bool:
    """Poll seal-status until OpenBAO reports unsealed, for up to ``seconds``."""
    deadline = time.monotonic() + seconds
    while True:
        _, body = _api(addr, "/v1/sys/seal-status")
        if body is not None and not body.get("sealed", True):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(delay)


def _initialize(addr: str, keyfile: str, auto: bool) -> int:
    """Initialize OpenBAO once and write its material to ``keyfile``."""
    if auto:
        print("Initializing OpenBAO (auto-unseal seal, 1 recovery key share)...")
        payload = {"recovery_shares": 1, "recovery_threshold": 1}
    else:
        print("Initializing OpenBAO (single-node appliance, 1 key share)...")
        payload = {"secret_shares": 1, "secret_threshold": 1}
    status, init = _api(addr, "/v1/sys/init", "PUT", payload)
    if status != 200 or init is None:
        print(f"ERROR: init failed: {status}", file=sys.stderr)
        return 1
    material = {"root_token": init.get("root_token")}
    if auto:
        material["recovery_keys"] = (
            init.get("recovery_keys_base64") or init.get("recovery_keys") or []
        )
    else:
        material["unseal_keys"] = init.get("keys_base64") or init.get("keys") or []
    _write_keyfile(keyfile, material)
    print(f"OpenBAO initialized; material written to {keyfile} (0600).")
    return 0


def _seal_unreachable(seal_type: str) -> int:
    print(
        f"ERROR: OpenBAO uses an auto-unseal seal ({seal_type}) and is still sealed "
        f"after {AUTO_UNSEAL_WAIT_SECONDS}s.\n"
        "  The seal could not reach its key service.  Check the seal stanza in\n"
        "  openbao.hcl (address, key name, credentials) and that the key service\n"
        "  is up and reachable from this host, then restart OpenBAO.",
        file=sys.stderr,
    )
    return 1


def _ensure_unsealed(addr: str, keyfile: str) -> int:
    """Initialize (once) + unseal OpenBAO.  Returns 0 on success."""
    status, seal = _api(addr, "/v1/sys/seal-status")
    if status != 200 or seal is None:
        print(f"ERROR: unexpected seal-status response: {status}", file=sys.stderr)
        return 1

    if seal.get("initialized") and not seal.get("sealed"):
        print("OpenBAO already initialized and unsealed.")
        return 0

    auto = _auto_unseal(seal)
    if not seal.get("initialized"):
        rc = _initialize(addr, keyfile, auto)
        if rc != 0:
            return rc

    if auto:
        # The seal unseals OpenBAO by itself; never submit a key.
        if _wait_unsealed(addr, AUTO_UNSEAL_WAIT_SECONDS):
            print(f"OpenBAO unsealed by its {seal.get('type')} seal.")
            return 0
        return _seal_unreachable(seal.get("type", "auto-unseal"))

    if not os.path.exists(keyfile):
        print(
            f"ERROR: OpenBAO is sealed but no key material at {keyfile}",
            file=sys.stderr,
        )
        return 1
    with open(keyfile, encoding="utf-8") as handle:
        material = json.load(handle)
    if _unseal(addr, material.get("unseal_keys", [])):
        print("OpenBAO unsealed.")
        return 0
    print("ERROR: unseal failed", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize + unseal OpenBAO.")
    parser.add_argument("--addr", default=os.environ.get("BAO_ADDR", DEFAULT_ADDR))
    parser.add_argument("--keyfile", default=DEFAULT_KEYFILE)
    parser.add_argument(
        "--app-token-file",
        default=None,
        help="Write an app-readable token here so the service can auth to OpenBAO.",
    )
    parser.add_argument(
        "--app-token-owner",
        default=None,
        help="chown the app token file to this user/group (e.g. 'sysmanage').",
    )
    parser.add_argument(
        "--kv-mount",
        default="secret",
        help="Ensure a kv-v2 secrets engine at this path (vault.mount_path).",
    )
    args = parser.parse_args()

    if not _wait_for_listener(args.addr):
        print(
            f"ERROR: OpenBAO listener at {args.addr} did not come up", file=sys.stderr
        )
        return 1

    rc = _ensure_unsealed(args.addr, args.keyfile)
    if rc != 0:
        return rc

    # Best-effort: OpenBAO is unsealed either way, and failing this unit would
    # hold the server down over a mount the operator can add by hand.
    token = _root_token(args.keyfile)
    if token:
        _ensure_kv_mount(args.addr, token, args.kv_mount)

    # Deliver the app token (idempotent) once OpenBAO is unsealed.
    if args.app_token_file:
        if token:
            _write_app_token(args.app_token_file, args.app_token_owner, token)
        else:
            print(
                f"WARNING: no root token in {args.keyfile}; app token not written",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
