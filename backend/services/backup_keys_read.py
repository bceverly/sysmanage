# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Reading an encrypted policy's secret keys out of OpenBAO -- in every edition.

Making, rotating and turning on encryption are Pro+ (backup_engine).  READING
the keys a restore, a listing, a what-changed, a diff or a verification of an
encrypted repository needs is not: "please don't hold someone's safety
hostage" (Bryan, 2026-11-03).  A lapsed license never locks a customer out of
their own backups, so this lives in the open-source server, and the Pro+
engine calls it rather than keeping a second copy.

The keys are every key the policy has held and not retired, newest first: a
capture after a rotation reuses packs written before it (24.6 S5).  They are
fetched for ONE job and handed straight to the agent (backup_key_release);
nothing here stores them.
"""

from typing import List, Optional

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence import models

PRIVATE_KEY_MARKER = "BEGIN PGP PRIVATE KEY BLOCK"


class BackupKeyReadError(Exception):
    """A policy's key could not be read from OpenBAO; the message says why."""


def key_references(db: Optional[Session], policy) -> List[str]:
    """The OpenBAO references of the policy's keys, newest first, the
    policy's current key always among them."""
    references: List[str] = []
    if db is not None:
        rows = (
            db.query(models.BackupPolicyKey)
            .filter(
                models.BackupPolicyKey.policy_id == policy.id,
                models.BackupPolicyKey.retired_at.is_(None),
            )
            .order_by(models.BackupPolicyKey.created_at.desc())
            .all()
        )
        references = [row.key_ref for row in rows if row.key_ref]
    current = getattr(policy, "encrypt_key_ref", None)
    if current and current not in references:
        references.insert(0, current)
    return references


def secret_keys(policy, db: Optional[Session] = None, vault=None) -> List[str]:
    """The armored secret keys of the policy's encrypted repository."""
    references = key_references(db, policy)
    if not references:
        raise BackupKeyReadError(_("This policy has no backup key in OpenBAO"))
    if vault is None:
        # pylint: disable=import-outside-toplevel
        from backend.services.vault_service import VaultService

        vault = VaultService()
    found = []
    for reference in references:
        stored = vault.retrieve_secret(reference)
        content = stored.get("content") if isinstance(stored, dict) else None
        if not isinstance(content, str) or PRIVATE_KEY_MARKER not in content:
            raise BackupKeyReadError(
                _("OpenBAO does not hold this policy's backup key")
            )
        found.append(content)
    return found
