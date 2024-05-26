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
            return decoded_token

        # Token has expired
        return None
    except (jwt.exceptions.InvalidTokenError, jwt.exceptions.DecodeError):
        return {}
