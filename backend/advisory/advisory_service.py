# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Advisory / errata service for Pro+ hosts (Phase 14.1).

A thin wrapper that delegates to the ``advisory_engine`` Cython module (the moat).
Advisory management requires a Pro+ license with the ``advisory_engine`` module.
Mirrors ``backend/vulnerability/vulnerability_service.py``.
"""

from typing import Any, Dict, List, Optional

from backend.licensing.features import ModuleCode
from backend.licensing.license_service import license_service
from backend.licensing.module_loader import module_loader
from backend.persistence import db as db_module
from backend.persistence import models
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.advisory.advisory_service")


class AdvisoryServiceError(Exception):
    """Raised when advisory operations fail."""


class AdvisoryService:
    """Thin wrapper delegating to the ``advisory_engine`` module.

    Uses the main engine for both the tenant and shared sessions (collapsed
    mode).  The MT-aware routing lives in the engine's router factory, which the
    server mounts separately with ``get_tenant_db`` / ``get_shared_db``.
    """

    def _get_module(self):
        if not license_service.has_module(ModuleCode.ADVISORY_ENGINE):
            raise AdvisoryServiceError(
                "Advisory management requires a Pro+ license with the "
                "advisory_engine module"
            )
        engine = module_loader.get_module("advisory_engine")
        if engine is None:
            raise AdvisoryServiceError("advisory_engine module is not loaded")
        return engine

    def _get_db_session(self):
        from sqlalchemy.orm import sessionmaker

        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )
        return session_local()

    def compute_applicable_advisories(self, host_id: str) -> Dict[str, Any]:
        """Recompute a host's applicable advisories from the shared catalog."""
        engine = self._get_module()
        with self._get_db_session() as db:
            return engine._advisory_service.compute_applicable_advisories(
                host_id, db, models, adv_db=db
            )

    def get_applicable_advisories(self, host_id: str) -> Dict[str, Any]:
        """Stored applicable advisories for a host."""
        engine = self._get_module()
        with self._get_db_session() as db:
            return engine._advisory_service.get_applicable_advisories(
                host_id, db, models
            )

    def list_advisories(
        self,
        source: Optional[str] = None,
        severity: Optional[str] = None,
        advisory_type: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """List the shared advisory catalog with optional filters."""
        engine = self._get_module()
        with self._get_db_session() as db:
            return engine._advisory_service.list_advisories(
                db,
                models,
                source=source,
                severity=severity,
                advisory_type=advisory_type,
                search=search,
                limit=limit,
                offset=offset,
            )

    def get_advisory_detail(self, advisory_row_id: str) -> Optional[Dict[str, Any]]:
        """One advisory with packages + CVE links."""
        engine = self._get_module()
        with self._get_db_session() as db:
            return engine._advisory_service.get_advisory_detail(
                advisory_row_id, db, models
            )

    def get_fleet_summary(self) -> Dict[str, Any]:
        """Fleet-wide applicable-advisory rollup."""
        engine = self._get_module()
        with self._get_db_session() as db:
            return engine._advisory_service.get_fleet_summary(db, models)

    def refresh_advisories(self, sources: Optional[List[str]] = None) -> Dict[str, Any]:
        """Refresh the advisory catalog from the configured sources."""
        engine = self._get_module()
        with self._get_db_session() as db:
            return engine._advisory_service.refresh_advisories(
                db, models, sources=sources
            )


# Global advisory service instance.
advisory_service = AdvisoryService()
