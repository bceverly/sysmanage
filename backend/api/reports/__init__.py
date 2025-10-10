"""
Reports API module - Split from monolithic reports.py for better maintainability
"""

from backend.api.reports.endpoints import router

__all__ = ["router"]
