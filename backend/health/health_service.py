"""
Health analysis service for Pro+ hosts.

This is a thin wrapper that delegates to the health_engine Cython module.
Health analysis requires a Pro+ license with the health_engine module.
"""

from typing import Any, Dict, List, Optional

from backend.licensing.features import ModuleCode
from backend.licensing.license_service import license_service
from backend.licensing.module_loader import module_loader
from backend.persistence import db as db_module
from backend.persistence import models
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.health.health_service")


class HealthAnalysisError(Exception):
    """Exception raised when health analysis fails."""


class HealthService:
    """
    Thin wrapper service for health analysis.
    Delegates to health_engine module.
    """

    def _get_module(self):
        """Get the health_engine module or raise an error."""
        if not license_service.has_module(ModuleCode.HEALTH_ENGINE):
            raise HealthAnalysisError(
                "Health analysis requires Pro+ license with health_engine module"
            )

        health_engine = module_loader.get_module("health_engine")
        if health_engine is None:
            raise HealthAnalysisError("health_engine module is not loaded")

        return health_engine

    def _get_db_session(self):
        """Get a database session."""
        from sqlalchemy.orm import sessionmaker

        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )
        return session_local()

    def analyze_host(self, host_id: str) -> Dict[str, Any]:
        """
        Perform health analysis on a host.

        Args:
            host_id: The host ID to analyze

        Returns:
            Dictionary with analysis results
        """
        health_engine = self._get_module()
        with self._get_db_session() as db:
            return health_engine._health_service.analyze_host(host_id, db, models)

    def get_latest_analysis(self, host_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent health analysis for a host.

        Args:
            host_id: The host ID

        Returns:
            Dictionary with analysis results, or None if no analysis exists
        """
        health_engine = self._get_module()
        with self._get_db_session() as db:
            return health_engine._health_service.get_latest_analysis(
                host_id, db, models
            )

    def get_analysis_history(
        self, host_id: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get health analysis history for a host.

        Args:
            host_id: The host ID
            limit: Maximum number of records to return

        Returns:
            List of analysis results
        """
        health_engine = self._get_module()
        with self._get_db_session() as db:
            return health_engine._health_service.get_analysis_history(
                host_id, limit, db, models
            )


# Global health service instance
health_service = HealthService()
