"""
This module manages the JWT aut mechanism used by the backend.
"""
import time
from typing import Dict

import jwt
import jwt.exceptions
from backend.config import config

# Read the YAML file
the_config = config.get_config()

JWT_SECRET = the_config["security"]["jwt_secret"]
JWT_ALGORITHM = the_config["security"]["jwt_algorithm"]

def token_response(token: str):
    """
    This is a helper function to create a JSON payload from a jwt token
    """
    return {
        "access_token": token
    }

def sign_jwt(user_id: str) -> Dict[str, str]:
    """
    This function signs/encodes a JWT token
    """
    payload = {
        "user_id": user_id,
        "expires": time.time() + int(the_config["security"]["jwt_timeout"])
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return token_response(token)

def decode_jwt(token: str) -> dict:
    """
    This function decodes a JWT token
    """
    try:
        decoded_token = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return decoded_token if decoded_token["expires"] >= time.time() else None
    except (jwt.exceptions.InvalidTokenError, jwt.exceptions.DecodeError):
        return {}
