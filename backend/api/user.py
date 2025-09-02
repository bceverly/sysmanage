"""
This module contains the API implementation for the user object in the system.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pyargon2 import hash as argon2_hash
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import sessionmaker

from backend.auth.auth_bearer import JWTBearer
from backend.auth.auth_handler import decode_jwt
from backend.config import config
from backend.persistence import db, models
from backend.security.login_security import login_security

router = APIRouter()


class User(BaseModel):
    """
    This class represents the JSON payload to the /user POST/PUT requests.
    """

    active: bool
    userid: EmailStr
    password: str
    first_name: str = None
    last_name: str = None


@router.delete("/user/{user_id}", dependencies=[Depends(JWTBearer())])
async def delete_user(user_id: int):
    """
    This function deletes a single user given an id
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # See if we were passed a valid id
        users = session.query(models.User).filter(models.User.id == user_id).all()

        # Check for failure
        if len(users) != 1:
            raise HTTPException(status_code=404, detail="User not found")

        # Delete the record
        session.query(models.User).filter(models.User.id == user_id).delete()
        session.commit()

    return {"result": True}


@router.get("/user/me", dependencies=[Depends(JWTBearer())])
async def get_logged_in_user(request: Request):
    """
    This function retrieves the user record for the currently logged in
    user.
    """
    # Get the current userid
    userid = ""
    if "Authorization" in request.headers:
        token = request.headers.get("Authorization")
        the_elements = token.split()
        if len(the_elements) == 2:
            old_dict = decode_jwt(the_elements[1])
            if old_dict:
                if "user_id" in old_dict:
                    userid = old_dict["user_id"]

    # Check for special case admin user
    the_config = config.get_config()
    if userid == the_config["security"]["admin_userid"]:
        ret_user = models.User(
            id=0,
            active=True,
            userid=userid,
            is_locked=False,
            failed_login_attempts=0,
            locked_at=None,
        )
        return ret_user

    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        users = session.query(models.User).filter(models.User.userid == userid).all()

        # Check for failure
        if len(users) != 1:
            raise HTTPException(status_code=404, detail="User not found")

        ret_user = models.User(
            id=users[0].id,
            active=users[0].active,
            userid=users[0].userid,
            first_name=users[0].first_name,
            last_name=users[0].last_name,
            is_locked=users[0].is_locked,
            failed_login_attempts=users[0].failed_login_attempts,
            locked_at=users[0].locked_at,
        )

        return ret_user


@router.get("/user/{user_id}", dependencies=[Depends(JWTBearer())])
async def get_user(user_id: int):
    """
    This function retrieves a single user by its id
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        users = session.query(models.User).filter(models.User.id == user_id).all()

        # Check for failure
        if len(users) != 1:
            raise HTTPException(status_code=404, detail="User not found")

        ret_user = models.User(
            id=users[0].id,
            active=users[0].active,
            userid=users[0].userid,
            first_name=users[0].first_name,
            last_name=users[0].last_name,
            is_locked=users[0].is_locked,
            failed_login_attempts=users[0].failed_login_attempts,
            locked_at=users[0].locked_at,
        )

        return ret_user


@router.get("/user/by_userid/{userid}", dependencies=[Depends(JWTBearer())])
async def get_user_by_userid(userid: str):
    """
    This function retrieves a single user by userid
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        users = session.query(models.User).filter(models.User.userid == userid).all()

        # Check for failure
        if len(users) != 1:
            raise HTTPException(status_code=404, detail="User not found")

        ret_user = models.User(
            id=users[0].id,
            active=users[0].active,
            userid=users[0].userid,
            first_name=users[0].first_name,
            last_name=users[0].last_name,
            is_locked=users[0].is_locked,
            failed_login_attempts=users[0].failed_login_attempts,
            locked_at=users[0].locked_at,
        )

        return ret_user


@router.get("/users", dependencies=[Depends(JWTBearer())])
async def get_all_users():
    """
    This function retrieves all users in the system
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        result = session.query(models.User).all()

        ret_users = []
        for user in result:
            the_user = models.User(
                id=user.id,
                active=user.active,
                userid=user.userid,
                first_name=user.first_name,
                last_name=user.last_name,
                is_locked=user.is_locked,
                failed_login_attempts=user.failed_login_attempts,
                locked_at=user.locked_at,
            )
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
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    # Add the data to the database
    with session_local() as session:
        # See if the caller is trying to add a user that already exists
        check_duplicate = (
            session.query(models.User)
            .filter(models.User.userid == new_user.userid)
            .all()
        )
        if len(check_duplicate) > 0:
            raise HTTPException(status_code=409, detail="User already exists")

        # This is a unique user.  Proceed...
        hashed_value = argon2_hash(
            new_user.password, the_config["security"]["password_salt"]
        )
        user = models.User(
            userid=new_user.userid,
            active=new_user.active,
            first_name=new_user.first_name,
            last_name=new_user.last_name,
            hashed_password=hashed_value,
            last_access=datetime.now(timezone.utc),
        )
        session.add(user)
        session.commit()
        ret_user = models.User(
            id=user.id,
            active=user.active,
            userid=user.userid,
            is_locked=user.is_locked,
            failed_login_attempts=user.failed_login_attempts,
            locked_at=user.locked_at,
        )

        return ret_user


@router.put("/user/{user_id}", dependencies=[Depends(JWTBearer())])
async def update_user(user_id: int, user_data: User):
    """
    This function updates an existing user by id
    """

    # Get the /etc/sysmanage.yaml configuration
    the_config = config.get_config()

    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    # Update the user
    with session_local() as session:
        # See if we were passed a valid id
        users = session.query(models.User).filter(models.User.id == user_id).all()

        # Check for failure
        if len(users) != 1:
            raise HTTPException(status_code=404, detail="User not found")

        # Update the values
        hashed_value = argon2_hash(
            user_data.password, the_config["security"]["password_salt"]
        )
        session.query(models.User).filter(models.User.id == user_id).update(
            {
                models.User.active: user_data.active,
                models.User.userid: user_data.userid,
                models.User.first_name: user_data.first_name,
                models.User.last_name: user_data.last_name,
                models.User.hashed_password: hashed_value,
                models.User.last_access: datetime.now(timezone.utc),
            }
        )
        session.commit()

        # Get updated user data to return current lock status
        updated_user = (
            session.query(models.User).filter(models.User.id == user_id).first()
        )
        ret_user = models.User(
            id=user_id,
            active=user_data.active,
            userid=user_data.userid,
            is_locked=updated_user.is_locked,
            failed_login_attempts=updated_user.failed_login_attempts,
            locked_at=updated_user.locked_at,
        )

    return ret_user


@router.post("/user/{user_id}/unlock", dependencies=[Depends(JWTBearer())])
async def unlock_user(user_id: int):
    """
    This function unlocks a user account manually
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # See if we were passed a valid id
        user = session.query(models.User).filter(models.User.id == user_id).first()

        # Check for failure
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Unlock the account
        login_security.unlock_user_account(user, session)

        ret_user = models.User(
            id=user.id,
            active=user.active,
            userid=user.userid,
            is_locked=user.is_locked,
            failed_login_attempts=user.failed_login_attempts,
            locked_at=user.locked_at,
        )

    return ret_user
