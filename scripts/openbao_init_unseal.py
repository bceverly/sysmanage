#!/usr/bin/env python3
"""
Idempotent OpenBAO initialize + unseal for a single-node SysManage appliance.

OpenBAO boots **sealed** and must be initialized once and unsealed on every
start before it can serve secrets.  This script makes that hands-off:

  * waits for the local OpenBAO listener to come up;
  * if OpenBAO is **uninitialized**, initializes it (1 key share / threshold
    1 — a single-node local appliance, auto-unsealed from local material)
    and writes the root token + unseal key(s) to a **root-owned, 0600** file;
  * if OpenBAO is **sealed**, reads that file and unseals it;
  * if OpenBAO is already **unsealed**, does nothing.

Designed to run as a systemd/rc oneshot ordered after the OpenBAO service and
before the SysManage service, AND to be safe to re-run at any time.  Uses only
the Python standard library (urllib) so it works with the system interpreter
during package post-install, before the SysManage venv exists.

Seal-key handling rationale: storing the unseal material locally (locked-down
perms) is the documented shipping mechanism — it is what makes air-gapped
deployments (where cloud-KMS auto-unseal is unreachable) come up cleanly, and
an air-gapped network is hardened by design.  KMS/transit auto-unseal for
internet-connected hardened deployments is a future enhancement.  See
docs/planning/openbao-deployment-and-airgap.md §6.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_ADDR = "http://127.0.0.1:8200"
DEFAULT_KEYFILE = "/var/lib/openbao/init.json"


def _api(addr: str, path: str, method: str = "GET", payload=None, timeout: int = 5):
    """Call the OpenBAO HTTP API; return (status_code, parsed_json|None)."""
    url = f"{addr.rstrip('/')}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
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
        except (urllib.error.URLError, OSError):
            pass
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
        except OSError:
            pass


def _unseal(addr: str, keys) -> bool:
    """Submit unseal keys until OpenBAO reports unsealed."""
    for key in keys:
        status, body = _api(addr, "/v1/sys/unseal", "PUT", {"key": key})
        if status == 200 and body is not None and not body.get("sealed", True):
            return True
    _, body = _api(addr, "/v1/sys/seal-status")
    return bool(body) and not body.get("sealed", True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize + unseal OpenBAO.")
    parser.add_argument("--addr", default=os.environ.get("BAO_ADDR", DEFAULT_ADDR))
    parser.add_argument("--keyfile", default=DEFAULT_KEYFILE)
    args = parser.parse_args()

    if not _wait_for_listener(args.addr):
        print(
            f"ERROR: OpenBAO listener at {args.addr} did not come up", file=sys.stderr
        )
        return 1

    status, seal = _api(args.addr, "/v1/sys/seal-status")
    if status != 200 or seal is None:
        print(f"ERROR: unexpected seal-status response: {status}", file=sys.stderr)
        return 1

    # Already initialized + unsealed → nothing to do.
    if seal.get("initialized") and not seal.get("sealed"):
        print("OpenBAO already initialized and unsealed.")
        return 0

    if not seal.get("initialized"):
        print("Initializing OpenBAO (single-node appliance, 1 key share)...")
        status, init = _api(
            args.addr,
            "/v1/sys/init",
            "PUT",
            {"secret_shares": 1, "secret_threshold": 1},
        )
        if status != 200 or init is None:
            print(f"ERROR: init failed: {status}", file=sys.stderr)
            return 1
        keys = init.get("keys_base64") or init.get("keys") or []
        _write_keyfile(
            args.keyfile,
            {"root_token": init.get("root_token"), "unseal_keys": keys},
        )
        print(f"OpenBAO initialized; material written to {args.keyfile} (0600).")
        if _unseal(args.addr, keys):
            print("OpenBAO unsealed.")
            return 0
        print("ERROR: unseal after init failed", file=sys.stderr)
        return 1

    # Initialized but sealed → unseal from stored material.
    if not os.path.exists(args.keyfile):
        print(
            f"ERROR: OpenBAO is sealed but no key material at {args.keyfile}",
            file=sys.stderr,
        )
        return 1
    with open(args.keyfile, encoding="utf-8") as handle:
        material = json.load(handle)
    if _unseal(args.addr, material.get("unseal_keys", [])):
        print("OpenBAO unsealed.")
        return 0
    print("ERROR: unseal failed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
