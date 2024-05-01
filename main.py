import uvicorn
import yaml

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import login

# Read/validate the configuration file
try:
    with open('sysmanage.yaml', 'r') as file:
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
        print ("Error reading sysmanage.yaml on line (%s) in column (%s)" %
               (mark.line+1, mark.column+1))
        exit(1)

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
    return {"message": "Hello World"}

if __name__ == "__main__":
    uvicorn.run(app, host=config['hostName'], port=config['apiPort'])
