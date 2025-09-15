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
    config_management,
    diagnostics,
    email,
    fleet,
    host,
    password_reset,
    profile,
    queue,
    scripts,
    security,
    tag,
    updates,
    user,
)
from backend.config import config
from backend.discovery.discovery_service import discovery_beacon
from backend.monitoring.heartbeat_monitor import heartbeat_monitor_service
from backend.security.certificate_manager import certificate_manager
from backend.utils.logging_formatter import UTCTimestampFormatter
from backend.utils.verbosity_logger import get_logger
from backend.websocket.message_processor import message_processor

# Initialize logger for startup debugging
startup_logger = get_logger("backend.startup")
startup_logger.info("=== STARTUP DEBUG LOGGING INITIALIZED ===")
startup_logger.info("Logger type: %s", type(startup_logger).__name__)
startup_logger.info("Python version: %s", sys.version)
startup_logger.info("Current working directory: %s", os.getcwd())
startup_logger.info("Environment variables count: %d", len(os.environ))


# Function to get dynamic hostnames and IPs for CORS
def get_cors_origins(web_ui_port, backend_api_port):
    """Generate CORS origins including dynamic hostname discovery."""
    startup_logger.info("=== CORS ORIGINS GENERATION START ===")
    startup_logger.info("Web UI port: %s, Backend API port: %s", web_ui_port, backend_api_port)
    cors_origins = []

    # Always add localhost for development
    localhost_origins = [
        f"http://localhost:{web_ui_port}",
        f"http://localhost:{backend_api_port}",
        f"http://127.0.0.1:{web_ui_port}",
        f"http://127.0.0.1:{backend_api_port}",
    ]
    startup_logger.info("Adding localhost origins: %s", localhost_origins)
    cors_origins.extend(localhost_origins)

    # Get system hostname and add variations
    try:
        hostname = socket.gethostname()
        startup_logger.info("System hostname: %s", hostname)
        if hostname and hostname != "localhost":
            hostname_origins = [
                f"http://{hostname}:{web_ui_port}",
                f"http://{hostname}:{backend_api_port}",
            ]
            startup_logger.info("Adding hostname origins: %s", hostname_origins)
            cors_origins.extend(hostname_origins)

        # Add FQDN if different from hostname
        try:
            fqdn = socket.getfqdn()
            startup_logger.info("System FQDN: %s", fqdn)
            if fqdn and fqdn != hostname and fqdn != "localhost":
                fqdn_origins = [
                    f"http://{fqdn}:{web_ui_port}",
                    f"http://{fqdn}:{backend_api_port}",
                ]
                startup_logger.info("Adding FQDN origins: %s", fqdn_origins)
                cors_origins.extend(fqdn_origins)
        except Exception as e:  # nosec B110
            startup_logger.warning("Failed to get FQDN: %s", e)

        # Add common domain variations
        hostname_variations = [
            f"{hostname}.local",
            f"{hostname}.lan",
            f"{hostname}.theeverlys.lan",
            f"{hostname}.theeverlys.com",
        ]
        startup_logger.info("Testing hostname variations: %s", hostname_variations)

        for variation in hostname_variations:
            variation_origins = [f"http://{variation}:{web_ui_port}", f"http://{variation}:{backend_api_port}"]
            startup_logger.info("Adding variation origins for %s: %s", variation, variation_origins)
            cors_origins.extend(variation_origins)
    except Exception as e:  # nosec B110
        startup_logger.warning("Failed to process hostname variations: %s", e)

    # Get network interface IPs
    try:
        hostname_for_ip = socket.gethostname()
        startup_logger.info("Getting IP for hostname: %s", hostname_for_ip)
        host_ip = socket.gethostbyname(hostname_for_ip)
        startup_logger.info("Resolved host IP: %s", host_ip)
        if host_ip and host_ip != "127.0.0.1":
            ip_origins = [
                f"http://{host_ip}:{web_ui_port}",
                f"http://{host_ip}:{backend_api_port}",
            ]
            startup_logger.info("Adding IP origins: %s", ip_origins)
            cors_origins.extend(ip_origins)
    except Exception as e:  # nosec B110
        startup_logger.warning("Failed to get network interface IPs: %s", e)

    startup_logger.info("Total CORS origins before deduplication: %d", len(cors_origins))
    unique_origins = list(set(cors_origins))  # Remove duplicates
    startup_logger.info("Total CORS origins after deduplication: %d", len(unique_origins))
    startup_logger.info("Final CORS origins: %s", unique_origins)
    startup_logger.info("=== CORS ORIGINS GENERATION COMPLETE ===")
    return unique_origins


