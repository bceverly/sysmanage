#!/usr/bin/env python3
"""
Prime OpenBAO with the config secrets from sysmanage.yaml (Phase 13.1.H).

The secure-installation flow generates secrets (jwt_secret, password_salt,
admin_password, DB password) and writes them to ``sysmanage.yaml``.  This
helper copies them into OpenBAO's consolidated config secret so they become
the source of truth (the app's startup overlay then reads them from OpenBAO),
moving secrets off disk per docs/planning/config-classification.md.

Idempotent and safe to run any time after OpenBAO is initialized + unsealed
and the app token is in place: it merges into the existing bag.  Best-effort
— if OpenBAO is disabled/unreachable it reports and exits non-zero, leaving
the YAML values (which still work via the fallback) untouched.
"""

import sys


def main() -> int:
    from backend.config import config, secrets_service

    cfg = config.get_config()
    security = cfg.get("security", {}) or {}
    db_block = cfg.get("registry") or cfg.get("database") or {}

    bag = {
        "jwt_secret": security.get("jwt_secret"),
        "password_salt": security.get("password_salt"),
        "admin_password": security.get("admin_password"),
        "admin_userid": security.get("admin_userid"),
        "db_password": db_block.get("password"),
    }
    bag = {k: v for k, v in bag.items() if v}

    if not bag:
        print("No secrets found in sysmanage.yaml to prime into OpenBAO.")
        return 0

    if secrets_service.store_config_secrets(bag):
        print(f"Primed {len(bag)} secret(s) into OpenBAO: {', '.join(sorted(bag))}.")
        print(
            "These are now read from OpenBAO at startup; you may remove them from "
            "sysmanage.yaml in a future config cleanup."
        )
        return 0

    print(
        "Could not prime OpenBAO (vault disabled or unreachable). The secrets in "
        "sysmanage.yaml still work via the fallback.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
