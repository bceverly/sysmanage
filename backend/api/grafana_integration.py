"""
Grafana integration API endpoints for managing Grafana server connections.
"""

import logging
import os
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from backend.api.host_utils import validate_host_approval_status
from backend.api.error_constants import (
    GRAFANA_API_KEY,
    GRAFANA_API_KEY_LABEL,
    MONITORING_SERVER,
)
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import db, models
from backend.security.roles import SecurityRoles
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.services.vault_service import VaultError, VaultService

router = APIRouter()
logger = logging.getLogger(__name__)


async def configure_prometheus_datasource(  # NOSONAR
    settings: "models.GrafanaIntegrationSettings", session
) -> None:
    """
    Configure Prometheus data source in Grafana.

    Args:
        settings: Grafana integration settings with API key
        session: Database session
    """
    grafana_url = settings.grafana_url
    if not grafana_url:
        logger.warning("Cannot configure Prometheus: Grafana URL not available")
        return

    # Get Prometheus URL from environment
    # Use hostname instead of localhost so external Grafana can reach it
    import socket

    hostname = socket.getfqdn()
    prometheus_url = os.getenv("PROMETHEUS_URL", f"http://{hostname}:9091")  # NOSONAR

    # Retrieve API key from vault
    if not settings.api_key_vault_token:
        logger.warning("Cannot configure Prometheus: No API key available")
        return

    try:
        vault_service = VaultService()
        secret = (
            session.query(models.Secret)
            .filter(
                models.Secret.name == GRAFANA_API_KEY,
                models.Secret.secret_type
                == GRAFANA_API_KEY_LABEL,  # nosec B105  # type label, not a password
                models.Secret.vault_token == settings.api_key_vault_token,
            )
            .first()
        )

        if not secret:
            logger.warning("Cannot configure Prometheus: API key secret not found")
            return

        secret_data = vault_service.retrieve_secret(
            secret.vault_path, settings.api_key_vault_token
        )
        # Don't log secret data structure to avoid potential information disclosure

        # Try different possible paths for the API key
        api_key = None
        if secret_data:
            # Path 1: data.data.content
            api_key = secret_data.get("data", {}).get("data", {}).get("content")
            if not api_key:
                # Path 2: data.content
                api_key = secret_data.get("data", {}).get("content")
            if not api_key:
                # Path 3: content (direct)
                api_key = secret_data.get("content")
            # Trim whitespace from retrieved key
            if api_key:
                api_key = api_key.strip()
                logger.debug(
                    "API key found: True, length=%s",
                    len(api_key),
                )
            else:
                logger.debug("API key found: False")

        if not api_key:
            logger.warning(
                "Cannot configure Prometheus: Failed to retrieve API key from secret_data"
            )
            return

    except Exception as e:  # pylint: disable=broad-except
        logger.error("Failed to retrieve API key from vault: %s", e)
        return

    # Configure Prometheus data source in Grafana
    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Check if data source already exists
        datasources_response = await client.get(
            f"{grafana_url}/api/datasources", headers=headers
        )

        existing_datasource = None
        if datasources_response.status_code == 200:
            datasources = datasources_response.json()
            for ds in datasources:
                if (
                    ds.get("type") == "prometheus"
                    and ds.get("name") == "SysManage Prometheus"
                ):
                    existing_datasource = ds
                    break

        datasource_config = {
            "name": "SysManage Prometheus",
            "type": "prometheus",
            "url": prometheus_url,
            "access": "proxy",
            "basicAuth": False,
            "isDefault": True,
            "jsonData": {
                "httpMethod": "POST",
                "timeInterval": "15s",
            },
        }

        if existing_datasource:
            # Update existing data source
            datasource_config["id"] = existing_datasource["id"]
            datasource_config["uid"] = existing_datasource["uid"]
            response = await client.put(
                f"{grafana_url}/api/datasources/{existing_datasource['id']}",
                headers=headers,
                json=datasource_config,
            )
            if response.status_code == 200:
                logger.info("Updated Prometheus data source in Grafana")
            else:
                logger.warning(
                    "Failed to update Prometheus data source: %s - %s",
                    response.status_code,
                    response.text,
                )
        else:
            # Create new data source
            response = await client.post(
                f"{grafana_url}/api/datasources",
                headers=headers,
                json=datasource_config,
            )
            if response.status_code in (200, 201):
                logger.info("Created Prometheus data source in Grafana")
            else:
                logger.warning(
                    "Failed to create Prometheus data source: %s - %s",
                    response.status_code,
                    response.text,
                )


