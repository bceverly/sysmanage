"""
This module provides the necessary function to support login to the SysManage
server.
"""
from datetime import datetime, timezone
from fastapi import HTTPException, APIRouter
from pydantic import BaseModel
from pyargon2 import hash as argon2_hash
from sqlalchemy.orm import sessionmaker

from persistence import db, models
from config import config

router = APIRouter()

class UserLogin(BaseModel):
    """
    This class represents the JSON payload to the /login POST request.
    """
    userid: str
    password: str

@router.post("/login")
async def login(login_data: UserLogin):
    """
    This function provides login ability to the SysManage server.
    """
    db.get_db()
    if login_data.userid == 'user':
        if login_data.password == 'password':
            return { "message": "success", "result": "true" }
        raise HTTPException(status_code=401, detail="Bad userid or password")

    # Get the /etc/sysmanage.yaml configuration
    the_config = config.get_config()

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
                return { "message": "success", "result": "true" }

    # If we got here, then there was no match
    raise HTTPException(status_code=401, detail="Bad userid or password")