# Parse the /etc/sysmanage.yaml file
startup_logger.info("=== LOADING CONFIGURATION ===")
try:
    app_config = config.get_config()
    startup_logger.info("Configuration loaded successfully")
    startup_logger.info("Config keys: %s", list(app_config.keys()))
    startup_logger.info("WebUI config: %s", app_config.get("webui", "NOT FOUND"))
    startup_logger.info("API config: %s", app_config.get("api", "NOT FOUND"))
except Exception as e:
    startup_logger.error("Failed to load configuration: %s", e, exc_info=True)
    raise

# Configure logging with UTC timestamp formatter
startup_logger.info("=== CONFIGURING LOGGING ===")
# Ensure logs directory exists
logs_dir = "logs"
startup_logger.info("Creating logs directory: %s", logs_dir)
os.makedirs(logs_dir, exist_ok=True)
startup_logger.info("Logs directory exists: %s", os.path.exists(logs_dir))

# Configure logging with error handling for file permissions
handlers = [logging.StreamHandler()]
startup_logger.info("Added console handler")

try:
    # Try to add file handler, but fallback gracefully if permission denied
    log_file = "logs/backend.log"
    startup_logger.info("Attempting to create file handler for: %s", log_file)
    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    handlers.append(file_handler)
    startup_logger.info("File handler created successfully")
except PermissionError as e:
    startup_logger.error("Permission denied for log file: %s", e)
    print(
        "WARNING: Cannot write to logs/backend.log due to permissions. Logging to console only.",
        file=sys.stderr,
    )
except Exception as e:
    startup_logger.error("Failed to create file handler: %s", e)

startup_logger.info("Configuring basic logging with %d handlers", len(handlers))
logging.basicConfig(
    level=logging.INFO,
    handlers=handlers,
)

# Apply UTC timestamp formatter to all handlers
startup_logger.info("Applying UTC timestamp formatter to all handlers")
utc_formatter = UTCTimestampFormatter("%(levelname)s: %(name)s: %(message)s")
for i, handler in enumerate(logging.root.handlers):
    startup_logger.info("Setting formatter for handler %d: %s", i, type(handler).__name__)
    handler.setFormatter(utc_formatter)
startup_logger.info("Logging configuration complete")


