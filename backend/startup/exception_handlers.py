# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Exception handlers module for the SysManage server.

This module provides exception handlers for FastAPI to ensure CORS headers
are properly set on error responses.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.services.agent_capability_service import UnsupportedCapabilityError
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.startup.exceptions")

# Log message format constant for request debugging
LOG_MSG_REQUEST_METHOD_HEADERS = "Request method: %s, Headers: %s"

# Headers whose values are credentials.  They were logged in full on every
# error, which put bearer tokens and session cookies in the server log.
_SECRET_HEADERS = frozenset(
    {"authorization", "cookie", "set-cookie", "x-api-key", "proxy-authorization"}
)


def _safe_headers(request: Request) -> dict:
    """The request's headers with every credential value redacted."""
    return {
        name: ("[redacted]" if name.lower() in _SECRET_HEADERS else value)
        for name, value in request.headers.items()
    }


def register_exception_handlers(app: FastAPI, origins: list):
    """
    Register exception handlers for the FastAPI application.

    Args:
        app: The FastAPI application instance
        origins: List of allowed CORS origins
    """
    logger.info("=== REGISTERING EXCEPTION HANDLERS ===")

    @app.exception_handler(UnsupportedCapabilityError)
    async def unsupported_capability_handler(
        request: Request, exc: UnsupportedCapabilityError
    ):
        """Phase 19: the target agent advertises it cannot run this command.

        409 rather than 400 or 501: the request is well-formed and the command
        is one this server supports -- it conflicts with the STATE of that
        particular host.  A 4xx also matters because this is not a bug to
        retry; the answer will be the same until the agent is replaced with a
        fuller build.
        """
        logger.info(
            "Refused '%s' for %s -- agent advertises a reduced capability set",
            exc.command_type,
            exc.hostname or "unknown host",
        )
        response = JSONResponse(
            status_code=409,
            content={
                "detail": str(exc),
                "command_type": exc.command_type,
                "reason": "unsupported_capability",
            },
        )
        # Same manual CORS treatment as the other error handlers -- a browser
        # cannot read the explanation without it, which would turn a clear
        # "not supported on this agent" into an opaque network error.
        request_origin = request.headers.get("origin")
        if request_origin and request_origin in origins:
            response.headers["Access-Control-Allow-Origin"] = request_origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Expose-Headers"] = "Authorization"
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """Handle HTTP exceptions and ensure CORS headers are included."""
        # A 4xx is the API answering as designed (401, 402, 404, 422 ...), so
        # it is one INFO line; only a 5xx raised as an HTTPException warns.
        # Logging every 4xx at WARNING with the full headers flooded CI (the
        # route walk refuses 800+ routes) and production logs alike.
        level = logger.warning if exc.status_code >= 500 else logger.info
        level(
            "HTTP Exception occurred - Status: %s, Detail: %s, %s %s",
            exc.status_code,
            exc.detail,
            request.method,
            request.url.path,
        )
        logger.debug(
            LOG_MSG_REQUEST_METHOD_HEADERS, request.method, _safe_headers(request)
        )

        response = JSONResponse(
            status_code=exc.status_code, content={"detail": exc.detail}
        )

        # Add CORS headers manually for error responses
        request_origin = request.headers.get("origin")
        logger.debug("Request origin: %s", request_origin)
        if request_origin and request_origin in origins:
            logger.debug("Adding CORS headers for origin: %s", request_origin)
            response.headers["Access-Control-Allow-Origin"] = request_origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Expose-Headers"] = "Authorization"
        elif request_origin:
            # No Origin at all is a same-origin or non-browser call: normal.
            logger.warning("Origin %s not in allowed origins", request_origin)

        return response

    logger.info("HTTP exception handler registered")

    @app.exception_handler(500)
    async def internal_server_error_handler(request: Request, exc: Exception):
        """Handle internal server errors and ensure CORS headers are included."""
        logger.error(
            "Internal Server Error occurred - Path: %s, Exception: %s",
            request.url.path,
            exc,
            exc_info=True,
        )
        logger.error(
            LOG_MSG_REQUEST_METHOD_HEADERS, request.method, _safe_headers(request)
        )
        logger.error("Exception type: %s", type(exc).__name__)
        logger.error("Exception args: %s", exc.args)

        response = JSONResponse(
            status_code=500, content={"detail": "Internal server error"}
        )

        # Add CORS headers manually for error responses
        request_origin = request.headers.get("origin")
        logger.debug("Request origin for 500 error: %s", request_origin)
        if request_origin and request_origin in origins:
            logger.debug("Adding CORS headers for 500 error origin: %s", request_origin)
            response.headers["Access-Control-Allow-Origin"] = request_origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Expose-Headers"] = "Authorization"
        elif request_origin:
            logger.warning(
                "Origin %s not in allowed origins for 500 error", request_origin
            )

        return response

    logger.info("Internal server error handler registered")

    # Add a general exception handler for any unhandled exceptions
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle any unhandled exceptions."""
        logger.error(
            "Unhandled Exception occurred - Path: %s, Exception: %s",
            request.url.path,
            exc,
            exc_info=True,
        )
        logger.error(
            LOG_MSG_REQUEST_METHOD_HEADERS, request.method, _safe_headers(request)
        )
        logger.error("Exception type: %s", type(exc).__name__)
        logger.error("Exception args: %s", exc.args)

        response = JSONResponse(
            status_code=500, content={"detail": "An unexpected error occurred"}
        )

        # Add CORS headers manually for error responses
        request_origin = request.headers.get("origin")
        logger.debug("Request origin for general exception: %s", request_origin)
        if request_origin and request_origin in origins:
            logger.debug(
                "Adding CORS headers for general exception origin: %s", request_origin
            )
            response.headers["Access-Control-Allow-Origin"] = request_origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Expose-Headers"] = "Authorization"

        return response

    logger.info("General exception handler registered")
    logger.info("=== EXCEPTION HANDLERS REGISTRATION COMPLETE ===")
