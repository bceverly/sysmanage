"""
This module provides the main setup and entry point for the SysManage server
process.  It reads and processes the sysmanage.yaml configuration file, sets
up the CORS configuration in the middleware, includes all of the various
routers for the system and then launches the application.
"""

import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
)
from backend.config import config
from backend.monitoring.heartbeat_monitor import heartbeat_monitor_service
from backend.discovery.discovery_service import discovery_beacon
from backend.security.certificate_manager import certificate_manager

# Parse the /etc/sysmanage.yaml file
app_config = config.get_config()


@asynccontextmanager
async def lifespan(_fastapi_app: FastAPI):
    """
    Application lifespan manager to handle startup and shutdown events.
    """
    # Startup: Ensure server certificates are generated
    certificate_manager.ensure_server_certificate()

    # Startup: Start the heartbeat monitor service
    heartbeat_task = asyncio.create_task(heartbeat_monitor_service())

    # Startup: Start the discovery beacon service
    await discovery_beacon.start_beacon_service()

    yield

    # Shutdown: Stop the discovery beacon service
    await discovery_beacon.stop_beacon_service()

    # Shutdown: Cancel the heartbeat monitor service
    heartbeat_task.cancel()
    try:
        await heartbeat_task
    except asyncio.CancelledError:
        pass


# Start the application
app = FastAPI(lifespan=lifespan)

# Set up the CORS configuration - purely config-driven
origins = []

# Add primary origins from config
webui_host = app_config["webui"]["host"]
webui_port = app_config["webui"]["port"]
api_host = app_config["api"]["host"]
api_port = app_config["api"]["port"]

# Add HTTP origins - but skip 0.0.0.0 as it's not a valid browser origin
if webui_host != "0.0.0.0":
    origins.append(f"http://{webui_host}:{webui_port}")
if api_host != "0.0.0.0":
    origins.append(f"http://{api_host}:{api_port}")

# Add HTTPS origins if certificates are configured - but skip 0.0.0.0
if app_config["api"].get("certFile") and app_config["api"].get("keyFile"):
    if webui_host != "0.0.0.0":
        origins.append(f"https://{webui_host}:{webui_port}")
    if api_host != "0.0.0.0":
        origins.append(f"https://{api_host}:{api_port}")

# Add localhost alternatives if host is 0.0.0.0 (listening on all interfaces)
if webui_host == "0.0.0.0":
    origins.extend([f"http://localhost:{webui_port}", f"http://127.0.0.1:{webui_port}"])
    if app_config["api"].get("certFile"):
        origins.extend(
            [f"https://localhost:{webui_port}", f"https://127.0.0.1:{webui_port}"]
        )

if api_host == "0.0.0.0":
    origins.extend([f"http://localhost:{api_port}", f"http://127.0.0.1:{api_port}"])
    if app_config["api"].get("certFile"):
        origins.extend(
            [f"https://localhost:{api_port}", f"https://127.0.0.1:{api_port}"]
        )

# Add any additional origins specified in config
if "cors" in app_config and "additional_origins" in app_config["cors"]:
    origins.extend(app_config["cors"]["additional_origins"])

# Debug logging
print(f"CORS Debug - WebUI: {webui_host}:{webui_port}")
print(f"CORS Debug - API: {api_host}:{api_port}")
print(f"CORS Debug - Generated origins: {origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Authorization"],
)

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
        **ssl_config,
    )
