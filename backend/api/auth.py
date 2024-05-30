"""
This module provides the necessary function to support login to the SysManage
server.
"""
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr
from pyargon2 import hash as argon2_hash
from sqlalchemy.orm import sessionmaker

from backend.auth.auth_handler import sign_jwt, decode_jwt, sign_refresh_token
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
async def login(login_data: UserLogin, response: Response):
    """
    This function provides login ability to the SysManage server.
    """
    # Get the /etc/sysmanage.yaml configuration
    the_config = config.get_config()

    db.get_db()
    if login_data.userid == the_config["security"]["admin_userid"]:
        if login_data.password == the_config["security"]["admin_password"]:
            refresh_token = sign_refresh_token(login_data.userid)
            jwt_refresh_timout = int(the_config["security"]["jwt_refresh_timeout"])
            response.set_cookie(key='refresh_token',
                                value=refresh_token,
                                expires=datetime.now().replace(tzinfo=timezone.utc) + timedelta(seconds=jwt_refresh_timout),
                                path='/',
                                domain='sysmanage.org',
                                secure=True,
                                httponly=True,
                                samesite='none')
            return {
                "Authorization": sign_jwt(login_data.userid)
            }

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

                # Add the refresh token to an http-only cookie
                response.body = {
                    "Authorization": sign_jwt(login_data.userid)
                }
                refresh_token = sign_refresh_token(login_data.userid)
                jwt_refresh_timout = int(the_config["security"]["jwt_refresh_timeout"])
                response.set_cookie(key='refresh_token',
                                    value=refresh_token,
                                    expires=datetime.now().replace(tzinfo=timezone.utc) + timedelta(seconds=jwt_refresh_timout),
                                    path='/',
                                    domain='sysmanage.org',
                                    secure=True,
                                    httponly=True,
                                    samesite='none')

                # Return success
                return response

    # If we got here, then there was no match
    raise HTTPException(status_code=401, detail="Bad userid or password")

@router.post("/refresh")
async def refresh(request: Request):
    """
    This API call looks for refresh token passed in the cookies of the
    request as an http_only cookie (inaccessible to the client).  If present,
    a new JWT Authentication token will be generated and returned.  If not,
    then a 403 - Forbidden error will be returned, forcing the client to
    re-authenticate via a user-managed login.
    """
    if len(request.cookies) > 0:
        if 'refresh_token' in request.cookies:
            refresh_token = request.cookies['refresh_token']
            token_dict = decode_jwt(refresh_token)
            the_userid = token_dict['user_id']
            new_token = sign_jwt(the_userid)
            return {
                "Authorization": new_token
            }

    raise HTTPException(status_code=403, detail="Invalid or missing refresh token")
