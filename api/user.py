"""
This module contains the API implementation for the user object in the system.
"""
from datetime import datetime, timezone
from fastapi import HTTPException, APIRouter
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.orm import sessionmaker

from pyargon2 import hash as argon2_hash

from persistence import db, models
from config import config

router = APIRouter()

class User(BaseModel):
    """
    This class represents the JSON payload to the /user POST request.
    """
    userid: str
    password: str
    last_access: datetime

@router.delete("/user/{id}")
async def delete_user(id: int):
    """
    This function deletes a single user given a userid
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())

    with session_local() as session:
        session.execute(delete(models.User).where(models.User.id == id))
        session.commit()

    return { "message": "success", "result": "true" }

@router.get("/user/{id}")
async def get_user(id: int):
    """
    This function retrieves a single user by its id
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())

    with session_local() as session:
        result = session.execute(select(models.User).where(models.User.id == id))
        users = result.mappings().all()

        # Check for failure
        if len(users) != 1:
            raise HTTPException(status_code=404, detail="User not found")
        
    return { "message": "success", "result": users[0] }

@router.get("/user/by_userid/{userid}")
async def get_user_by_userid(userid: str):
    """
    This function retrieves a single user by userid
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())

    with session_local() as session:
        result = session.execute(select(models.User).where(models.User.userid == userid))
        users = result.mappings().all()
        return { "message": "success", "result": users }

    return { "message": "success", "result": "true" }

@router.get("/users")
async def get_all_users():
    """
    This function retrieves all users in the system
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())

    with session_local() as session:
        result = session.query(models.User).all()
        return { "message": "success", "result": result }

    return { "message": "success", "result": "true" }

@router.post("/user")
async def add_user(new_user: User):
    """
    This function adds a new user to the system.
    """
    # Get the /etc/sysmanage.yaml configuration
    the_config = config.get_config()

    # Get the SQLAlchemy session
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())

    # Add the data to the database
    with session_local() as session:
        hashed_value = argon2_hash(new_user.password, the_config["security"]["password_salt"])
        user = models.User(userid=new_user.userid, active=True, hashed_password=hashed_value, last_access=datetime.now(timezone.utc))
        session.add(user)
        session.commit()
    
    return { "message": "success", "result": user }
