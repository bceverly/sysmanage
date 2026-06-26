"""
Report templates and branding (Phase 8.7).

Two tables backing the Pro+ ``reporting_engine`` module:

  report_branding
      Singleton row.  Stores organization name + header text + path to a
      logo file under ``storage/branding/`` so generated PDFs and HTMLs
      can render a consistent header.  We intentionally keep this small
      (the user asked for "just logo and header").

  report_template
      Admin-defined custom report layout.  Each row references a
      ``base_report_type`` (one of the reporting_engine ReportTypeEnum
      values) and stores a JSON ``selected_fields`` list dictating which
      columns appear, in what order.

The Pro+ Cython renderer (``reporting_engine.pyx``) reads these tables
at render time;  the OSS server owns the schema + migrations + REST
endpoints so non-Pro+ deployments don't crash on unknown tables.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    JSON,
    LargeBinary,
    String,
    Text,
)

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

# Sentinel id for the singleton ReportBranding row.  Using a fixed UUID
# keeps the upsert pattern simple — there is exactly one branding row
# system-wide (matches the user's "logo + header" feature).
SINGLETON_BRANDING_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class ReportBranding(Base):
    """Singleton row holding org logo + header text used by every report."""

    __tablename__ = "report_branding"

    id = Column(GUID(), primary_key=True, default=lambda: SINGLETON_BRANDING_ID)
    company_name = Column(String(255), nullable=True)
    header_text = Column(String(500), nullable=True)
    # Logo bytes stored inline.  A singleton row + a small (~1 MB max)
    # logo means we don't pay the operational cost of managing a file
    # on disk.  Same pattern as User.profile_image.
    logo_data = Column(LargeBinary, nullable=True)
    # MIME type cached so the GET /logo endpoint can stream without
    # re-sniffing on every request.
    logo_mime_type = Column(String(80), nullable=True)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    updated_by = Column(GUID(), ForeignKey("user.id", ondelete="SET NULL"))

    def __repr__(self):
        return f"<ReportBranding(company='{self.company_name}')>"

    def to_dict(self) -> dict:
        return {
            "company_name": self.company_name,
            "header_text": self.header_text,
            "has_logo": bool(self.logo_data),
            "logo_mime_type": self.logo_mime_type,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ReportTemplate(Base):
    """Admin-defined custom report layout.

    Each template is bound to one ``base_report_type`` (e.g.
    ``registered-hosts``) and lists the fields the operator wants
    rendered, in order.  ``selected_fields`` is a JSON array of field
    codes the renderer recognizes per base type.
    """

    __tablename__ = "report_template"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    base_report_type = Column(String(50), nullable=False, index=True)
    selected_fields = Column(JSON, nullable=False, default=list)
    enabled = Column(Boolean, nullable=False, default=True)

    created_by = Column(GUID(), ForeignKey("user.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return (
            f"<ReportTemplate(id={self.id}, name='{self.name}', "
            f"base='{self.base_report_type}')>"
        )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "base_report_type": self.base_report_type,
            "selected_fields": self.selected_fields or [],
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
