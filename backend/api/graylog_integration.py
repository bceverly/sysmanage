"""
Graylog integration API endpoints for managing Graylog server connections.
"""

import logging
from datetime import datetime
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from backend.api.host_utils import validate_host_approval_status
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import db, models
from backend.security.roles import SecurityRoles
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.services.vault_service import VaultError, VaultService

router = APIRouter()
logger = logging.getLogger(__name__)


class GraylogIntegrationRequest(BaseModel):
    """Request model for Graylog integration settings."""

    enabled: bool
    use_managed_server: bool
    host_id: Optional[str] = None
    manual_url: Optional[str] = None
    api_token: Optional[str] = None


class GraylogServerInfo(BaseModel):
    """Model for Graylog server information."""

    id: str
    fqdn: str
    role: str = "Log Aggregation Server"
    package_name: str = "graylog-server"
    package_version: Optional[str] = None
    is_active: bool = False


class GraylogHealthStatus(BaseModel):
    """Model for Graylog health check status."""

    healthy: bool
    version: Optional[str] = None
    cluster_id: Optional[str] = None
    node_id: Optional[str] = None
    error: Optional[str] = None
    has_gelf_tcp: Optional[bool] = None
    gelf_tcp_port: Optional[int] = None
    has_syslog_tcp: Optional[bool] = None
    syslog_tcp_port: Optional[int] = None
    has_syslog_udp: Optional[bool] = None
    syslog_udp_port: Optional[int] = None
    has_windows_sidecar: Optional[bool] = None
    windows_sidecar_port: Optional[int] = None


@router.get("/graylog-servers", dependencies=[Depends(JWTBearer())])
async def get_graylog_servers():
    """
    Get list of hosts that have the Graylog server role.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find all hosts with Graylog role
        graylog_hosts = (
            session.query(models.Host)
            .join(models.HostRole)
            .filter(
                models.HostRole.role == "Log Aggregation Server",
                models.HostRole.package_name == "graylog-server",
                models.Host.active == True,
                models.Host.approval_status == "approved",
            )
            .all()
        )

        servers = []
        for host in graylog_hosts:
            # Get the Graylog role details
            graylog_role = (
                session.query(models.HostRole)
                .filter(
                    models.HostRole.host_id == host.id,
                    models.HostRole.role == "Log Aggregation Server",
                    models.HostRole.package_name == "graylog-server",
                )
                .first()
            )

            servers.append(
                GraylogServerInfo(
                    id=str(host.id),
                    fqdn=host.fqdn,
                    package_version=(
                        graylog_role.package_version if graylog_role else None
                    ),
                    is_active=graylog_role.is_active if graylog_role else False,
                )
            )

        return {"graylog_servers": servers}


@router.get("/settings", dependencies=[Depends(JWTBearer())])
async def get_graylog_integration_settings():
    """
    Get current Graylog integration settings.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        from sqlalchemy.orm import joinedload

        settings = (
            session.query(models.GraylogIntegrationSettings)
            .options(joinedload(models.GraylogIntegrationSettings.host))
            .first()
        )

        if not settings:
            # Return default settings if none exist
            return {
                "enabled": False,
                "use_managed_server": True,
                "host_id": None,
                "manual_url": None,
                "api_token": None,
            }

        return settings.to_dict()


