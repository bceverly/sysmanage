"""
This module provides the main setup and entry point for the SysManage server
process.  It reads and processes the sysmanage.yaml configuration file, sets
up the CORS configuration in the middleware, includes all of the various
routers for the system and then launches the application.
"""
import ssl
import uvicorn

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.api import login, user
from backend.auth.auth_handler import sign_jwt, reauth_decode_jwt
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
)

# Add middleware to refresh the JWT token in the response headers
@app.middleware("http")
async def add_token_header(request: Request, call_next):
    """
    This function retrieves/decodes the user_id from the request JWT token
    and adds an HTTP repsonse header that contains a refreshed token
    """
    response = await call_next(request)

    # Check that this is a content-type = application/json
    content_type = response.headers.get('Content-Type')
    if content_type != "application/json":
        return response

    # Do not "leak" a valid reauthorization token if we are in an
    # Error: Forbidden state
    if response.status_code == 403:
        return response

    # get the Bearer token from the request
    the_headers = request.headers
    if "Authorization" in the_headers:
        old_string = the_headers["Authorization"]
        the_elements = old_string.split()
        if len(the_elements) == 2:
            old_dict = reauth_decode_jwt(the_elements[1])
            if old_dict:
                if "user_id" in old_dict:
                    user_id = old_dict["user_id"]
                    new_token = sign_jwt(user_id)
                    response.headers["X_Reauthorization"] = new_token["X_Reauthorization"]

    return response

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
    uvicorn.run(app, host=app_config['api']['host'],
                port=app_config['api']['port'],
                ssl_keyfile=app_config['api']['keyFile'],
                ssl_certfile=app_config['api']['certFile'],
                ssl_ca_certs=app_config['api']['chainFile'])
