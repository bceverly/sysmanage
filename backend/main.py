"""
This module provides the main setup and entry point for the SysManage server
process.  It reads and processes the sysmanage.yaml configuration file, sets
up the CORS configuration in the middleware, includes all of the various
routers for the system and then launches the application.
"""

import os
import socket
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import config
from backend.startup.cors_config import get_cors_origins
from backend.startup.exception_handlers import register_exception_handlers
from backend.startup.lifecycle import lifespan
from backend.startup.logging_config import configure_logging
from backend.startup.route_registration import register_app_routes, register_routes
from backend.telemetry.otel_config import setup_telemetry
from backend.utils.verbosity_logger import get_logger

# Initialize logger for startup debugging
startup_logger = get_logger("backend.startup")
startup_logger.info("=== STARTUP DEBUG LOGGING INITIALIZED ===")
startup_logger.info("Logger type: %s", type(startup_logger).__name__)
startup_logger.info("Python version: %s", sys.version)
startup_logger.info("Current working directory: %s", os.getcwd())
startup_logger.info("Environment variables count: %d", len(os.environ))

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
configure_logging()

# Start the application
startup_logger.info("=== CREATING FASTAPI APPLICATION ===")
startup_logger.info("Creating FastAPI app with lifespan manager")
app = FastAPI(lifespan=lifespan)
startup_logger.info("FastAPI app created successfully")
startup_logger.info(
    "App info - Title: %s, Version: %s",
    getattr(app, "title", "Not set"),
    getattr(app, "version", "Not set"),
)

# Set up OpenTelemetry instrumentation
startup_logger.info("=== SETTING UP OPENTELEMETRY ===")
try:
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    prometheus_port = int(os.getenv("OTEL_PROMETHEUS_PORT", "9090"))
    setup_telemetry(
        app,
        service_name="sysmanage",
        service_version="1.0.0",
        otlp_endpoint=otlp_endpoint,
        prometheus_port=prometheus_port,
    )
    startup_logger.info("OpenTelemetry setup completed")
except Exception as e:
    startup_logger.warning(f"OpenTelemetry setup failed (non-fatal): {e}")
startup_logger.info("=== OPENTELEMETRY SETUP COMPLETE ===")

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
register_exception_handlers(app, origins)

# Register all API routes
register_routes(app)

# Register basic application routes
register_app_routes(app)


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
    ws_ping_interval = 60.0  # pylint: disable=invalid-name
    ws_ping_timeout = 60.0  # pylint: disable=invalid-name
    ws_max_size = 100 * 1024 * 1024  # 100MB max message size for software inventory

    startup_logger.info("=== UVICORN CONFIGURATION ===")
    startup_logger.info("Host: %s", host)
    startup_logger.info("Port: %s", port)
    startup_logger.info("WebSocket ping interval: %s seconds", ws_ping_interval)
    startup_logger.info("WebSocket ping timeout: %s seconds", ws_ping_timeout)
    startup_logger.info(
        "WebSocket max message size: %s MB", ws_max_size / (1024 * 1024)
    )
    startup_logger.info("SSL enabled: %s", bool(ssl_config))
    startup_logger.info("Log level: INFO")

    # Test network binding before starting
    startup_logger.info("=== NETWORK BINDING TEST ===")
    try:
        test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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
            ws_max_size=ws_max_size,  # Increased from default 16MB to handle large software inventories
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
