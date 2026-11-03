# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Marker: the OSS backup key read and break-glass export are present (2026-11-03)

No schema change.  A license lapse never locks a customer out of their own
backups (Bryan, 2026-11-03), so reading an encrypted policy's keys for a
restore (``backend/services/backup_keys_read.py``) and the break-glass key
export (``backend/services/backup_breakglass.py``) live in the open-source
server.  The Pro+ backup_engine calls them and no longer carries copies of its
own, so it must never load on a server without them: it requires this
revision (``min_oss_alembic_revision``), and the server's migration-compat
check refuses an engine whose required revision it has not reached.

Upgrade and downgrade do nothing.

Revision ID: q77ossbackupkeys
Revises: q76backupescrow
"""

from typing import Union

revision: str = "q77ossbackupkeys"
down_revision: Union[str, None] = "q76backupescrow"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Nothing to change: the revision itself is the marker."""


def downgrade() -> None:
    """Nothing to undo."""
