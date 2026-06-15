"""
Startup secrets overlay — Phase 13.1.H (config classification).

Several secrets are read at *import* time and captured in module globals
(notably ``backend.auth.auth_handler.JWT_SECRET``) or pulled directly from
the in-memory config dict (``security.password_salt``,
``security.admin_password``, the DB password).  Those can't be migrated to a
lazy OpenBAO read without a per-call vault hit and without breaking the test
harness that patches the globals.

Instead, once OpenBAO is up (the init/unseal one-shot unseals it before the
app starts), :func:`refresh_secrets_from_openbao` reads the consolidated
config-secret bag and **overlays** the values onto the live config dict and
the captured module globals.  Because the functions look those names up at
call time, re-assigning them updates every subsequent caller with zero churn
to call sites or tests.

Behavior is unchanged when OpenBAO is disabled/empty: the YAML values loaded
at import remain in force.  This is how B-bucket secrets actually move into
OpenBAO while keeping a deployment that hasn't migrated working.
"""

import logging

logger = logging.getLogger(__name__)

# Secret keys that live under config["security"].
_SECURITY_KEYS = ("jwt_secret", "password_salt", "admin_password", "admin_userid")


def refresh_secrets_from_openbao() -> bool:
    """Overlay OpenBAO config secrets onto the live config + module globals.

    Returns True if any secret was overlaid, False otherwise.  Best-effort:
    never raises (a failure just leaves the YAML-loaded values in place).
    """
    try:
        from backend.config import config, secrets_service  # noqa: PLC0415

        bag = secrets_service.get_config_secret_bag()
        if not isinstance(bag, dict) or not bag:
            return False

        cfg = config.get_config()
        overlaid = []

        security = cfg.setdefault("security", {})
        for key in _SECURITY_KEYS:
            value = bag.get(key)
            if value:
                security[key] = value
                overlaid.append(key)

        # DB password lives under both the legacy ``database`` and the new
        # ``registry`` blocks (alias-and-deprecate), so update whichever exist.
        db_password = bag.get("db_password")
        if db_password:
            for block in ("database", "registry"):
                if isinstance(cfg.get(block), dict):
                    cfg[block]["password"] = db_password
            overlaid.append("db_password")

        # Re-sync the JWT secret captured at import in auth_handler so already-
        # imported sign/verify functions pick up the OpenBAO value.
        if bag.get("jwt_secret"):
            from backend.auth import auth_handler  # noqa: PLC0415

            auth_handler.JWT_SECRET = bag["jwt_secret"]

        if overlaid:
            # Logs only secret *names* (e.g. "jwt_secret"), never values.
            # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
            logger.info(
                "Overlaid %d secret(s) from OpenBAO: %s",
                len(overlaid),
                ", ".join(overlaid),
            )
        return bool(overlaid)
    # Best-effort overlay: a failure here must never block boot.
    except Exception as exc:  # noqa: BLE001
        # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
        logger.warning("Secret overlay from OpenBAO skipped: %s", exc)
        return False
