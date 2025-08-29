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

from backend.api import agent, auth, certificates, fleet, host, user, config_management
from backend.config import config
from backend.monitoring.heartbeat_monitor import heartbeat_monitor_service
from backend.discovery.discovery_service import discovery_beacon
from backend.security.certificate_manager import certificate_manager

# Parse the /etc/sysmanage.yaml file
app_config = config.get_config()


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
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

# Set up the CORS configuration
origins = [
    "http://" + app_config["webui"]["host"] + ":" + str(app_config["webui"]["port"]),
    "http://" + app_config["api"]["host"] + ":" + str(app_config["api"]["port"]),
    # Add localhost origins for development
    "http://localhost:3000",
    "http://localhost:8080",
    "https://localhost:3000",
    "http://localhost:7443",
    "https://localhost:7443",
    "https://sysmanage.org:7443",
]
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
        **ssl_config
    )
