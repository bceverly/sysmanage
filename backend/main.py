"""
This module provides the main setup and entry point for the SysManage server
process.  It reads and processes the sysmanage.yaml configuration file, sets
up the CORS configuration in the middleware, includes all of the various
routers for the system and then launches the application.
"""
import uvicorn

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import login, user
from backend.config import config

# Parse the /etc/sysmanage.yaml file
app_config = config.get_config()

# Start the application
app = FastAPI()

# Set up the CORS configuration
origins = [
    "http://"+app_config['network']['hostName'],
    "http://"+app_config['network']['hostName']+":"+str(app_config['network']['webPort']),
    "http://"+app_config['network']['hostName']+":"+str(app_config['network']['apiPort']),
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import the dependencies
app.include_router(login.router)
app.include_router(user.router)

@app.get("/")
async def root():
    """
    This function provides the HTTP response to calls to the root path of
    the service.
    """
    return {"message": "Hello World"}

if __name__ == "__main__":
    uvicorn.run(app, host=app_config['network']['hostName'], port=app_config['network']['apiPort'])