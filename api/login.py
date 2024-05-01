"""
This module provides the necessary function to support login to the SysManage
server.
"""
from fastapi import HTTPException, APIRouter
from pydantic import BaseModel

router = APIRouter()

class UserLogin(BaseModel):
    """
    This class represents the payload to the /login POST request.
    """
    userid: str
    password: str

@router.post("/login")
async def login(login_data: UserLogin):
    """
    This function provides login ability to the SysManage server.
    """
    if login_data.userid == 'user':
        if login_data.password == 'password':
            return { "message": "success", "result": "true" }

    raise HTTPException(status_code=401, detail="Bad userid or password")
