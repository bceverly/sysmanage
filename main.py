import uvicorn
import yaml

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Start the application
app = FastAPI()

# Read/validate the configuration file
try:
    with open('sysmanage.yaml', 'r') as file:
        config = yaml.safe_load(file)
        if not 'hostName' in config.keys():
            print("Missing hostName entry in sysmanage.yaml configuration file")
            exit(1)
        if not 'apiPort' in config.keys():
            print("Missing apiPort entry in sysmanage.yaml configuration file")
            exit(1)
        if not 'webPort' in config.keys():
            print("Missing webPort entry in sysmanage.yaml configuration file")
            exit(1)
except yaml.YAMLError as exc:
    if hasattr(exc, 'problem_mark'):
        mark = exc.problem_mark
        print ("Error reading sysmanage.yaml on line (%s) in column (%s)" % (mark.line+1, mark.column+1))

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

@app.get("/")
async def root():
    return {"message": "Hello World"}

class UserLogin(BaseModel):
    userid: str
    password: str

@app.post("/login")
async def login(login_data: UserLogin):
    if login_data.userid == 'user':
        if login_data.password == 'password':
            return { "message": "success", "result": "true" }

    raise HTTPException(status_code=401, detail="Bad userid or password")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)