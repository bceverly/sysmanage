# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
A host's compliance evidence (ROADMAP 24.4): what its benchmark checks read.

One row per host, replaced by each ``compliance_evidence_update``: the
effective sshd settings, the catalog's sysctls, file modes, kernel modules,
login.defs, PAM, faillock, auditd, AIDE, chrony, umask, FIPS and enabled
services, in the compliance engine's ``host_data`` shapes.  ``sections`` is
a JSON object; a section that is absent or null was NOT collected (the read
needed root and sudo refused it, the OS is not covered yet) and the engine
scores its rules "not applicable", never "fail".  ``sources`` is each
section's collection status, for the operator.  ``received_at`` newer than
the host's latest scan makes the scheduled scan pick the host up.
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text

from backend.persistence.db import Base
from backend.persistence.models.core import GUID


class HostComplianceEvidence(Base):
    """The latest compliance evidence one host reported."""

    __tablename__ = "host_compliance_evidence"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(
        GUID(),
        ForeignKey("host.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    platform = Column(String(32), nullable=True)
    sections = Column(Text, nullable=False)  # JSON object: section -> value
    sources = Column(Text, nullable=True)  # JSON object: section -> status
    collected_at = Column(DateTime, nullable=True)  # the agent's clock
    received_at = Column(DateTime, nullable=False)  # the server's clock
