"""
This module ise used to verify the JWT token we use for authentication
"""

from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.auth.auth_handler import decode_jwt


class JWTBearer(HTTPBearer):
    """
    This is a subclass of the FastAPI HTTPBearer class that is used to manage
    authentication via JWT
    """
    def __init__(self, auto_error: bool = True):
        """
        We are turning on auto_error here
        """
        super(JWTBearer, self).__init__(auto_error=auto_error)

    async def __call__(self, request: Request):
        """
        This function verifies the JWT token as well as the overall
        credential scheme used.
        """
        credentials: HTTPAuthorizationCredentials = await super(JWTBearer, self).__call__(request)
        if credentials:
            print('credentials exist')
            if not credentials.scheme == "Bearer":
                raise HTTPException(status_code=403, detail="Invalid authentication scheme.")
            if not self.verify_jwt(credentials.credentials):
                raise HTTPException(status_code=403, detail="Invalid token or expired token.")
            
            print("valid credentials")
            return credentials.credentials
        
        print('Credentials did not exist.')
        raise HTTPException(status_code=403, detail="Invalid authorization code.")

    def verify_jwt(self, jwtoken: str) -> bool:
        """
        This function decodes and verifies the JWT token
        """
        is_token_valid: bool = False

        try:
            payload = decode_jwt(jwtoken)
        except:
            payload = None
        if payload:
            is_token_valid = True

        return is_token_valid
