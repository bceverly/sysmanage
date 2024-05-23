"""
This module manages the JWT aut mechanism used by the backend.
"""
from datetime import datetime, timezone, timedelta
import time
from typing import Dict

import jwt
import jwt.exceptions
from sqlalchemy.orm import sessionmaker

from backend.config import config
from backend.persistence import db, models

# Read the YAML file
the_config = config.get_config()

JWT_SECRET = the_config["security"]["jwt_secret"]
JWT_ALGORITHM = the_config["security"]["jwt_algorithm"]

def token_response(token: str):
    """
    This is a helper function to create a JSON payload from a jwt token
    """
    return {
        "Reauthorization": token
    }

def sign_jwt(user_id: str) -> Dict[str, str]:
    """
    This function signs/encodes a JWT token
    """
    # Create the payload
    payload = {
        "user_id": user_id,
        "expires": time.time() + int(the_config["security"]["jwt_timeout"])
    }

    # Encode the token
    the_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    # Return the encoded token
    return token_response(the_token)

def reauth_decode_jwt(token: str) -> dict:
    """
    This function is ONLY used to decode a token for the purpose of generating
    a reauthorization token.  It does not check to see if a token has been
    used already and thus would be subject to a replay attack within the
    expiration timeframe.  It is to only be used after a token has already
    been validated as not previously used so that the userid can be extracted
    for use in creating the reauthorization token.
    """
    try:
        decoded_token = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

        # Test to see if the token has expired
        if decoded_token["expires"] >= time.time():
            return decoded_token

        # Token has expired
        return None
    except (jwt.exceptions.InvalidTokenError, jwt.exceptions.DecodeError):
        return {}

def decode_jwt(token: str) -> dict:
    """
    This function decodes a JWT token
    """
    try:
        print(f"decode_jwt(token) = {token}")
        decoded_token = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

        # Test to see if the token has expired
        if decoded_token["expires"] >= time.time():
            # Time value is not past expiration; however, need to check to
            # see if the token has already been used
            session_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())

            # Delete any old tokens to keep the query fast
            with session_local() as session:
                stmt = session.query(models.BearerToken).filter(models.BearerToken.created_datetime < datetime.now(timezone.utc) - 
                                                                timedelta(seconds=int(the_config["security"]["jwt_timeout"])))
                stmt.delete()
                session.commit()

            # Check to see if the token is in the database, if not, then it has never
            # been used and is currently valid.
            with session_local() as session:
                tokens = session.query(models.BearerToken).filter(models.BearerToken.token == token).all()
                if len(tokens) > 0:
                    # We got a hit on the database, this is a replay attack
                    return None

            # Insert the token into the database, indicating that the token
            # is no longer valid (i.e. it has been used)
            bearer_token = models.BearerToken(token=token,
                                              created_datetime=datetime.now(timezone.utc))
            with session_local() as session:
                session.add(bearer_token)
                session.commit()

            return decoded_token

        # Token has expired
        return None
    except (jwt.exceptions.InvalidTokenError, jwt.exceptions.DecodeError):
        return {}
