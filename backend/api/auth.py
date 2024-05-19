"""
This module provides the necessary function to support login to the SysManage
server.
"""
from datetime import datetime, timezone
from fastapi import HTTPException, APIRouter, Depends
from pydantic import BaseModel, EmailStr
from pyargon2 import hash as argon2_hash
from sqlalchemy.orm import sessionmaker

from backend.auth.auth_handler import sign_jwt
from backend.auth.auth_bearer import JWTBearer
from backend.persistence import db, models
from backend.config import config

router = APIRouter()

class UserLogin(BaseModel):
    """
    This class represents the JSON payload to the /login POST request.
    """
    userid: EmailStr
    password: str

@router.post("/login")
async def login(login_data: UserLogin):
    """
    This function provides login ability to the SysManage server.
    """
    # Get the /etc/sysmanage.yaml configuration
    the_config = config.get_config()

    db.get_db()
    if login_data.userid == the_config["security"]["admin_userid"]:
        if login_data.password == the_config["security"]["admin_password"]:
            return sign_jwt(login_data.userid)
        
        raise HTTPException(status_code=401, detail="Bad userid or password")

    # Get the SQLAlchemy session
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())

    # Check if this is a valid user
    with session_local() as session:
        # Hash the password passed in
        hashed_value = argon2_hash(login_data.password, the_config["security"]["password_salt"])

        # Query the database
        records = session.query(models.User).all()
        for record in records:
            if record.userid == login_data.userid and record.hashed_password == hashed_value:
                # Update the last access datetime
                session.query(models.User).filter(models.User.id == record.id).update({models.User.last_access: datetime.now(timezone.utc)})
                session.commit()

                # Return success
                return sign_jwt(login_data.userid)

    # If we got here, then there was no match
    raise HTTPException(status_code=401, detail="Bad userid or password")

@router.post("/validate", dependencies=[Depends(JWTBearer())])
async def validate():
    """
    This function provides login ability to the SysManage server.  Since it
    is set up as depending on JWTBearer(), it will automatically do what we
    want it to - validate the token passed in (JWTBearer() will return an
    error if the token is invalid for some reason) and then will add the
    response header with a refreshed token.
    """
    return {
        "result": True
        }
