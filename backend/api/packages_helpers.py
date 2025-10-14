"""
Helper functions for package management API.
Synchronous database operations to be run in thread pools.
"""

from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql.functions import count

from backend.i18n import _
from backend.persistence import db as db_module
from backend.persistence.models import AvailablePackage


def get_packages_summary_sync() -> List[dict]:
    """
    Synchronous helper function to retrieve package summary.
    This runs in a thread pool to avoid blocking the event loop.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )

    with session_local() as session:
        try:
            # Query to get package counts grouped by OS, version, and package manager
            results = (
                session.query(
                    AvailablePackage.os_name,
                    AvailablePackage.os_version,
                    AvailablePackage.package_manager,
                    count(AvailablePackage.id).label("package_count"),
                )
                .group_by(
                    AvailablePackage.os_name,
                    AvailablePackage.os_version,
                    AvailablePackage.package_manager,
                )
                .all()
            )

            # Organize results by OS/version
            os_summary = {}
            for result in results:
                os_key = f"{result.os_name}:{result.os_version}"

                if os_key not in os_summary:
                    os_summary[os_key] = {
                        "os_name": result.os_name,
                        "os_version": result.os_version,
                        "package_managers": [],
                        "total_packages": 0,
                    }

                manager_summary = {
                    "package_manager": result.package_manager,
                    "package_count": result.package_count,
                }

                os_summary[os_key]["package_managers"].append(manager_summary)
                os_summary[os_key]["total_packages"] += result.package_count

            # Convert to list format
            summary_list = list(os_summary.values())

            # Sort by OS name, then version
            summary_list.sort(key=lambda x: (x["os_name"], x["os_version"]))

            return summary_list

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=_("Failed to retrieve package summary: %s") % str(e),
            ) from e


def search_packages_count_sync(
    query: str,
    os_name: Optional[str],
    os_version: Optional[str],
    package_manager: Optional[str],
) -> dict:
    """
    Synchronous helper function to count packages matching search criteria.
    This runs in a thread pool to avoid blocking the event loop.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )

    with session_local() as session:
        try:
            db_query = session.query(AvailablePackage).filter(
                AvailablePackage.package_name.ilike(f"%{query}%")
            )

            if os_name:
                db_query = db_query.filter(AvailablePackage.os_name == os_name)

            if os_version:
                db_query = db_query.filter(AvailablePackage.os_version == os_version)

            if package_manager:
                db_query = db_query.filter(
                    AvailablePackage.package_manager == package_manager
                )

            total_count = db_query.count()
            return {"total_count": total_count}

        except Exception as e:
            raise HTTPException(
                status_code=500, detail=_("Failed to count packages: %s") % str(e)
            ) from e


def search_packages_sync(
    query: str,
    os_name: Optional[str],
    os_version: Optional[str],
    package_manager: Optional[str],
    limit: int,
    offset: int,
) -> List[dict]:
    """
    Synchronous helper function to search for packages.
    This runs in a thread pool to avoid blocking the event loop.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )

    with session_local() as session:
        try:
            db_query = session.query(AvailablePackage).filter(
                AvailablePackage.package_name.ilike(f"%{query}%")
            )

            if os_name:
                db_query = db_query.filter(AvailablePackage.os_name == os_name)

            if os_version:
                db_query = db_query.filter(AvailablePackage.os_version == os_version)

            if package_manager:
                db_query = db_query.filter(
                    AvailablePackage.package_manager == package_manager
                )

            # Apply pagination
            packages = (
                db_query.order_by(
                    AvailablePackage.package_name, AvailablePackage.package_manager
                )
                .offset(offset)
                .limit(limit)
                .all()
            )

            return [
                {
                    "name": pkg.package_name,
                    "version": pkg.package_version,
                    "description": pkg.package_description,
                    "package_manager": pkg.package_manager,
                }
                for pkg in packages
            ]

        except Exception as e:
            raise HTTPException(
                status_code=500, detail=_("Failed to search packages: %s") % str(e)
            ) from e
