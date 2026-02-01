"""
Health analysis service for Pro+ hosts.

Orchestrates health analysis using the health_engine module
and stores results in the database.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, sessionmaker

from backend.licensing.features import ModuleCode
from backend.licensing.license_service import license_service
from backend.licensing.module_loader import module_loader
from backend.persistence import db as db_module
from backend.persistence.models import (
    DiagnosticReport,
    Host,
    HostHealthAnalysis,
    NetworkInterface,
    StorageDevice,
)
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.health.health_service")


class HealthAnalysisError(Exception):
    """Exception raised when health analysis fails."""


class HealthService:
    """
    Service for performing AI-powered health analysis on hosts.
    """

    def _compute_grade(self, score: int) -> str:
        """Convert numeric score to letter grade."""
        if score >= 95:
            return "A+"
        elif score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"

    def _gather_host_metrics(self, db: Session, host_id: str) -> Dict[str, Any]:
        """
        Gather all available metrics for a host.

        Args:
            db: Database session
            host_id: The host ID

        Returns:
            Dictionary of metrics for analysis
        """
        host = db.query(Host).filter(Host.id == host_id).first()
        if not host:
            raise HealthAnalysisError(f"Host not found: {host_id}")

        metrics = {
            "host_id": str(host.id),
            "fqdn": host.fqdn,
            "platform": host.platform,
            "platform_release": host.platform_release,
            "platform_version": host.platform_version,
            "architecture": host.machine_architecture,
            "status": host.status,
            "active": host.active,
            "last_access": host.last_access.isoformat() if host.last_access else None,
        }

        # Hardware metrics
        metrics["hardware"] = {
            "cpu_vendor": host.cpu_vendor,
            "cpu_model": host.cpu_model,
            "cpu_cores": host.cpu_cores,
            "cpu_threads": host.cpu_threads,
            "cpu_frequency_mhz": host.cpu_frequency_mhz,
            "memory_total_mb": host.memory_total_mb,
        }

        # Storage devices
        storage_devices = (
            db.query(StorageDevice).filter(StorageDevice.host_id == host_id).all()
        )
        metrics["storage"] = [
            {
                "device_name": sd.device_name,
                "mount_point": sd.mount_point,
                "filesystem_type": sd.filesystem,
                "total_bytes": sd.total_size_bytes,
                "used_bytes": sd.used_size_bytes,
                "free_bytes": sd.available_size_bytes,
                "percent_used": (
                    round(sd.used_size_bytes / sd.total_size_bytes * 100, 1)
                    if sd.total_size_bytes and sd.used_size_bytes
                    else None
                ),
            }
            for sd in storage_devices
        ]

        # Network interfaces
        network_interfaces = (
            db.query(NetworkInterface).filter(NetworkInterface.host_id == host_id).all()
        )
        metrics["network"] = [
            {
                "interface_name": ni.interface_name,
                "ip_address": ni.ipv4_address,
                "mac_address": ni.mac_address,
                "is_up": ni.is_up,
            }
            for ni in network_interfaces
        ]

        # Get latest diagnostic report if available
        latest_diagnostic = (
            db.query(DiagnosticReport)
            .filter(DiagnosticReport.host_id == host_id)
            .order_by(DiagnosticReport.created_at.desc())
            .first()
        )
        if latest_diagnostic:
            try:
                diagnostic_data = (
                    json.loads(latest_diagnostic.report_data)
                    if isinstance(latest_diagnostic.report_data, str)
                    else latest_diagnostic.report_data
                )
                metrics["diagnostics"] = diagnostic_data
                metrics["diagnostics_timestamp"] = (
                    latest_diagnostic.created_at.isoformat()
                )
            except Exception as e:
                logger.warning("Failed to parse diagnostic data: %s", e)

        # Security status
        if hasattr(host, "antivirus_status") and host.antivirus_status:
            av = host.antivirus_status
            metrics["antivirus"] = {
                "installed": av.software_name is not None,
                "software_name": av.software_name,
                "version": av.version,
                "enabled": av.enabled,
            }

        if hasattr(host, "firewall_status") and host.firewall_status:
            fw = host.firewall_status
            metrics["firewall"] = {
                "firewall_name": fw.firewall_name,
                "enabled": fw.enabled,
            }

        # Reboot status
        metrics["reboot_required"] = host.reboot_required
        metrics["reboot_required_reason"] = host.reboot_required_reason

        return metrics

    async def analyze_host(self, host_id: str) -> Dict[str, Any]:
        """
        Perform health analysis on a host.

        Args:
            host_id: The host ID to analyze

        Returns:
            Dictionary with analysis results

        Raises:
            HealthAnalysisError: If analysis fails
        """
        # Check if health_engine module is available
        if not license_service.has_module(ModuleCode.HEALTH_ENGINE):
            raise HealthAnalysisError(
                "Health analysis requires Pro+ license with health_engine module"
            )

        health_engine = module_loader.get_module("health_engine")
        if health_engine is None:
            raise HealthAnalysisError("health_engine module is not loaded")

        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )

        with session_local() as db:
            # Gather metrics
            try:
                metrics = self._gather_host_metrics(db, host_id)
            except Exception as e:
                raise HealthAnalysisError(f"Failed to gather host metrics: {e}") from e

            # Run analysis through health_engine
            try:
                result = health_engine.analyze_health(metrics)
            except Exception as e:
                raise HealthAnalysisError(f"Health engine analysis failed: {e}") from e

            # Parse result
            score = result.get("score", 0)
            grade = result.get("grade") or self._compute_grade(score)
            issues = result.get("issues", [])
            recommendations = result.get("recommendations", [])
            analysis_version = result.get("version", "unknown")

            # Save to database
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            analysis = HostHealthAnalysis(
                host_id=host_id,
                analyzed_at=now,
                score=score,
                grade=grade,
                issues=issues,
                recommendations=recommendations,
                analysis_version=analysis_version,
                raw_metrics=metrics,
            )
            db.add(analysis)
            db.commit()
            db.refresh(analysis)

            logger.info(
                "Health analysis completed for host %s: score=%d, grade=%s",
                host_id,
                score,
                grade,
            )

            return {
                "id": str(analysis.id),
                "host_id": str(host_id),
                "analyzed_at": analysis.analyzed_at.isoformat(),
                "score": score,
                "grade": grade,
                "issues": issues,
                "recommendations": recommendations,
                "analysis_version": analysis_version,
            }

    async def get_latest_analysis(self, host_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent health analysis for a host.

        Args:
            host_id: The host ID

        Returns:
            Dictionary with analysis results, or None if no analysis exists
        """
        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )

        with session_local() as db:
            analysis = (
                db.query(HostHealthAnalysis)
                .filter(HostHealthAnalysis.host_id == host_id)
                .order_by(HostHealthAnalysis.analyzed_at.desc())
                .first()
            )

            if not analysis:
                return None

            return {
                "id": str(analysis.id),
                "host_id": str(analysis.host_id),
                "analyzed_at": analysis.analyzed_at.isoformat(),
                "score": analysis.score,
                "grade": analysis.grade,
                "issues": analysis.issues,
                "recommendations": analysis.recommendations,
                "analysis_version": analysis.analysis_version,
            }

    async def get_analysis_history(
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
        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )

        with session_local() as db:
            analyses = (
                db.query(HostHealthAnalysis)
                .filter(HostHealthAnalysis.host_id == host_id)
                .order_by(HostHealthAnalysis.analyzed_at.desc())
                .limit(limit)
                .all()
            )

            return [
                {
                    "id": str(a.id),
                    "host_id": str(a.host_id),
                    "analyzed_at": a.analyzed_at.isoformat(),
                    "score": a.score,
                    "grade": a.grade,
                    "issues": a.issues,
                    "recommendations": a.recommendations,
                    "analysis_version": a.analysis_version,
                }
                for a in analyses
            ]


# Global health service instance
health_service = HealthService()