@asynccontextmanager
async def lifespan(_fastapi_app: FastAPI):
    """
    Application lifespan manager to handle startup and shutdown events.
    """
    startup_logger.info("=== FASTAPI LIFESPAN STARTUP BEGIN ===")
    startup_logger.info("lifespan function called with app: %s", type(_fastapi_app).__name__)
    startup_logger.info("FastAPI app instance ID: %s", id(_fastapi_app))

    heartbeat_task = None
    message_processor_task = None

    try:
        # Startup: Ensure server certificates are generated
        startup_logger.info("=== CERTIFICATE GENERATION ===")
        print(
            "About to call certificate_manager.ensure_server_certificate()",
            flush=True,
        )
        startup_logger.info("About to call certificate_manager.ensure_server_certificate()")
        certificate_manager.ensure_server_certificate()
        startup_logger.info("certificate_manager.ensure_server_certificate() completed successfully")

        # Startup: Start the heartbeat monitor service
        startup_logger.info("=== HEARTBEAT MONITOR STARTUP ===")
        startup_logger.info("About to start heartbeat monitor service")
        heartbeat_task = asyncio.create_task(heartbeat_monitor_service())
        startup_logger.info("Heartbeat monitor task created: %s", heartbeat_task)
        startup_logger.info("Heartbeat monitor service started successfully")

        # Startup: Start the message processor service
        startup_logger.info("=== MESSAGE PROCESSOR STARTUP ===")
        startup_logger.info("About to start message processor")

        # Get current event loop and schedule the message processor to start
        loop = asyncio.get_event_loop()
        startup_logger.info("Got event loop: %s", loop)

        # Create the task and schedule it with the event loop
        message_processor_task = loop.create_task(message_processor.start())
        startup_logger.info("Created message processor task: %s", message_processor_task)
        startup_logger.info("Message processor task ID: %s", id(message_processor_task))

        # Allow the event loop to process the task creation
        startup_logger.info("Yielding control to event loop for 0.1 seconds")
        await asyncio.sleep(0.1)  # Short yield to let task start

        # Force the event loop to process any pending tasks
        startup_logger.info("Additional yield for 0.5 seconds to let task start")
        await asyncio.sleep(0.5)  # Give it time to actually start

        # Check task status
        startup_logger.info("Checking message processor task status")
        startup_logger.info("Task done: %s", message_processor_task.done())
        startup_logger.info("Task cancelled: %s", message_processor_task.cancelled())

        if message_processor_task.done():
            print(
                "WARNING - Message processor task completed during startup",
                flush=True,
            )
            startup_logger.warning("Message processor task completed during startup")
            try:
                result = await message_processor_task
                startup_logger.info("Task result: %s", result)
                print(f"Task result: {result}")
            except Exception as task_e:
                startup_logger.error(
                    "Message processor startup failed: %s", task_e, exc_info=True
                )
                print(f"Task exception: {task_e}")
                raise
        else:
            startup_logger.info("Message processor task scheduled and running successfully")

        # Startup: Start the discovery beacon service
        startup_logger.info("=== DISCOVERY BEACON STARTUP ===")
        startup_logger.info("About to start discovery beacon service")
        await discovery_beacon.start_beacon_service()
        startup_logger.info("Discovery beacon service started successfully")

        startup_logger.info("=== ALL STARTUP TASKS COMPLETED SUCCESSFULLY ===")
        startup_logger.info("Server is ready to accept requests")

        yield

        startup_logger.info("=== FASTAPI LIFESPAN SHUTDOWN BEGIN ===")

    except Exception as e:
        startup_logger.error("=== EXCEPTION IN LIFESPAN STARTUP ===")
        startup_logger.error("Exception in lifespan startup: %s", e, exc_info=True)
        startup_logger.error("Exception type: %s", type(e).__name__)
        startup_logger.error("Exception args: %s", e.args)
        raise

    # Shutdown: Stop the discovery beacon service
    startup_logger.info("Stopping discovery beacon service")
    try:
        await discovery_beacon.stop_beacon_service()
        startup_logger.info("Discovery beacon service stopped")
    except Exception as e:
        startup_logger.error("Error stopping discovery beacon: %s", e)

    # Shutdown: Stop the message processor service
    startup_logger.info("Stopping message processor service")
    try:
        message_processor.stop()
        if message_processor_task:
            message_processor_task.cancel()
            try:
                await message_processor_task
            except asyncio.CancelledError:
                startup_logger.info("Message processor task cancelled successfully")
        startup_logger.info("Message processor service stopped")
    except Exception as e:
        startup_logger.error("Error stopping message processor: %s", e)

    # Shutdown: Cancel the heartbeat monitor service
    startup_logger.info("Stopping heartbeat monitor service")
    try:
        if heartbeat_task:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                startup_logger.info("Heartbeat monitor task cancelled successfully")
        startup_logger.info("Heartbeat monitor service stopped")
    except Exception as e:
        startup_logger.error("Error stopping heartbeat monitor: %s", e)

    startup_logger.info("=== FASTAPI LIFESPAN SHUTDOWN COMPLETE ===")


# Start the application
startup_logger.info("=== CREATING FASTAPI APPLICATION ===")
startup_logger.info("Creating FastAPI app with lifespan manager")
app = FastAPI(lifespan=lifespan)
startup_logger.info("FastAPI app created successfully")
startup_logger.info("App info - Title: %s, Version: %s", getattr(app, 'title', 'Not set'), getattr(app, 'version', 'Not set'))

# Set up the CORS configuration - dynamically discover hostnames
startup_logger.info("=== SETTING UP CORS CONFIGURATION ===")
webui_port = app_config["webui"]["port"]
api_port = app_config["api"]["port"]
startup_logger.info("Ports from config - WebUI: %s, API: %s", webui_port, api_port)

# Get dynamic origins including hostname discovery
startup_logger.info("Calling get_cors_origins()")
origins = get_cors_origins(webui_port, api_port)
startup_logger.info("Initial origins count: %d", len(origins))

# Add any additional origins specified in config
if "cors" in app_config and "additional_origins" in app_config["cors"]:
    additional = app_config["cors"]["additional_origins"]
    startup_logger.info("Adding additional origins from config: %s", additional)
    origins.extend(additional)
else:
    startup_logger.info("No additional CORS origins in config")

# Add HTTPS origins if certificates are configured
cert_file = app_config["api"].get("certFile")
key_file = app_config["api"].get("keyFile")
startup_logger.info("SSL cert config - certFile: %s, keyFile: %s", cert_file, key_file)
if cert_file and key_file:
    https_origins = []
    for origin in origins:
        https_origins.append(origin.replace("http://", "https://"))
    startup_logger.info("Adding HTTPS origins: %d origins", len(https_origins))
    origins.extend(https_origins)
