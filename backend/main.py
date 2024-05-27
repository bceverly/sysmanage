"""
This module provides the main setup and entry point for the SysManage server
process.  It reads and processes the sysmanage.yaml configuration file, sets
up the CORS configuration in the middleware, includes all of the various
routers for the system and then launches the application.
"""
import uvicorn

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.api import auth, host, user
from backend.auth.auth_handler import sign_jwt
from backend.config import config

# Parse the /etc/sysmanage.yaml file
app_config = config.get_config()

# Start the application
app = FastAPI()

# Set up the CORS configuration
origins = [
    "https://"+app_config['webui']['host']+":"+str(app_config['webui']['port']),
    "https://"+app_config['api']['host']+":"+str(app_config['api']['port']),
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
app.include_router(host.router)
app.include_router(auth.router)
app.include_router(user.router)

@app.get("/")
async def root():
    """
    This function provides the HTTP response to calls to the root path of
    the service.
    """
    return {"message": "Hello World"}

if __name__ == "__main__":
    uvicorn.run(app, host=app_config['api']['host'],
                port=app_config['api']['port'],
                ssl_keyfile=app_config['api']['keyFile'],
                ssl_certfile=app_config['api']['certFile'],
                ssl_ca_certs=app_config['api']['chainFile'])
