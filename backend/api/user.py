"""
This module contains the API implementation for the user object in the system.
"""
from datetime import datetime, timezone
from fastapi import HTTPException, APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import sessionmaker

from pyargon2 import hash as argon2_hash

from backend.auth.auth_bearer import JWTBearer
from backend.persistence import db, models
from backend.config import config

router = APIRouter()

class User(BaseModel):
    """
    This class represents the JSON payload to the /user POST/PUT requests.
    """
    active: bool
    userid: EmailStr
    password: str

@router.delete("/user/{id}", dependencies=[Depends(JWTBearer())])
async def delete_user(id: int):
    """
    This function deletes a single user given an id
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())

    with session_local() as session:
        # See if we were passed a valid id
        users = session.query(models.User).filter(models.User.id == id).all()

        # Check for failure
        if len(users) != 1:
            raise HTTPException(status_code=404, detail="User not found")

        # Delete the record
        session.query(models.User).filter(models.User.id == id).delete()
        session.commit()

    return {
        "result": True
        }

@router.get("/user/{id}", dependencies=[Depends(JWTBearer())])
async def get_user(id: int):
    """
    This function retrieves a single user by its id
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())

    with session_local() as session:
        users = session.query(models.User).filter(models.User.id == id).all()

        # Check for failure
        if len(users) != 1:
            raise HTTPException(status_code=404, detail="User not found")

        ret_user = models.User(id=users[0].id,
                               active=users[0].active,
                               userid=users[0].userid)

        return ret_user

@router.get("/user/by_userid/{userid}", dependencies=[Depends(JWTBearer())])
async def get_user_by_userid(userid: str):
    """
    This function retrieves a single user by userid
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())

    with session_local() as session:
        users = session.query(models.User).filter(models.User.userid == userid).all()

        # Check for failure
        if len(users) != 1:
            raise HTTPException(status_code=404, detail="User not found")
        
        ret_user = models.User(id=users[0].id,
                               active=users[0].active,
                               userid=users[0].userid)

        return ret_user

@router.get("/users", dependencies=[Depends(JWTBearer())])
async def get_all_users():
    """
    This function retrieves all users in the system
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())

    with session_local() as session:
        result = session.query(models.User).all()

        ret_users = []
        for user in result:
            the_user = models.User(id=user.id,
                                   active=user.active,
                                   userid=user.userid)
            ret_users.append(the_user)

        return ret_users

@router.post("/user", dependencies=[Depends(JWTBearer())])
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
        user = models.User(userid=new_user.userid,
                           active=new_user.active,
                           hashed_password=hashed_value,
                           last_access=datetime.now(timezone.utc))
        session.add(user)
        session.commit()
        ret_user = models.User(id = user.id,
                               active = user.active,
                               userid = user.userid)

        return ret_user 

@router.put("/user/{id}", dependencies=[Depends(JWTBearer())])
async def update_user(id: int, user_data: User):
    """
    This function updates an existing user by id
    """

    # Get the /etc/sysmanage.yaml configuration
    the_config = config.get_config()

    # Get the SQLAlchemy session
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())

    # Update the user
    with session_local() as session:
        # See if we were passed a valid id
        users = session.query(models.User).filter(models.User.id == id).all()

        # Check for failure
        if len(users) != 1:
            raise HTTPException(status_code=404, detail="User not found")

        # Update the values
        hashed_value = argon2_hash(user_data.password, the_config["security"]["password_salt"])
        session.query(models.User).filter(models.User.id == id).update({models.User.active: user_data.active,
                                                                        models.User.userid: user_data.userid, 
                                                                        models.User.hashed_password: hashed_value, 
                                                                        models.User.last_access: datetime.now(timezone.utc)})
        session.commit()

        ret_user = models.User(id = user_data.id,
                               active = user_data.active,
                               userid = user_data.userid)

    return ret_user
