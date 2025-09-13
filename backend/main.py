"""
This module provides the main setup and entry point for the SysManage server
process.  It reads and processes the sysmanage.yaml configuration file, sets
up the CORS configuration in the middleware, includes all of the various
routers for the system and then launches the application.
"""

import asyncio
import logging
import os
import socket
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api import (
    agent,
    auth,
    certificates,
    diagnostics,
    fleet,
    host,
    user,
    config_management,
    profile,
    updates,
    scripts,
    security,
    tag,
    queue,
)
from backend.config import config
from backend.monitoring.heartbeat_monitor import heartbeat_monitor_service
from backend.discovery.discovery_service import discovery_beacon
from backend.security.certificate_manager import certificate_manager
from backend.websocket.message_processor import message_processor
from backend.utils.logging_formatter import UTCTimestampFormatter
from backend.utils.verbosity_logger import get_logger

# Initialize logger for startup debugging
startup_logger = get_logger("backend.startup")


# Function to get dynamic hostnames and IPs for CORS
def get_cors_origins(web_ui_port, backend_api_port):
    """Generate CORS origins including dynamic hostname discovery."""
    cors_origins = []

    # Always add localhost for development
    cors_origins.extend(
        [
            f"http://localhost:{web_ui_port}",
            f"http://localhost:{backend_api_port}",
            f"http://127.0.0.1:{web_ui_port}",
            f"http://127.0.0.1:{backend_api_port}",
        ]
    )

    # Get system hostname and add variations
    try:
        hostname = socket.gethostname()
        if hostname and hostname != "localhost":
            cors_origins.extend(
                [
                    f"http://{hostname}:{web_ui_port}",
                    f"http://{hostname}:{backend_api_port}",
                ]
            )

        # Add FQDN if different from hostname
        try:
            fqdn = socket.getfqdn()
            if fqdn and fqdn != hostname and fqdn != "localhost":
                cors_origins.extend(
                    [
                        f"http://{fqdn}:{web_ui_port}",
                        f"http://{fqdn}:{backend_api_port}",
                    ]
                )
        except Exception:  # nosec B110
            pass

        # Add common domain variations
        hostname_variations = [
            f"{hostname}.local",
            f"{hostname}.lan",
            f"{hostname}.theeverlys.lan",
            f"{hostname}.theeverlys.com",
        ]

        for variation in hostname_variations:
            origins.extend(
                [f"http://{variation}:{webui_port}", f"http://{variation}:{api_port}"]
            )
    except Exception:  # nosec B110
        pass

    # Get network interface IPs
    try:
        hostname_for_ip = socket.gethostname()
        host_ip = socket.gethostbyname(hostname_for_ip)
        if host_ip and host_ip != "127.0.0.1":
            cors_origins.extend(
                [
                    f"http://{host_ip}:{web_ui_port}",
                    f"http://{host_ip}:{backend_api_port}",
                ]
            )
    except Exception:  # nosec B110
        pass

    return list(set(cors_origins))  # Remove duplicates


# Parse the /etc/sysmanage.yaml file
app_config = config.get_config()

# Configure logging with UTC timestamp formatter
# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

# Configure logging with error handling for file permissions
handlers = [logging.StreamHandler()]

try:
    # Try to add file handler, but fallback gracefully if permission denied
    file_handler = logging.FileHandler("logs/backend.log", mode="a", encoding="utf-8")
    handlers.append(file_handler)
except PermissionError:
    print(
        "WARNING: Cannot write to logs/backend.log due to permissions. Logging to console only.",
        file=sys.stderr,
    )

logging.basicConfig(
    level=logging.INFO,
    handlers=handlers,
)

# Apply UTC timestamp formatter to all handlers
utc_formatter = UTCTimestampFormatter("%(levelname)s: %(name)s: %(message)s")
for handler in logging.root.handlers:
    handler.setFormatter(utc_formatter)


@asynccontextmanager
async def lifespan(_fastapi_app: FastAPI):
    """
    Application lifespan manager to handle startup and shutdown events.
    """
    startup_logger.debug("lifespan function called")
    startup_logger.debug("About to call logging.info")
    startup_logger.info("lifespan function called")
    startup_logger.debug("logging.info called successfully")
    try:
        # Startup: Ensure server certificates are generated
        print(
            "About to call certificate_manager.ensure_server_certificate()",
            flush=True,
        )
        logging.info("About to call certificate_manager.ensure_server_certificate()")
        certificate_manager.ensure_server_certificate()
        startup_logger.debug("certificate_manager completed")
        startup_logger.info("certificate_manager.ensure_server_certificate() completed")

        # Startup: Start the heartbeat monitor service
        startup_logger.debug("About to start heartbeat monitor service")
        heartbeat_task = asyncio.create_task(heartbeat_monitor_service())
        startup_logger.debug("heartbeat monitor service started")

        # Startup: Start the message processor service
        startup_logger.debug("About to start message processor")
        startup_logger.info("About to start message processor")

        # Get current event loop and schedule the message processor to start
        loop = asyncio.get_event_loop()
        startup_logger.debug("Got event loop")

        # Create the task and schedule it with the event loop
        message_processor_task = loop.create_task(message_processor.start())
        startup_logger.debug("Created message processor task with loop.create_task")
        logging.info("Message processor task created: %s", message_processor_task)

        # Allow the event loop to process the task creation
        startup_logger.debug("Yielding control to event loop")
        await asyncio.sleep(0.1)  # Short yield to let task start

        # Force the event loop to process any pending tasks
        await asyncio.sleep(0.5)  # Give it time to actually start
        startup_logger.debug("Finished yielding to event loop")

        # Check task status
        if message_processor_task.done():
            print(
                "WARNING - Message processor task completed during startup",
                flush=True,
            )
            startup_logger.warning("Message processor task completed during startup")
            try:
                result = await message_processor_task
                print(f"Task result: {result}")
            except Exception as task_e:
                startup_logger.error(
                    "Message processor startup failed: %s", task_e, exc_info=True
                )
                print(f"Task exception: {task_e}")
                raise
        else:
            startup_logger.debug("Message processor task scheduled and running")
            startup_logger.info("Message processor task scheduled and running")

        # Startup: Start the discovery beacon service
        startup_logger.debug("About to start discovery beacon service")
        await discovery_beacon.start_beacon_service()
        startup_logger.debug("discovery beacon service started")

        startup_logger.info("All startup tasks completed successfully")
        startup_logger.debug("All startup tasks completed successfully")

        yield
    except Exception as e:
        startup_logger.error("Exception in lifespan startup: %s", e, exc_info=True)
        raise

    # Shutdown: Stop the discovery beacon service
    await discovery_beacon.stop_beacon_service()

    # Shutdown: Stop the message processor service
    message_processor.stop()
    message_processor_task.cancel()
    try:
        await message_processor_task
    except asyncio.CancelledError:
        pass

    # Shutdown: Cancel the heartbeat monitor service
    heartbeat_task.cancel()
    try:
        await heartbeat_task
    except asyncio.CancelledError:
        pass


