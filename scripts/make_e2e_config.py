#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Generate a hermetic config for the Playwright E2E backend.

E2E must NOT depend on the box's OpenBAO / secret-migration state — on a
"migrated" deployment the secrets (``security.jwt_secret`` etc.) live only in a
persistent OpenBAO and are absent from the YAML, so a throwaway ``-dev`` OpenBAO
started for the test has nothing to serve and the backend signs JWTs with an
empty key (``HMAC key must not be empty`` -> login 500).  Exercising the real
OpenBAO instead would make the test brittle.

This copies the config the app would load (so the DB settings are IDENTICAL —
the e2e test user and the e2e backend talk to the same database), injects a
throwaway ``security.jwt_secret`` so JWT signing works, and disables the vault
overlay so the real OpenBAO is never touched.  Only ``jwt_secret`` is injected:
``password_salt`` is left exactly as the source config has it, so password
hashing stays consistent between user-creation and login within a run.

Usage:  python scripts/make_e2e_config.py <output_path>
"""

import os
import secrets
import sys

# Run as ``python scripts/make_e2e_config.py`` puts ``scripts/`` on sys.path[0],
# not the repo root — add the repo root so the server's ``backend`` package is
# importable (matches scripts/e2e_test_user.py).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: make_e2e_config.py <output_path>", file=sys.stderr)
        return 2
    out_path = sys.argv[1]

    import yaml

    # Authoritative resolution of the config the app would load (respects
    # SYSMANAGE_CONFIG_PATH / ProgramData / /etc / dev fallbacks).  Import this
    # WITHOUT SYSMANAGE_CONFIG_PATH pointing at our output, or it self-references.
    from backend.config.config import CONFIG_PATH

    with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle) or {}

    # Inject a throwaway JWT secret so backend.auth.auth_handler.sign_jwt() has a
    # non-empty HMAC key. Random per run — fine, the whole run is self-contained.
    security = cfg.setdefault("security", {})
    if not security.get("jwt_secret"):
        security["jwt_secret"] = secrets.token_urlsafe(48)

    # Keep the real OpenBAO out of the loop entirely (brittleness): the injected
    # secret above is the source of truth for this run.
    vault = cfg.setdefault("vault", {})
    vault["enabled"] = False

    with open(out_path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(cfg, handle, default_flow_style=False, sort_keys=False)

    # Never print secret values — just what was done and from where.
    print(
        f"Wrote hermetic e2e config to {out_path} "
        f"(source: {CONFIG_PATH}; jwt_secret injected, vault disabled)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
