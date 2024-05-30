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
    print(f'Returning token {token}')
    return {
        "Authorization": token
    }

def sign_jwt(user_id: str):
    """
    This function signs/encodes a JWT token
    """
    # Create the payload
    payload = {
        "user_id": user_id,
        "expires": time.time() + int(the_config["security"]["jwt_auth_timeout"])
    }

    # Encode the token
    the_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    # Return the encoded token
#    return token_response(the_token)
    return the_token

def decode_jwt(token: str) -> dict:
    """
    This function decodes a JWT token
    """
    try:
        decoded_token = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

        # Test to see if the token has expired
        if decoded_token["expires"] >= time.time():
            print("Token is NOT expired")
            return decoded_token

        # Token has expired
        return None
    except (jwt.exceptions.InvalidTokenError, jwt.exceptions.DecodeError):
        print("JWT exception")
        return {}
    except Exception as e:
        print(f"Uncaught exception in decode_jwt: {e}")
