"""
Tests for backend/startup/route_registration.py module.
Tests route registration functionality.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI


class TestRegisterRoutes:
    """Tests for register_routes function."""

    def test_register_routes_function_exists(self):
        """Test register_routes function exists."""
        from backend.startup.route_registration import register_routes

        assert callable(register_routes)

    def test_register_routes_adds_routes(self):
        """Test register_routes adds routes to app."""
        from backend.startup.route_registration import register_routes

        app = FastAPI()
        initial_routes = len(app.routes)

        register_routes(app)

        # Should have added routes
        assert len(app.routes) > initial_routes

    def test_register_routes_includes_auth_router(self):
        """Test register_routes includes auth router."""
        from backend.startup.route_registration import register_routes

        app = FastAPI()
        register_routes(app)

        # Check that auth routes are included
        paths = [getattr(route, "path", "") for route in app.routes]
        assert "/login" in paths or any("/login" in p for p in paths)

    def test_register_routes_includes_health_routes(self):
        """Test register_routes includes health endpoints when app routes are registered."""
        from backend.startup.route_registration import (
            register_routes,
            register_app_routes,
        )

        app = FastAPI()
        register_routes(app)
        register_app_routes(app)

        paths = [getattr(route, "path", "") for route in app.routes]
        assert "/api/health" in paths

    def test_register_routes_includes_user_router(self):
        """Test register_routes includes user router with /api prefix."""
        from backend.startup.route_registration import register_routes

        app = FastAPI()
        register_routes(app)

        paths = [getattr(route, "path", "") for route in app.routes]
        # Check for user routes with /api prefix
        has_user_routes = any("/api/user" in p for p in paths)
        assert has_user_routes

    def test_register_routes_includes_host_router(self):
        """Test register_routes includes host router."""
        from backend.startup.route_registration import register_routes

        app = FastAPI()
        register_routes(app)

        paths = [getattr(route, "path", "") for route in app.routes]
        has_host_routes = any("/host" in p for p in paths)
        assert has_host_routes

    def test_register_routes_includes_certificates_router(self):
        """Test register_routes includes certificates router."""
        from backend.startup.route_registration import register_routes

        app = FastAPI()
        register_routes(app)

        paths = [getattr(route, "path", "") for route in app.routes]
        has_cert_routes = any("/certificate" in p for p in paths)
        assert has_cert_routes


class TestRegisterAppRoutes:
    """Tests for register_app_routes function."""

    def test_register_app_routes_function_exists(self):
        """Test register_app_routes function exists."""
        from backend.startup.route_registration import register_app_routes

        assert callable(register_app_routes)

    def test_register_app_routes_adds_root(self):
        """Test register_app_routes adds root route."""
        from backend.startup.route_registration import register_app_routes

        app = FastAPI()
        register_app_routes(app)

        paths = [getattr(route, "path", "") for route in app.routes]
        assert "/" in paths

    def test_register_app_routes_adds_health_check(self):
        """Test register_app_routes adds health check route."""
        from backend.startup.route_registration import register_app_routes

        app = FastAPI()
        register_app_routes(app)

        paths = [getattr(route, "path", "") for route in app.routes]
        assert "/api/health" in paths

    @pytest.mark.asyncio
    async def test_root_endpoint_returns_message(self):
        """Test root endpoint returns expected message."""
        from backend.startup.route_registration import register_app_routes

        from fastapi.testclient import TestClient

        app = FastAPI()
        register_app_routes(app)

        client = TestClient(app)
        response = client.get("/")

        assert response.status_code == 200
        assert response.json() == {"message": "Hello World"}

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_status(self):
        """Test health endpoint returns healthy status."""
        from backend.startup.route_registration import register_app_routes

        from fastapi.testclient import TestClient

        app = FastAPI()
        register_app_routes(app)

        client = TestClient(app)
        response = client.get("/api/health")

        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

    @pytest.mark.asyncio
    async def test_health_endpoint_supports_head(self):
        """Test health endpoint supports HEAD request."""
        from backend.startup.route_registration import register_app_routes

        from fastapi.testclient import TestClient

        app = FastAPI()
        register_app_routes(app)

        client = TestClient(app)
        response = client.head("/api/health")

        assert response.status_code == 200


class TestRouteRegistrationImports:
    """Tests for module imports."""

    def test_imports_fastapi(self):
        """Test FastAPI is imported."""
        from backend.startup import route_registration

        # Check that FastAPI is used in the module
        assert hasattr(route_registration, "FastAPI")

    def test_imports_logger(self):
        """Test logger is configured."""
        from backend.startup import route_registration

        assert hasattr(route_registration, "logger")

    def test_imports_api_modules(self):
        """Test API modules are imported."""
        from backend.startup import route_registration

        # Check that key API modules are imported
        assert hasattr(route_registration, "auth")
        assert hasattr(route_registration, "user")
        assert hasattr(route_registration, "host")