else:
    startup_logger.info("No SSL certificates configured, skipping HTTPS origins")

# Debug logging
startup_logger.info("=== FINAL CORS CONFIGURATION ===")
startup_logger.info("WebUI Port: %s", webui_port)
startup_logger.info("API Port: %s", api_port)
startup_logger.info("Total origins count: %d", len(origins))
startup_logger.info("First 10 origins: %s", origins[:10] if origins else [])
if len(origins) > 10:
    startup_logger.info("... and %d more origins", len(origins) - 10)

print(f"CORS Debug - WebUI Port: {webui_port}")
print(f"CORS Debug - API Port: {api_port}")
print(
    f"CORS Debug - Generated origins: {origins[:10]}..."
)  # Show first 10 to avoid log spam
print(f"CORS Debug - Total origins count: {len(origins)}")

startup_logger.info("Adding CORS middleware to FastAPI app")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Authorization"],
)
startup_logger.info("CORS middleware added successfully")


# Add exception handlers to ensure CORS headers are always present
startup_logger.info("=== REGISTERING EXCEPTION HANDLERS ===")

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions and ensure CORS headers are included."""
    startup_logger.warning("HTTP Exception occurred - Status: %s, Detail: %s, Path: %s",
                          exc.status_code, exc.detail, request.url.path)
    startup_logger.warning("Request method: %s, Headers: %s", request.method, dict(request.headers))

    response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    # Add CORS headers manually for error responses
    request_origin = request.headers.get("origin")
    startup_logger.debug("Request origin: %s", request_origin)
    if request_origin and request_origin in origins:
        startup_logger.debug("Adding CORS headers for origin: %s", request_origin)
        response.headers["Access-Control-Allow-Origin"] = request_origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Expose-Headers"] = "Authorization"
    else:
        startup_logger.warning("Origin %s not in allowed origins or not provided", request_origin)

    return response

startup_logger.info("HTTP exception handler registered")

@app.exception_handler(500)
async def internal_server_error_handler(request: Request, exc: Exception):
    """Handle internal server errors and ensure CORS headers are included."""
    startup_logger.error("Internal Server Error occurred - Path: %s, Exception: %s",
                        request.url.path, exc, exc_info=True)
    startup_logger.error("Request method: %s, Headers: %s", request.method, dict(request.headers))
    startup_logger.error("Exception type: %s", type(exc).__name__)
    startup_logger.error("Exception args: %s", exc.args)

    response = JSONResponse(
        status_code=500, content={"detail": "Internal server error"}
    )

    # Add CORS headers manually for error responses
    request_origin = request.headers.get("origin")
    startup_logger.debug("Request origin for 500 error: %s", request_origin)
    if request_origin and request_origin in origins:
        startup_logger.debug("Adding CORS headers for 500 error origin: %s", request_origin)
        response.headers["Access-Control-Allow-Origin"] = request_origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Expose-Headers"] = "Authorization"
    else:
        startup_logger.warning("Origin %s not in allowed origins for 500 error", request_origin)

    return response

startup_logger.info("Internal server error handler registered")

# Add a general exception handler for any unhandled exceptions
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle any unhandled exceptions."""
    startup_logger.error("Unhandled Exception occurred - Path: %s, Exception: %s",
                        request.url.path, exc, exc_info=True)
    startup_logger.error("Request method: %s, Headers: %s", request.method, dict(request.headers))
    startup_logger.error("Exception type: %s", type(exc).__name__)
    startup_logger.error("Exception args: %s", exc.args)

    response = JSONResponse(
        status_code=500, content={"detail": "An unexpected error occurred"}
    )

    # Add CORS headers manually for error responses
    request_origin = request.headers.get("origin")
    startup_logger.debug("Request origin for general exception: %s", request_origin)
    if request_origin and request_origin in origins:
        startup_logger.debug("Adding CORS headers for general exception origin: %s", request_origin)
        response.headers["Access-Control-Allow-Origin"] = request_origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Expose-Headers"] = "Authorization"

    return response

startup_logger.info("General exception handler registered")
startup_logger.info("=== EXCEPTION HANDLERS REGISTRATION COMPLETE ===")


# Import the dependencies

startup_logger.info("=== REGISTERING ROUTES ===")

# Unauthenticated routes (no /api prefix)
startup_logger.info("Registering unauthenticated routes:")

