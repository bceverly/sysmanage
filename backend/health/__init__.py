"""
SysManage Pro+ Health Analysis Module.

Provides AI-powered health analysis for hosts using the health_engine Cython module.
"""

from backend.health.health_service import health_service

__all__ = ["health_service"]
