"""
Exception handlers module for the SysManage server.

This module provides exception handlers for FastAPI to ensure CORS headers
are properly set on error responses.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.startup.exceptions")

# Log message format constant for request debugging
LOG_MSG_REQUEST_METHOD_HEADERS = "Request method: %s, Headers: %s"


def register_exception_handlers(app: FastAPI, origins: list):
    """
    Register exception handlers for the FastAPI application.

    Args:
        app: The FastAPI application instance
        origins: List of allowed CORS origins
    """
    logger.info("=== REGISTERING EXCEPTION HANDLERS ===")

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """Handle HTTP exceptions and ensure CORS headers are included."""
        logger.warning(
            "HTTP Exception occurred - Status: %s, Detail: %s, Path: %s",
            exc.status_code,
            exc.detail,
            request.url.path,
        )
        logger.warning(
            LOG_MSG_REQUEST_METHOD_HEADERS, request.method, dict(request.headers)
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
        else:
            logger.warning(
                "Origin %s not in allowed origins or not provided", request_origin
            )

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
            LOG_MSG_REQUEST_METHOD_HEADERS, request.method, dict(request.headers)
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
        else:
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
            LOG_MSG_REQUEST_METHOD_HEADERS, request.method, dict(request.headers)
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
