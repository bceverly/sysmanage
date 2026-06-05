"""Read/write accessors for the ``server_configuration`` singleton.

Centralises DB access for server-instance-wide settings (currently
just the air-gap ``server_role``) so the config module, the API
handler, and any future caller share one code path — and so a missing
row degrades gracefully to the default instead of raising.
"""

from __future__ import annotations

import logging

from backend.persistence import db, models
from backend.persistence.models.server_configuration import (
    DEFAULT_FEDERATION_ROLE,
    DEFAULT_SERVER_ROLE,
    SINGLETON_SERVER_CONFIG_ID,
    VALID_FEDERATION_ROLES,
    VALID_SERVER_ROLES,
)

logger = logging.getLogger(__name__)


def get_server_role() -> str:
    """Return the configured server role, or the default on any failure.

    Reads the singleton ``server_configuration`` row.  Falls back to
    ``DEFAULT_SERVER_ROLE`` ("standard") when the row is missing or the
    DB isn't reachable — the role is non-critical metadata, so a lookup
    failure should degrade to "no air gap" rather than crash the caller.
    """
    try:
        session_local = db.get_session_local()
        with session_local() as session:
            row = session.query(models.ServerConfiguration).first()
            if row is None or not row.server_role:
                return DEFAULT_SERVER_ROLE
            return row.server_role
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Could not read server_role from DB; defaulting: %s", exc)
        return DEFAULT_SERVER_ROLE


def set_server_role(role: str) -> str:
    """Persist the server role to the singleton row.

    Upserts the singleton (creating it with the sentinel id if a fresh
    DB somehow lacks it).  Raises ``ValueError`` on an invalid role so
    the API layer can turn it into a 400.  Returns the stored role.
    """
    if role not in VALID_SERVER_ROLES:
        raise ValueError(
            f"invalid server role {role!r}; must be one of: "
            f"{', '.join(VALID_SERVER_ROLES)}"
        )
    session_local = db.get_session_local()
    with session_local() as session:
        row = session.query(models.ServerConfiguration).first()
        if row is None:
            row = models.ServerConfiguration(
                id=SINGLETON_SERVER_CONFIG_ID, server_role=role
            )
            session.add(row)
        else:
            row.server_role = role
        session.commit()
    return role


def get_federation_role() -> str:
    """Return the configured federation role, or the default on any failure.

    Separate axis from :func:`get_server_role` — reads ``federation_role``
    from the same singleton row.  Falls back to ``DEFAULT_FEDERATION_ROLE``
    ("none") when the row is missing or the DB isn't reachable.
    """
    try:
        session_local = db.get_session_local()
        with session_local() as session:
            row = session.query(models.ServerConfiguration).first()
            if row is None or not row.federation_role:
                return DEFAULT_FEDERATION_ROLE
            return row.federation_role
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Could not read federation_role from DB; defaulting: %s", exc)
        return DEFAULT_FEDERATION_ROLE


def set_federation_role(role: str) -> str:
    """Persist the federation role to the singleton row.

    Upserts the singleton (creating it with the sentinel id if a fresh DB
    lacks it).  Raises ``ValueError`` on an invalid role.  Returns the
    stored role.
    """
    if role not in VALID_FEDERATION_ROLES:
        raise ValueError(
            f"invalid federation role {role!r}; must be one of: "
            f"{', '.join(VALID_FEDERATION_ROLES)}"
        )
    session_local = db.get_session_local()
    with session_local() as session:
        row = session.query(models.ServerConfiguration).first()
        if row is None:
            row = models.ServerConfiguration(
                id=SINGLETON_SERVER_CONFIG_ID, federation_role=role
            )
            session.add(row)
        else:
            row.federation_role = role
        session.commit()
    return role


def get_import_device():
    """Return the configured air-gap import block device, or None.

    The device node (e.g. ``/dev/sr0``) an Air-Gap Repository operator
    picked as the import drive.  None when unset or on any DB failure.
    """
    try:
        session_local = db.get_session_local()
        with session_local() as session:
            row = session.query(models.ServerConfiguration).first()
            return row.airgap_import_device if row else None
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Could not read airgap_import_device from DB: %s", exc)
        return None


def set_import_device(device):
    """Persist the air-gap import block device (or None to clear)."""
    session_local = db.get_session_local()
    with session_local() as session:
        row = session.query(models.ServerConfiguration).first()
        if row is None:
            row = models.ServerConfiguration(
                id=SINGLETON_SERVER_CONFIG_ID,
                server_role=DEFAULT_SERVER_ROLE,
                airgap_import_device=device,
            )
            session.add(row)
        else:
            row.airgap_import_device = device
        session.commit()
    return device
