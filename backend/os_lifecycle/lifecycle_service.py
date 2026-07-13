"""
OS lifecycle / release-upgrade service for Pro+ hosts (Phase 14.3).

A thin wrapper that delegates to the ``lifecycle_engine`` Cython module (the moat).
OS lifecycle management requires a Pro+ license with the ``lifecycle_engine``
module.  Mirrors ``backend/advisory/advisory_service.py``.

The heavy read/report endpoints are served directly by the engine's router
(mounted MT-aware in ``proplus_routes.py``).  This wrapper exists for the OSS
seam that needs to reach the engine *outside* a request — chiefly the
release-upgrade **dispatch** action (``backend/api/lifecycle_actions.py``),
which creates a job via the engine and then enqueues the command through the
store-and-forward queue (maintenance-window aware).
"""

from typing import Any, Dict, List, Optional

from backend.licensing.features import ModuleCode
from backend.licensing.license_service import license_service
from backend.licensing.module_loader import module_loader
from backend.persistence import db as db_module
from backend.persistence import models
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.os_lifecycle.lifecycle_service")


class LifecycleServiceError(Exception):
    """Raised when OS-lifecycle operations fail."""


class LifecycleService:
    """Thin wrapper delegating to the ``lifecycle_engine`` module.

    Uses the main engine for both the tenant and shared sessions (collapsed
    mode).  The MT-aware routing lives in the engine's router factory, which the
    server mounts separately with ``get_tenant_db`` / ``get_shared_db``.
    """

    def _get_module(self):
        if not license_service.has_module(ModuleCode.LIFECYCLE_ENGINE):
            raise LifecycleServiceError(
                "OS lifecycle management requires a Pro+ license with the "
                "lifecycle_engine module"
            )
        engine = module_loader.get_module("lifecycle_engine")
        if engine is None:
            raise LifecycleServiceError("lifecycle_engine module is not loaded")
        return engine

    def _get_db_session(self):
        from sqlalchemy.orm import sessionmaker

        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )
        return session_local()

    def compute_host_eol(self, host_id: str) -> Dict[str, Any]:
        """EOL status for one host, computed against the shared registry."""
        engine = self._get_module()
        with self._get_db_session() as db:
            return engine._lifecycle_service.compute_host_eol(
                host_id, db, models, lc_db=db
            )

    def get_fleet_eol(self) -> Dict[str, Any]:
        """Fleet-wide EOL rollup (supported / approaching / eol / unknown)."""
        engine = self._get_module()
        with self._get_db_session() as db:
            return engine._lifecycle_service.get_fleet_eol(db, models, lc_db=db)

    def list_releases(
        self,
        os_name: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """List the shared OS-lifecycle registry with optional filters."""
        engine = self._get_module()
        with self._get_db_session() as db:
            return engine._lifecycle_service.list_releases(
                db, models, os_name=os_name, limit=limit, offset=offset
            )

    def refresh_eol(self, products: Optional[List[str]] = None) -> Dict[str, Any]:
        """Refresh the lifecycle registry from endoflife.date."""
        engine = self._get_module()
        with self._get_db_session() as db:
            return engine._lifecycle_service.refresh_eol(db, models, products=products)

    def create_upgrade_job(
        self,
        host_id: str,
        to_version: Optional[str] = None,
        method: Optional[str] = None,
        scheduled_at=None,
    ) -> Dict[str, Any]:
        """Create a release-upgrade job (method inference + pre-checks).

        Dispatch to the agent is the caller's responsibility (the OSS action
        enqueues the command through the store-and-forward queue).
        """
        engine = self._get_module()
        with self._get_db_session() as db:
            return engine._lifecycle_service.create_upgrade_job(
                host_id,
                db,
                models,
                lc_db=db,
                to_version=to_version,
                method=method,
                scheduled_at=scheduled_at,
            )

    def get_upgrade_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """One release-upgrade job by id."""
        engine = self._get_module()
        with self._get_db_session() as db:
            return engine._lifecycle_service.get_upgrade_job(job_id, db, models)

    def list_upgrade_jobs(self, host_id: str) -> Dict[str, Any]:
        """Release-upgrade jobs for a host."""
        engine = self._get_module()
        with self._get_db_session() as db:
            return engine._lifecycle_service.list_upgrade_jobs(host_id, db, models)


# Global lifecycle service instance.
lifecycle_service = LifecycleService()
