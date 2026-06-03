"""
This module manages the JWT aut mechanism used by the backend.
"""

import time
from typing import Optional

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
    # Returning authentication token
    return {"Authorization": token}


def sign_jwt(user_id: str):
    """
    This function signs/encodes a JWT token
    """
    # Create the payload
    payload = {
        "user_id": user_id,
        "expires": time.time() + int(the_config["security"]["jwt_auth_timeout"]),
    }

    # Encode the token
    the_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return the_token


def sign_refresh_token(user_id: str):
    """
    This function signs/encodes a JWT refresh token
    """
    # Create the payload
    payload = {
        "user_id": user_id,
        "expires": time.time() + int(the_config["security"]["jwt_refresh_timeout"]),
    }

    # Encode the token
    the_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return the_token


# MFA-pending tokens are short-lived (5 min default) so a stolen pending
# token can't be sat on indefinitely.  They carry a ``mfa_pending: True``
# claim that the JWTBearer dependency rejects — only the dedicated
# ``/api/auth/mfa/verify`` endpoint accepts them.
_MFA_PENDING_TTL_SECONDS = 5 * 60


def sign_mfa_pending_token(user_id: str) -> str:
    """Sign a short-lived token that authorises ``/api/auth/mfa/verify``
    only — i.e. proof that the password check just succeeded but the
    second factor still has to clear."""
    payload = {
        "user_id": user_id,
        "expires": time.time() + _MFA_PENDING_TTL_SECONDS,
        "mfa_pending": True,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_mfa_pending_token(token: str):
    """Decode an MFA-pending token, returning its payload only when the
    ``mfa_pending`` claim is set and the token hasn't expired.  Used by
    the verify endpoint to re-authorise the second-factor exchange.
    """
    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except (jwt.exceptions.InvalidTokenError, jwt.exceptions.DecodeError):
        return None
    if decoded.get("expires", 0) < time.time():
        return None
    if not decoded.get("mfa_pending"):
        return None
    return decoded


# Air-gap ISO download tokens are short-lived, single-purpose tokens that
# authorise ONE streaming ISO download.  A browser can't put the session
# JWT in the Authorization header when it follows a plain download link,
# and buffering a multi-GB ISO through fetch() to add the header OOMs the
# tab — so the UI requests one of these (authenticated) and then navigates
# the browser straight to the token-authed download route.  Scoped to a
# single run_id and expiring in minutes so a leaked URL is low-impact.
_AIRGAP_DOWNLOAD_TTL_SECONDS = 5 * 60


def sign_airgap_download_token(run_id: str) -> str:
    """Sign a short-lived token authorising a streaming download of one
    air-gap collection run's ISO (and nothing else)."""
    payload = {
        "run_id": str(run_id),
        "scope": "airgap-iso-download",
        "expires": time.time() + _AIRGAP_DOWNLOAD_TTL_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_airgap_download_token(token: str, run_id: str) -> bool:
    """Return True only when ``token`` is a valid, unexpired air-gap
    download token scoped to ``run_id``."""
    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except (jwt.exceptions.InvalidTokenError, jwt.exceptions.DecodeError):
        return False
    return (
        decoded.get("scope") == "airgap-iso-download"
        and str(decoded.get("run_id")) == str(run_id)
        and decoded.get("expires", 0) >= time.time()
    )


def sign_airgap_bundle_token(bundle_id: str) -> str:
    """Sign a short-lived token authorising a streaming download of one
    air-gap bundle ISO (and nothing else).  Same rationale as
    ``sign_airgap_download_token`` — a browser following a plain
    download link can't set the Authorization header, and buffering a
    multi-GB bundle through fetch() to add it OOMs the tab."""
    payload = {
        "bundle_id": str(bundle_id),
        "scope": "airgap-bundle-download",
        "expires": time.time() + _AIRGAP_DOWNLOAD_TTL_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_airgap_bundle_token(token: str, bundle_id: str) -> bool:
    """Return True only when ``token`` is a valid, unexpired air-gap
    bundle-download token scoped to ``bundle_id``."""
    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except (jwt.exceptions.InvalidTokenError, jwt.exceptions.DecodeError):
        return False
    return (
        decoded.get("scope") == "airgap-bundle-download"
        and str(decoded.get("bundle_id")) == str(bundle_id)
        and decoded.get("expires", 0) >= time.time()
    )


def decode_jwt(token: str) -> Optional[dict]:
    """
    This function decodes a JWT token
    """
    try:
        decoded_token = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

        # Test to see if the token has expired
        if decoded_token["expires"] >= time.time():
            return decoded_token

        # Token has expired
        return None
    except (jwt.exceptions.InvalidTokenError, jwt.exceptions.DecodeError):
        # JWT decoding exception
        return {}
    except (ValueError, TypeError, KeyError):
        # Uncaught exception in JWT decoding
        return None
