"""
This module provides the main setup and entry point for the SysManage server
process.  It reads and processes the sysmanage.yaml configuration file, sets
up the CORS configuration in the middleware, includes all of the various
routers for the system and then launches the application.
"""
import sys
import uvicorn
import yaml

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import login

# Read/validate the configuration file
try:
    with open('sysmanage.yaml', 'r', encoding="utf-8") as file:
        config = yaml.safe_load(file)
        if not 'hostName' in config.keys():
            config['hostName'] = "localhost"
        if not 'apiPort' in config.keys():
            config['apiPort'] = 8000
        if not 'webPort' in config.keys():
            config['webPort'] = 8080
except yaml.YAMLError as exc:
    if hasattr(exc, 'problem_mark'):
        mark = exc.problem_mark
        print (f"Error reading sysmanage.yaml on line {mark.line+1} in column {mark.column+1}")
        sys.exit(1)

# Start the application
app = FastAPI()

# Set up the CORS configuration
origins = [
    "http://"+config['hostName'],
    "http://"+config['hostName']+":"+str(config['webPort']),
    "http://"+config['hostName']+":"+str(config['apiPort']),
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

@app.get("/")
async def root():
    """
    This function provides the HTTP response to calls to the root path of
    the service.
    """
    return {"message": "Hello World"}

if __name__ == "__main__":
    uvicorn.run(app, host=config['hostName'], port=config['apiPort'])
