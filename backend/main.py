"""
This module provides the main setup and entry point for the SysManage server
process.  It reads and processes the sysmanage.yaml configuration file, sets
up the CORS configuration in the middleware, includes all of the various
routers for the system and then launches the application.
"""

import asyncio
import logging
import socket
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
    fleet,
    host,
    user,
    config_management,
    profile,
    updates,
    scripts,
    security,
)
from backend.config import config
from backend.monitoring.heartbeat_monitor import heartbeat_monitor_service
from backend.discovery.discovery_service import discovery_beacon
from backend.security.certificate_manager import certificate_manager
from backend.websocket.message_processor import message_processor
from backend.utils.logging_formatter import UTCTimestampFormatter


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
        except Exception:
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
    except Exception:
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
    except Exception:
        pass

    return list(set(cors_origins))  # Remove duplicates


# Parse the /etc/sysmanage.yaml file
app_config = config.get_config()

# Configure logging with UTC timestamp formatter
logging.basicConfig(
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/backend.log", mode="a"),
    ],
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
    print("DEBUG: lifespan function called", flush=True)
    print("DEBUG: About to call logging.info", flush=True)
    logging.info("DEBUG: lifespan function called")
    print("DEBUG: logging.info called successfully", flush=True)
    try:
        # Startup: Ensure server certificates are generated
        print(
            "DEBUG: About to call certificate_manager.ensure_server_certificate()",
            flush=True,
        )
        logging.info(
            "DEBUG: About to call certificate_manager.ensure_server_certificate()"
        )
        certificate_manager.ensure_server_certificate()
        print("DEBUG: certificate_manager completed", flush=True)
        logging.info("DEBUG: certificate_manager.ensure_server_certificate() completed")

        # Startup: Start the heartbeat monitor service
        print("DEBUG: About to start heartbeat monitor service", flush=True)
        heartbeat_task = asyncio.create_task(heartbeat_monitor_service())
        print("DEBUG: heartbeat monitor service started", flush=True)

        # Startup: Start the message processor service
        print("DEBUG: About to start message processor", flush=True)
        logging.info("DEBUG: About to start message processor")

        # Get current event loop and schedule the message processor to start
        loop = asyncio.get_event_loop()
        print("DEBUG: Got event loop", flush=True)

        # Create the task and schedule it with the event loop
        message_processor_task = loop.create_task(message_processor.start())
        print("DEBUG: Created message processor task with loop.create_task", flush=True)
        logging.info(
            "DEBUG: Message processor task created: %s", message_processor_task
        )

        # Allow the event loop to process the task creation
        print("DEBUG: Yielding control to event loop", flush=True)
        await asyncio.sleep(0.1)  # Short yield to let task start

        # Force the event loop to process any pending tasks
        await asyncio.sleep(0.5)  # Give it time to actually start
        print("DEBUG: Finished yielding to event loop", flush=True)

        # Check task status
        if message_processor_task.done():
            print(
                "DEBUG: WARNING - Message processor task completed during startup",
                flush=True,
            )
            logging.warning("DEBUG: Message processor task completed during startup")
            try:
                result = await message_processor_task
                print(f"DEBUG: Task result: {result}", flush=True)
            except Exception as task_e:
                logging.error(
                    "DEBUG: Message processor startup failed: %s", task_e, exc_info=True
                )
                print(f"DEBUG: Task exception: {task_e}", flush=True)
                raise
        else:
            print("DEBUG: Message processor task scheduled and running", flush=True)
            logging.info("DEBUG: Message processor task scheduled and running")

        # Startup: Start the discovery beacon service
        print("DEBUG: About to start discovery beacon service", flush=True)
        await discovery_beacon.start_beacon_service()
        print("DEBUG: discovery beacon service started", flush=True)

        logging.info("DEBUG: All startup tasks completed successfully")
        print("DEBUG: All startup tasks completed successfully", flush=True)

        yield
    except Exception as e:
        logging.error("DEBUG: Exception in lifespan startup: %s", e, exc_info=True)
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
app.include_router(profile.router)
app.include_router(updates.router, prefix="/api/updates", tags=["updates"])
app.include_router(scripts.router, prefix="/api/scripts", tags=["scripts"])
app.include_router(security.router)


@app.get("/")
async def root():
    """
    This function provides the HTTP response to calls to the root path of
    the service.
    """
    return {"message": "Hello World"}


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

    uvicorn.run(
        app,
        host=app_config["api"]["host"],
        port=app_config["api"]["port"],
        ws_ping_interval=60.0,  # Increased from default 20s to match agent config
        ws_ping_timeout=60.0,  # Increased to handle large message transmissions
        **ssl_config,
    )
