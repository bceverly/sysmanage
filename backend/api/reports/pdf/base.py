"""
Base class for PDF report generation using ReportLab
"""

import io
from typing import List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.i18n import _

# PDF generation imports
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


class ReportGenerator:
    """Base class for report generation"""

    def __init__(self, db: Session):
        self.db = db
        self.styles = getSampleStyleSheet() if REPORTLAB_AVAILABLE else None

    def create_pdf_buffer(self, title: str, content: List) -> io.BytesIO:
        """Create a PDF document from content list"""
        if not REPORTLAB_AVAILABLE:
            raise HTTPException(
                status_code=500,
                detail=_(
                    "PDF generation is not available. Please install reportlab package."
                ),
            )

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            title=title,
            author="SysManage",
            subject=title,
            creator="SysManage Reporting System",
        )

        # Build the document
        doc.build(content)
        buffer.seek(0)
        return buffer