startup_logger.info("Adding auth router (no prefix)")
app.include_router(auth.router)  # /login, /refresh
startup_logger.info("Auth router added")

startup_logger.info("Adding agent router (no prefix)")
app.include_router(agent.router)  # /agent/auth, /api/agent/connect
startup_logger.info("Agent router added")

startup_logger.info("Adding host public router (no prefix)")
app.include_router(host.public_router)  # /host/register (no auth)
startup_logger.info("Host public router added")

startup_logger.info("Adding certificates public router (no prefix)")
app.include_router(
    certificates.public_router
)  # /certificates/server-fingerprint, /certificates/ca-certificate (no auth)
startup_logger.info("Certificates public router added")

startup_logger.info("Adding password reset router (no prefix)")
app.include_router(
    password_reset.router
)  # /forgot-password, /reset-password, /validate-reset-token (no auth)
startup_logger.info("Password reset router added")

# Secure routes (with /api prefix and JWT authentication required)
startup_logger.info("Registering authenticated routes with /api prefix:")

startup_logger.info("Adding user router with /api prefix")
app.include_router(user.router, prefix="/api", tags=["users"])
startup_logger.info("User router added")

startup_logger.info("Adding fleet router with /api prefix")
app.include_router(fleet.router, prefix="/api", tags=["fleet"])
startup_logger.info("Fleet router added")

startup_logger.info("Adding config management router with /api prefix")
app.include_router(config_management.router, prefix="/api", tags=["config"])
startup_logger.info("Config management router added")

startup_logger.info("Adding diagnostics router with /api prefix")
app.include_router(diagnostics.router, prefix="/api", tags=["diagnostics"])
startup_logger.info("Diagnostics router added")

startup_logger.info("Adding email router with /api prefix")
app.include_router(email.router, prefix="/api", tags=["email"])
startup_logger.info("Email router added")

startup_logger.info("Adding profile router with /api prefix")
app.include_router(profile.router, prefix="/api", tags=["profile"])
startup_logger.info("Profile router added")

startup_logger.info("Adding updates router with /api/updates prefix")
app.include_router(updates.router, prefix="/api/updates", tags=["updates"])
startup_logger.info("Updates router added")

startup_logger.info("Adding scripts router with /api/scripts prefix")
app.include_router(scripts.router, prefix="/api/scripts", tags=["scripts"])
startup_logger.info("Scripts router added")

startup_logger.info("Adding tag router with /api prefix")
app.include_router(tag.router, prefix="/api", tags=["tags"])
startup_logger.info("Tag router added")

startup_logger.info("Adding queue router with /api/queue prefix")
app.include_router(queue.router, prefix="/api/queue", tags=["queue"])
startup_logger.info("Queue router added")

startup_logger.info("Adding certificates auth router with /api prefix")
app.include_router(
    certificates.auth_router, prefix="/api", tags=["certificates"]
)  # /api/certificates/client/* (with auth)
startup_logger.info("Certificates auth router added")

startup_logger.info("Adding host auth router with /api prefix")
app.include_router(
    host.auth_router, prefix="/api", tags=["hosts"]
)  # /api/host/* (with auth)
startup_logger.info("Host auth router added")

startup_logger.info("Adding security router with /api prefix")
app.include_router(
    security.router, prefix="/api", tags=["security"]
)  # /api/security/* (with auth)
startup_logger.info("Security router added")

startup_logger.info("Adding password reset admin router with /api prefix")
app.include_router(
    password_reset.admin_router, prefix="/api", tags=["password_reset"]
)  # /api/admin/reset-user-password (with auth)
startup_logger.info("Password reset admin router added")

startup_logger.info("=== ALL ROUTES REGISTERED ===")

# Log all registered routes for debugging
startup_logger.info("=== ROUTE SUMMARY ===")
route_count = 0
for route in app.routes:
    if hasattr(route, 'path') and hasattr(route, 'methods'):
        startup_logger.info("Route: %s %s", list(route.methods), route.path)
        route_count += 1
    elif hasattr(route, 'path'):
        startup_logger.info("Route: %s", route.path)
        route_count += 1
startup_logger.info("Total routes registered: %d", route_count)


startup_logger.info("=== REGISTERING APPLICATION ROUTES ===")

@app.get("/")
async def root():
    """
    This function provides the HTTP response to calls to the root path of
    the service.
    """
    startup_logger.debug("Root endpoint called")
    return {"message": "Hello World"}

startup_logger.info("Root route (/) registered")