# Start the application
app = FastAPI(lifespan=lifespan)

# Set up the CORS configuration - dynamically discover hostnames
webui_port = app_config["webui"]["port"]
api_port = app_config["api"]["port"]

# Get dynamic origins including hostname discovery
origins = get_cors_origins(webui_port, api_port)

# Add any additional origins specified in config
if "cors" in app_config and "additional_origins" in app_config["cors"]:
    origins.extend(app_config["cors"]["additional_origins"])

# Add HTTPS origins if certificates are configured
if app_config["api"].get("certFile") and app_config["api"].get("keyFile"):
    https_origins = []
    for origin in origins:
        https_origins.append(origin.replace("http://", "https://"))
    origins.extend(https_origins)

# Debug logging
print(f"CORS Debug - WebUI Port: {webui_port}")
print(f"CORS Debug - API Port: {api_port}")
print(
    f"CORS Debug - Generated origins: {origins[:10]}..."
)  # Show first 10 to avoid log spam
print(f"CORS Debug - Total origins count: {len(origins)}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Authorization"],
)


# Add exception handlers to ensure CORS headers are always present
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions and ensure CORS headers are included."""
    response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    # Add CORS headers manually for error responses
    request_origin = request.headers.get("origin")
    if request_origin and request_origin in origins:
        response.headers["Access-Control-Allow-Origin"] = request_origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Expose-Headers"] = "Authorization"

    return response


@app.exception_handler(500)
async def internal_server_error_handler(request: Request, exc: Exception):
    """Handle internal server errors and ensure CORS headers are included."""
    response = JSONResponse(
        status_code=500, content={"detail": "Internal server error"}
    )

    # Add CORS headers manually for error responses
    request_origin = request.headers.get("origin")
    if request_origin and request_origin in origins:
        response.headers["Access-Control-Allow-Origin"] = request_origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Expose-Headers"] = "Authorization"

    return response


# Import the dependencies
app.include_router(agent.router)
app.include_router(certificates.router)
app.include_router(host.router)
app.include_router(auth.router)
app.include_router(user.router)
app.include_router(fleet.router)
app.include_router(config_management.router)
app.include_router(profile.router, prefix="/api", tags=["profile"])
app.include_router(updates.router, prefix="/api/updates", tags=["updates"])
app.include_router(scripts.router, prefix="/api/scripts", tags=["scripts"])
app.include_router(diagnostics.router, tags=["diagnostics"])
app.include_router(security.router)
app.include_router(tag.router, prefix="/api", tags=["tags"])
app.include_router(queue.router, prefix="/api/queue", tags=["queue"])


@app.get("/")
async def root():
    """
    This function provides the HTTP response to calls to the root path of
    the service.
    """
    return {"message": "Hello World"}


@app.get("/api/health")
@app.head("/api/health")
async def health_check():
    """
    Health check endpoint for connection monitoring.
    """
    return {"status": "healthy"}


if __name__ == "__main__":
    # Check if SSL certificates are configured
    ssl_config = {}
    if app_config["api"].get("keyFile") and app_config["api"].get("certFile"):
        ssl_config = {
            "ssl_keyfile": app_config["api"]["keyFile"],
            "ssl_certfile": app_config["api"]["certFile"],
        }
        if app_config["api"].get("chainFile"):
            ssl_config["ssl_ca_certs"] = app_config["api"]["chainFile"]

    # Configure uvicorn logging to match our format
    log_config = uvicorn.config.LOGGING_CONFIG

    # Update both formatters to use our custom UTC timestamp format
    log_config["formatters"]["access"] = {
        "()": "backend.utils.logging_formatter.UTCTimestampFormatter",
        "fmt": "%(levelname)s: %(name)s: %(message)s",
    }
    log_config["formatters"]["default"] = {
        "()": "backend.utils.logging_formatter.UTCTimestampFormatter",
        "fmt": "%(levelname)s: %(name)s: %(message)s",
    }

    uvicorn.run(
        app,
        host=app_config["api"]["host"],
        port=app_config["api"]["port"],
        ws_ping_interval=60.0,  # Increased from default 20s to match agent config
        ws_ping_timeout=60.0,  # Increased to handle large message transmissions
        log_config=log_config,
        **ssl_config,
    )