class GrafanaIntegrationRequest(BaseModel):
    """Request model for Grafana integration settings."""

    enabled: bool
    use_managed_server: bool
    host_id: Optional[str] = None
    manual_url: Optional[str] = None
    api_key: Optional[str] = None


class GrafanaServerInfo(BaseModel):
    """Model for Grafana server information."""

    id: str
    fqdn: str
    role: str = MONITORING_SERVER
    package_name: str = "grafana"
    package_version: Optional[str] = None
    is_active: bool = False


class GrafanaHealthStatus(BaseModel):
    """Model for Grafana health check status."""

    healthy: bool
    version: Optional[str] = None
    build_info: Optional[dict] = None
    error: Optional[str] = None


@router.get("/grafana-servers", dependencies=[Depends(JWTBearer())])
async def get_grafana_servers():
    """
    Get list of hosts that have the Grafana server role.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find all hosts with Grafana role
        grafana_hosts = (
            session.query(models.Host)
            .join(models.HostRole)
            .filter(
                models.HostRole.role == MONITORING_SERVER,
                models.HostRole.package_name == "grafana",
                models.Host.active == True,
                models.Host.approval_status == "approved",
            )
            .all()
        )

        servers = []
        for host in grafana_hosts:
            # Get the Grafana role details
            grafana_role = (
                session.query(models.HostRole)
                .filter(
                    models.HostRole.host_id == host.id,
                    models.HostRole.role == MONITORING_SERVER,
                    models.HostRole.package_name == "grafana",
                )
                .first()
            )

            servers.append(
                GrafanaServerInfo(
                    id=str(host.id),
                    fqdn=host.fqdn,
                    package_version=(
                        grafana_role.package_version if grafana_role else None
                    ),
                    is_active=grafana_role.is_active if grafana_role else False,
                )
            )

        return {"grafana_servers": servers}


@router.get("/settings", dependencies=[Depends(JWTBearer())])
async def get_grafana_integration_settings():  # NOSONAR
    """
    Get current Grafana integration settings.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        from sqlalchemy.orm import joinedload

        settings = (
            session.query(models.GrafanaIntegrationSettings)
            .options(joinedload(models.GrafanaIntegrationSettings.host))
            .first()
        )

        if not settings:
            # Return default settings if none exist
            return {
                "enabled": False,
                "use_managed_server": True,
                "host_id": None,
                "manual_url": None,
                "api_key": None,
            }

        return settings.to_dict()