@router.post("/settings", dependencies=[Depends(JWTBearer())])
async def update_graylog_integration_settings(
    request: GraylogIntegrationRequest,
    req: Request,
    current_user=Depends(get_current_user),
):
    """
    Update Graylog integration settings.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Check if user has permission to enable Graylog integration
        auth_user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not auth_user:
            raise HTTPException(status_code=401, detail=_("User not found"))
        if auth_user._role_cache is None:
            auth_user.load_role_cache(session)
        if not auth_user.has_role(SecurityRoles.ENABLE_GRAYLOG_INTEGRATION):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: ENABLE_GRAYLOG_INTEGRATION role required"),
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

            # Verify host has Graylog role
            graylog_role = (
                session.query(models.HostRole)
                .filter(
                    models.HostRole.host_id == request.host_id,
                    models.HostRole.role == "Log Aggregation Server",
                    models.HostRole.package_name == "graylog-server",
                )
                .first()
            )

            if not graylog_role:
                raise HTTPException(
                    status_code=400,
                    detail=_("Selected host does not have Graylog server role"),
                )

        # Get or create settings
        settings = session.query(models.GraylogIntegrationSettings).first()

        if not settings:
            settings = models.GraylogIntegrationSettings()
            session.add(settings)

        # Handle API token storage in vault
        vault_token = None
        # Only update API token if it's provided and not the masked placeholder
        if (
            request.api_token
            and request.api_token.strip()
            and request.api_token != "***"  # nosec B105 - placeholder not password
        ):
            try:
                vault_service = VaultService()

                # Store API token in vault (trimmed to remove any leading/trailing whitespace)
                vault_result = vault_service.store_secret(
                    secret_name="Graylog API Token",  # nosec B106 - name not password
                    secret_data=request.api_token.strip(),
                    secret_type="API Token",  # nosec B106 - type label not password
                    secret_subtype="graylog",
                )

                vault_token = vault_result["vault_token"]

                # Create database entry for the secret (will show up in secrets screen)
                secret_entry = models.Secret(
                    name="Graylog API Token",  # nosec B106 - name not password
                    secret_type="API Token",  # nosec B106 - type label not password
                    secret_subtype="graylog",
                    vault_token=vault_token,
                    vault_path=vault_result["vault_path"],
                    created_by=getattr(req.state, "user", {}).get("username", "system"),
                    updated_by=getattr(req.state, "user", {}).get("username", "system"),
                )

                # Remove any existing Graylog API token secret
                existing_secret = (
                    session.query(models.Secret)
                    .filter(
                        models.Secret.name == "Graylog API Token",
                        models.Secret.secret_type
                        == "API Token",  # nosec B105 - type label not password
                    )
                    .first()
                )

                if existing_secret:
                    session.delete(existing_secret)

                session.add(secret_entry)

            except VaultError as e:
                logger.error("Failed to store Graylog API token in vault: %s", e)
                raise HTTPException(
                    status_code=500, detail=_("Failed to securely store API token")
                ) from e

        # Update settings
        settings.enabled = request.enabled
        settings.use_managed_server = request.use_managed_server
        settings.host_id = request.host_id if request.use_managed_server else None
        settings.manual_url = (
            request.manual_url if not request.use_managed_server else None
        )
        # Only update vault token if a new API token was provided
        if vault_token:
            settings.api_token_vault_token = vault_token

        session.commit()
        session.refresh(settings)

        # Log audit entry for Graylog integration settings update
        AuditService.log_update(
            db=session,
            entity_type=EntityType.SETTING,
            entity_name="Graylog Integration Settings",
            user_id=auth_user.id,
            username=current_user,
            entity_id=str(settings.id),
            details={
                "enabled": settings.enabled,
                "use_managed_server": settings.use_managed_server,
                "host_id": str(settings.host_id) if settings.host_id else None,
                "manual_url": settings.manual_url,
                "has_api_token": bool(settings.api_token_vault_token),
            },
        )

        return {
            "result": True,
            "message": _("Graylog integration settings updated successfully"),
        }


@router.get("/health", dependencies=[Depends(JWTBearer())])
async def check_graylog_health():
    """
    Check the health status of the configured Graylog server.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        from sqlalchemy.orm import joinedload

        settings = (
            session.query(models.GraylogIntegrationSettings)
            .options(joinedload(models.GraylogIntegrationSettings.host))
            .first()
        )

        if not settings:
            raise HTTPException(
                status_code=400, detail=_("Graylog integration has not been configured")
            )

        if not settings.enabled:
            raise HTTPException(
                status_code=400, detail=_("Graylog integration is not enabled")
            )

        try:
            graylog_url = settings.graylog_url
        except Exception as e:
            logger.error("Error accessing graylog_url property: %s", e)
            raise HTTPException(
                status_code=500, detail=_("Error retrieving Graylog URL: %s") % str(e)
            ) from e

        if not graylog_url:
            raise HTTPException(
                status_code=400, detail=_("Graylog URL is not configured")
            )

        # Extract hostname from graylog_url for port detection
        import socket
        from urllib.parse import urlparse

        parsed_url = urlparse(graylog_url)
        graylog_host = parsed_url.hostname or graylog_url.split("://")[-1].split(":")[0]

        try:
            # Retrieve API token from vault if available
            api_token = None
            if settings.api_token_vault_token:
                try:
                    vault_service = VaultService()
                    # Find the secret in database to get vault path
                    secret = (
                        session.query(models.Secret)
                        .filter(
                            models.Secret.name == "Graylog API Token",
                            models.Secret.secret_type
                            == "API Token",  # nosec B105 - type label not password
                            models.Secret.vault_token == settings.api_token_vault_token,
                        )
                        .first()
                    )

                    if secret:
                        secret_data = vault_service.retrieve_secret(
                            secret.vault_path, settings.api_token_vault_token
                        )
                        # Try different possible paths for the API token
                        if secret_data:
                            # Path 1: data.data.content
                            api_token = (
                                secret_data.get("data", {})
                                .get("data", {})
                                .get("content")
                            )
                            if not api_token:
                                # Path 2: data.content
                                api_token = secret_data.get("data", {}).get("content")
                            if not api_token:
                                # Path 3: content (direct)
                                api_token = secret_data.get("content")
                            # Trim whitespace from retrieved token
                            if api_token:
                                api_token = api_token.strip()
                except VaultError as e:
                    logger.warning(
                        "Could not retrieve Graylog API token from vault: %s", e
                    )
                except Exception as e:  # pylint: disable=broad-except
                    logger.warning("Unexpected error retrieving API token: %s", e)

            # Try to get Graylog health endpoint
            async with httpx.AsyncClient(timeout=10.0) as client:
                # First try the unauthenticated load balancer status endpoint
                logger.info(
                    "Checking Graylog health at URL: %s/api/system/lbstatus",
                    graylog_url,
                )
                lb_response = await client.get(f"{graylog_url}/api/system/lbstatus")

                if lb_response.status_code == 200:
                    # LB status endpoint returns "ALIVE" or similar
                    lb_status = lb_response.text.strip()

                    # If we have an API token, also get detailed system info
                    version = None
                    cluster_id = None
                    node_id = None

                    if api_token:
                        logger.info(
                            "Fetching detailed system info from %s/api/system",
                            graylog_url,
                        )
                        headers = {
                            "Authorization": f"Bearer {api_token}",
                            "X-Requested-By": "sysmanage",
                        }
                        system_response = await client.get(
                            f"{graylog_url}/api/system", headers=headers
                        )
                        if system_response.status_code == 200:
                            system_data = system_response.json()
                            version = system_data.get("version")
                            cluster_id = system_data.get("cluster_id")
                            node_id = system_data.get("node_id")

                    # Detect available Graylog input ports
                    # Common Graylog input ports to check
                    # GELF TCP: typically 12201
                    # Syslog TCP: typically 514 or 1514
                    # Syslog UDP: typically 514 or 1514
                    # Windows Sidecar (Beats): typically 5044

                    has_gelf_tcp = False
                    gelf_tcp_port = None
                    has_syslog_tcp = False
                    syslog_tcp_port = None
                    has_syslog_udp = False
                    syslog_udp_port = None
                    has_windows_sidecar = False
                    windows_sidecar_port = None

                    # Check GELF TCP (12201)
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(1)
                        result = sock.connect_ex((graylog_host, 12201))
                        sock.close()
                        if result == 0:
                            has_gelf_tcp = True
                            gelf_tcp_port = 12201
                    except Exception:  # nosec B110 - Port scan failure expected
                        pass

                    # Check Syslog TCP (1514, then 514)
                    for port in [1514, 514]:
                        try:
                            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            sock.settimeout(1)
                            result = sock.connect_ex((graylog_host, port))
                            sock.close()
                            if result == 0:
                                has_syslog_tcp = True
                                syslog_tcp_port = port
                                break
                        except Exception:  # nosec B110 - Port scan failure expected
                            pass

                    # Check Syslog UDP (1514, then 514)
                    for port in [1514, 514]:
                        try:
                            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                            sock.settimeout(1)
                            # For UDP, we can't really "connect", so we just check if we can send
                            # We'll assume it's available if the previous TCP check succeeded
                            if has_syslog_tcp and syslog_tcp_port == port:
                                has_syslog_udp = True
                                syslog_udp_port = port
                            sock.close()
                            if has_syslog_udp:
                                break
                        except Exception:  # nosec B110 - Port scan failure expected
                            pass

                    # Check Windows Sidecar / Beats (5044)
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(1)
                        result = sock.connect_ex((graylog_host, 5044))
                        sock.close()
                        if result == 0:
                            has_windows_sidecar = True
                            windows_sidecar_port = 5044
                    except Exception:  # nosec B110 - Port scan failure expected
                        pass

                    # Update the database with detected ports
                    settings.has_gelf_tcp = has_gelf_tcp
                    settings.gelf_tcp_port = gelf_tcp_port
                    settings.has_syslog_tcp = has_syslog_tcp
                    settings.syslog_tcp_port = syslog_tcp_port
                    settings.has_syslog_udp = has_syslog_udp
                    settings.syslog_udp_port = syslog_udp_port
                    settings.has_windows_sidecar = has_windows_sidecar
                    settings.windows_sidecar_port = windows_sidecar_port
                    settings.inputs_last_checked = datetime.utcnow()
                    session.commit()

                    return GraylogHealthStatus(
                        healthy=(lb_status.upper() == "ALIVE"),
                        version=version,
                        cluster_id=cluster_id,
                        node_id=node_id,
                        has_gelf_tcp=has_gelf_tcp,
                        gelf_tcp_port=gelf_tcp_port,
                        has_syslog_tcp=has_syslog_tcp,
                        syslog_tcp_port=syslog_tcp_port,
                        has_syslog_udp=has_syslog_udp,
                        syslog_udp_port=syslog_udp_port,
                        has_windows_sidecar=has_windows_sidecar,
                        windows_sidecar_port=windows_sidecar_port,
                    )
                else:
                    return GraylogHealthStatus(
                        healthy=False,
                        error=f"HTTP {lb_response.status_code}: {lb_response.text}",
                    )

        except (
            httpx.ReadTimeout,
            httpx.ConnectTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
        ) as e:
            logger.error("Graylog health check timeout for %s: %s", graylog_url, e)
            return GraylogHealthStatus(
                healthy=False,
                error=_("Connection timeout - Graylog server may be unreachable"),
            )
        except httpx.ConnectError as e:
            logger.error(
                "Graylog health check connection failed for %s: %s", graylog_url, e
            )
            return GraylogHealthStatus(
                healthy=False,
                error=_(
                    "Connection failed - Graylog server may be down or unreachable"
                ),
            )
        except Exception as e:  # pylint: disable=broad-except
            logger.error("Error checking Graylog health: %s", e)
            return GraylogHealthStatus(
                healthy=False, error=_("Unexpected error checking Graylog health")
            )


class GraylogAttachmentRequest(BaseModel):
    """Request model for attaching a host to Graylog."""

    mechanism: str  # syslog_tcp, syslog_udp, gelf_tcp, windows_sidecar
    graylog_server: str  # IP or hostname of Graylog server
    port: int  # Port for the selected mechanism


# attach_host_to_graylog endpoint moved to backend/api/host.py to avoid routing conflicts
