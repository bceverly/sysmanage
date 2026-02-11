"""
Tests for backend/startup/exception_handlers.py module.
Tests exception handlers for the FastAPI application.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException


class TestRegisterExceptionHandlers:
    """Tests for register_exception_handlers function."""

    def test_http_exception_handler_with_cors(self):
        """Test HTTP exception handler adds CORS headers."""
        from backend.startup.exception_handlers import register_exception_handlers

        app = FastAPI()
        origins = ["http://localhost:3000", "http://example.com"]
        register_exception_handlers(app, origins)

        @app.get("/test-error")
        async def test_endpoint():
            raise StarletteHTTPException(status_code=404, detail="Not found")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/test-error", headers={"origin": "http://localhost:3000"}
        )

        assert response.status_code == 404
        assert response.json() == {"detail": "Not found"}
        assert (
            response.headers.get("Access-Control-Allow-Origin")
            == "http://localhost:3000"
        )
        assert response.headers.get("Access-Control-Allow-Credentials") == "true"

    def test_http_exception_handler_without_origin(self):
        """Test HTTP exception handler without origin header."""
        from backend.startup.exception_handlers import register_exception_handlers

        app = FastAPI()
        origins = ["http://localhost:3000"]
        register_exception_handlers(app, origins)

        @app.get("/test-error")
        async def test_endpoint():
            raise StarletteHTTPException(status_code=400, detail="Bad request")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test-error")

        assert response.status_code == 400
        assert response.json() == {"detail": "Bad request"}
        # No CORS headers when no origin
        assert "Access-Control-Allow-Origin" not in response.headers

    def test_http_exception_handler_origin_not_allowed(self):
        """Test HTTP exception handler with non-allowed origin."""
        from backend.startup.exception_handlers import register_exception_handlers

        app = FastAPI()
        origins = ["http://localhost:3000"]
        register_exception_handlers(app, origins)

        @app.get("/test-error")
        async def test_endpoint():
            raise StarletteHTTPException(status_code=403, detail="Forbidden")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test-error", headers={"origin": "http://evil.com"})

        assert response.status_code == 403
        # No CORS headers for non-allowed origin
        assert "Access-Control-Allow-Origin" not in response.headers

    def test_general_exception_handler_with_cors(self):
        """Test general exception handler adds CORS headers."""
        from backend.startup.exception_handlers import register_exception_handlers

        app = FastAPI()
        origins = ["http://localhost:8080"]
        register_exception_handlers(app, origins)

        @app.get("/test-crash")
        async def test_endpoint():
            raise ValueError("Something went wrong")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/test-crash", headers={"origin": "http://localhost:8080"}
        )

        assert response.status_code == 500
        assert "detail" in response.json()
        assert (
            response.headers.get("Access-Control-Allow-Origin")
            == "http://localhost:8080"
        )

    def test_general_exception_handler_without_cors(self):
        """Test general exception handler without CORS origin."""
        from backend.startup.exception_handlers import register_exception_handlers

        app = FastAPI()
        origins = []
        register_exception_handlers(app, origins)

        @app.get("/test-crash")
        async def test_endpoint():
            raise RuntimeError("Unexpected error")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test-crash")

        assert response.status_code == 500
        assert "Access-Control-Allow-Origin" not in response.headers

    def test_handlers_registered(self):
        """Test that all handlers are registered."""
        from backend.startup.exception_handlers import register_exception_handlers

        app = FastAPI()
        register_exception_handlers(app, ["http://localhost:3000"])

        # Check that exception handlers were registered
        assert StarletteHTTPException in app.exception_handlers
        assert Exception in app.exception_handlers