@router.post("/settings", dependencies=[Depends(JWTBearer())])
async def update_grafana_integration_settings(  # NOSONAR
    request: GrafanaIntegrationRequest,
    req: Request,
    current_user=Depends(get_current_user),
):
    """
    Update Grafana integration settings.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Check if user has permission to enable Grafana integration
        auth_user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not auth_user:
            raise HTTPException(status_code=401, detail=_("User not found"))
        if auth_user._role_cache is None:
            auth_user.load_role_cache(session)
        if not auth_user.has_role(SecurityRoles.ENABLE_GRAFANA_INTEGRATION):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: ENABLE_GRAFANA_INTEGRATION role required"),
            )
        # Validate host if using managed server
        if request.use_managed_server and request.host_id:
            host = (
                session.query(models.Host)
                .filter(models.Host.id == request.host_id)
                .first()
            )
            if not host:
                raise HTTPException(status_code=404, detail=_("Host not found"))
            validate_host_approval_status(host)

            # Verify host has Grafana role
            grafana_role = (
                session.query(models.HostRole)
                .filter(
                    models.HostRole.host_id == request.host_id,
                    models.HostRole.role == MONITORING_SERVER,
                    models.HostRole.package_name == "grafana",
                )
                .first()
            )

            if not grafana_role:
                raise HTTPException(
                    status_code=400,
                    detail=_("Selected host does not have Grafana server role"),
                )

        # Get or create settings
        settings = session.query(models.GrafanaIntegrationSettings).first()

        if not settings:
            settings = models.GrafanaIntegrationSettings()
            session.add(settings)

        # Handle API key storage in vault
        vault_token = None
        # Only update API key if it's provided and not the masked placeholder
        if request.api_key and request.api_key.strip() and request.api_key != "***":
            try:
                vault_service = VaultService()

                # Store API key in vault (trimmed to remove any leading/trailing whitespace)
                vault_result = vault_service.store_secret(
                    secret_name=GRAFANA_API_KEY,  # nosec B106  # name, not a password
                    secret_data=request.api_key.strip(),
                    secret_type=GRAFANA_API_KEY_LABEL,  # nosec B106  # type label, not a password
                    secret_subtype="grafana",
                )

                vault_token = vault_result["vault_token"]

                # Create database entry for the secret (will show up in secrets screen)
                secret_entry = models.Secret(
                    name=GRAFANA_API_KEY,  # nosec B106  # name, not a password
                    secret_type=GRAFANA_API_KEY_LABEL,  # nosec B106  # type label, not a password
                    secret_subtype="grafana",
                    vault_token=vault_token,
                    vault_path=vault_result["vault_path"],
                    created_by=getattr(req.state, "user", {}).get("username", "system"),
                    updated_by=getattr(req.state, "user", {}).get("username", "system"),
                )

                # Remove any existing Grafana API key secret
                existing_secret = (
                    session.query(models.Secret)
                    .filter(
                        models.Secret.name == GRAFANA_API_KEY,
                        models.Secret.secret_type
                        == GRAFANA_API_KEY_LABEL,  # nosec B105  # type label, not a password
                    )
                    .first()
                )

                if existing_secret:
                    session.delete(existing_secret)

                session.add(secret_entry)

            except VaultError as e:
                logger.error("Failed to store Grafana API key in vault: %s", e)
                raise HTTPException(
                    status_code=500, detail=_("Failed to securely store API key")
                ) from e

        # Update settings
        settings.enabled = request.enabled
        settings.use_managed_server = request.use_managed_server
        settings.host_id = request.host_id if request.use_managed_server else None
        settings.manual_url = (
            request.manual_url if not request.use_managed_server else None
        )
        # Only update vault token if a new API key was provided
        if vault_token:
            settings.api_key_vault_token = vault_token

        session.commit()
        session.refresh(settings)

        # If enabled and we have an API key, configure Prometheus data source
        logger.info(
            "Checking if should configure Prometheus: enabled=%s, has_api_key=%s",
            settings.enabled,
            bool(settings.api_key_vault_token),
        )
        if settings.enabled and settings.api_key_vault_token:
            logger.info("Configuring Prometheus data source in Grafana...")
            try:
                await configure_prometheus_datasource(settings, session)
                logger.info("Prometheus data source configuration completed")
            except Exception as e:  # pylint: disable=broad-except
                logger.warning("Failed to configure Prometheus data source: %s", e)
                # Don't fail the settings update if data source config fails

        # Log audit entry for Grafana integration settings update
        AuditService.log_update(
            db=session,
            entity_type=EntityType.SETTING,
            entity_name="Grafana Integration Settings",
            user_id=auth_user.id,
            username=current_user,
            entity_id=str(settings.id),
            details={
                "enabled": settings.enabled,
                "use_managed_server": settings.use_managed_server,
                "host_id": str(settings.host_id) if settings.host_id else None,
                "manual_url": settings.manual_url,
                "has_api_key": bool(settings.api_key_vault_token),
            },
        )

        return {
            "result": True,
            "message": _("Grafana integration settings updated successfully"),
        }


@router.get("/health", dependencies=[Depends(JWTBearer())])
async def check_grafana_health():  # NOSONAR
    """
    Check the health status of the configured Grafana server.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        from sqlalchemy.orm import joinedload

        settings = (
            session.query(models.GrafanaIntegrationSettings)
            .options(joinedload(models.GrafanaIntegrationSettings.host))
            .first()
        )

        if not settings:
            raise HTTPException(
                status_code=400, detail=_("Grafana integration has not been configured")
            )

        if not settings.enabled:
            raise HTTPException(
                status_code=400, detail=_("Grafana integration is not enabled")
            )

        try:
            grafana_url = settings.grafana_url
        except Exception as e:
            logger.error("Error accessing grafana_url property: %s", e)
            raise HTTPException(
                status_code=500, detail=_("Error retrieving Grafana URL: %s") % str(e)
            ) from e

        if not grafana_url:
            raise HTTPException(
                status_code=400, detail=_("Grafana URL is not configured")
            )

        try:
            # Retrieve API key from vault if available
            api_key = None
            if settings.api_key_vault_token:
                try:
                    vault_service = VaultService()
                    # Find the secret in database to get vault path
                    secret = (
                        session.query(models.Secret)
                        .filter(
                            models.Secret.name == GRAFANA_API_KEY,
                            models.Secret.secret_type
                            == GRAFANA_API_KEY_LABEL,  # nosec B105  # type label, not a password
                            models.Secret.vault_token == settings.api_key_vault_token,
                        )
                        .first()
                    )

                    if secret:
                        secret_data = vault_service.retrieve_secret(
                            secret.vault_path, settings.api_key_vault_token
                        )
                        if secret_data.get("data", {}).get("data", {}).get("content"):
                            api_key = secret_data["data"]["data"]["content"]
                except VaultError as e:
                    logger.warning(
                        "Could not retrieve Grafana API key from vault: %s", e
                    )
                except Exception as e:  # pylint: disable=broad-except
                    logger.warning("Unexpected error retrieving API key: %s", e)

            # Try to get Grafana health endpoint
            logger.info("Checking Grafana health at URL: %s/api/health", grafana_url)
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Try health API first
                health_response = await client.get(f"{grafana_url}/api/health")

                if health_response.status_code == 200:
                    _health_data = health_response.json()  # NOSONAR

                    # Try to get version info
                    version_info = None
                    try:
                        # If we have an API key, try to get more detailed info
                        headers = {}
                        if api_key:
                            headers["Authorization"] = f"Bearer {api_key}"

                        # Try to get build info for version details
                        build_response = await client.get(
                            f"{grafana_url}/api/frontend/settings", headers=headers
                        )
                        if build_response.status_code == 200:
                            build_data = build_response.json()
                            version_info = build_data.get("buildInfo", {})
                    except Exception as e:  # pylint: disable=broad-except
                        logger.debug("Could not fetch Grafana version info: %s", e)

                    return GrafanaHealthStatus(
                        healthy=True,
                        version=version_info.get("version") if version_info else None,
                        build_info=version_info,
                    )
                else:
                    return GrafanaHealthStatus(
                        healthy=False,
                        error=f"HTTP {health_response.status_code}: {health_response.text}",
                    )

        except (
            httpx.ReadTimeout,
            httpx.ConnectTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
        ) as e:
            logger.error("Grafana health check timeout for %s: %s", grafana_url, e)
            return GrafanaHealthStatus(
                healthy=False,
                error=_("Connection timeout - Grafana server may be unreachable"),
            )
        except httpx.ConnectError as e:
            logger.error(
                "Grafana health check connection failed for %s: %s", grafana_url, e
            )
            return GrafanaHealthStatus(
                healthy=False,
                error=_(
                    "Connection failed - Grafana server may be down or unreachable"
                ),
            )
        except Exception as e:  # pylint: disable=broad-except
            logger.error("Error checking Grafana health: %s", e)
            return GrafanaHealthStatus(
                healthy=False, error=_("Unexpected error checking Grafana health")
            )