@app.get("/api/health")
@app.head("/api/health")
async def health_check():
    """
    Health check endpoint for connection monitoring.
    """
    startup_logger.debug("Health check endpoint called")
    return {"status": "healthy"}

startup_logger.info("Health check routes (/api/health) registered")
startup_logger.info("=== APPLICATION ROUTES REGISTRATION COMPLETE ===")


if __name__ == "__main__":
    startup_logger.info("=== STARTING UVICORN SERVER ===")
    startup_logger.info("Main module entry point reached")

    # Check if SSL certificates are configured
    startup_logger.info("Checking SSL certificate configuration")
    ssl_config = {}
    key_file = app_config["api"].get("keyFile")
    cert_file = app_config["api"].get("certFile")
    chain_file = app_config["api"].get("chainFile")

    startup_logger.info("SSL Config - keyFile: %s", key_file)
    startup_logger.info("SSL Config - certFile: %s", cert_file)
    startup_logger.info("SSL Config - chainFile: %s", chain_file)

    if key_file and cert_file:
        startup_logger.info("SSL certificates found, configuring HTTPS")
        ssl_config = {
            "ssl_keyfile": key_file,
            "ssl_certfile": cert_file,
        }
        if chain_file:
            ssl_config["ssl_ca_certs"] = chain_file
            startup_logger.info("SSL chain file added to config")
        startup_logger.info("SSL config: %s", ssl_config)
    else:
        startup_logger.info("No SSL certificates configured, using HTTP")

    # Configure uvicorn logging to match our format
    startup_logger.info("Configuring uvicorn logging")
    log_config = uvicorn.config.LOGGING_CONFIG
    startup_logger.info("Original uvicorn log config keys: %s", list(log_config.keys()))

    # Update both formatters to use our custom UTC timestamp format
    startup_logger.info("Setting custom formatters for uvicorn")
    log_config["formatters"]["access"] = {
        "()": "backend.utils.logging_formatter.UTCTimestampFormatter",
        "fmt": "%(levelname)s: %(name)s: %(message)s",
    }
    log_config["formatters"]["default"] = {
        "()": "backend.utils.logging_formatter.UTCTimestampFormatter",
        "fmt": "%(levelname)s: %(name)s: %(message)s",
    }
    startup_logger.info("Uvicorn logging configuration complete")

    # Prepare uvicorn configuration
    host = app_config["api"]["host"]
    port = app_config["api"]["port"]
    ws_ping_interval = 60.0
    ws_ping_timeout = 60.0

    startup_logger.info("=== UVICORN CONFIGURATION ===")
    startup_logger.info("Host: %s", host)
    startup_logger.info("Port: %s", port)
    startup_logger.info("WebSocket ping interval: %s seconds", ws_ping_interval)
    startup_logger.info("WebSocket ping timeout: %s seconds", ws_ping_timeout)
    startup_logger.info("SSL enabled: %s", bool(ssl_config))
    startup_logger.info("Log level: INFO")

    # Test network binding before starting
    startup_logger.info("=== NETWORK BINDING TEST ===")
    try:
        import socket as test_socket
        test_sock = test_socket.socket(test_socket.AF_INET, test_socket.SOCK_STREAM)
        test_sock.setsockopt(test_socket.SOL_SOCKET, test_socket.SO_REUSEADDR, 1)
        startup_logger.info("Testing bind to %s:%s", host, port)
        test_sock.bind((host, port))
        test_sock.close()
        startup_logger.info("Network binding test successful")
    except Exception as e:
        startup_logger.error("Network binding test FAILED: %s", e)
        startup_logger.error("This indicates the server will not be able to start!")
        startup_logger.error("Check if another process is using port %s", port)
        raise

    startup_logger.info("=== LAUNCHING UVICORN SERVER ===")
    startup_logger.info("About to call uvicorn.run()")

    try:
        uvicorn.run(
            app,
            host=host,
            port=port,
            ws_ping_interval=ws_ping_interval,  # Increased from default 20s to match agent config
            ws_ping_timeout=ws_ping_timeout,  # Increased to handle large message transmissions
            log_config=log_config,
            **ssl_config,
        )
    except Exception as e:
        startup_logger.error("UVICORN SERVER STARTUP FAILED: %s", e, exc_info=True)
        startup_logger.error("Server startup exception details:")
        startup_logger.error("Exception type: %s", type(e).__name__)
        startup_logger.error("Exception args: %s", e.args)
        raise

    startup_logger.info("Uvicorn.run() completed - this should not normally be reached")
    startup_logger.info("If you see this message, the server has shut down")
