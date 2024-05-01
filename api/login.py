from fastapi import FastAPI, HTTPException, APIRouter
from pydantic import BaseModel

router = APIRouter()

class UserLogin(BaseModel):
    userid: str
    password: str

@router.post("/login")
async def login(login_data: UserLogin):
    if login_data.userid == 'user':
        if login_data.password == 'password':
            return { "message": "success", "result": "true" }

    raise HTTPException(status_code=401, detail="Bad userid or password")
