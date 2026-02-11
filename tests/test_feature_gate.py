"""
Tests for backend/licensing/feature_gate.py module.
Tests feature and module gating decorators for Pro+ licensing.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.licensing.feature_gate import (
    LicenseRequiredError,
    _check_module_licensed_http,
    _check_module_licensed_sync,
    _check_module_loaded_http,
    _check_module_loaded_sync,
    requires_feature,
    requires_module,
    requires_pro_plus,
)
from backend.licensing.features import FeatureCode, ModuleCode


class TestLicenseRequiredError:
    """Tests for LicenseRequiredError exception class."""

    def test_init_with_message_only(self):
        """Test initialization with message only."""
        error = LicenseRequiredError("Test message")
        assert str(error) == "Test message"
        assert error.feature is None
        assert error.module is None

    def test_init_with_feature(self):
        """Test initialization with feature."""
        error = LicenseRequiredError("Test message", feature="health")
        assert str(error) == "Test message"
        assert error.feature == "health"
        assert error.module is None

    def test_init_with_module(self):
        """Test initialization with module."""
        error = LicenseRequiredError("Test message", module="health_engine")
        assert str(error) == "Test message"
        assert error.feature is None
        assert error.module == "health_engine"

    def test_init_with_both(self):
        """Test initialization with both feature and module."""
        error = LicenseRequiredError("Test", feature="health", module="health_engine")
        assert error.feature == "health"
        assert error.module == "health_engine"


class TestRequiresFeature:
    """Tests for requires_feature decorator."""

    @patch("backend.licensing.feature_gate.license_service")
    def test_requires_feature_async_allowed(self, mock_service):
        """Test async function with feature allowed."""
        mock_service.has_feature.return_value = True

        @requires_feature(FeatureCode.HEALTH_ANALYSIS)
        async def test_func():
            return "success"

        result = asyncio.get_event_loop().run_until_complete(test_func())
        assert result == "success"
        mock_service.has_feature.assert_called_once_with(FeatureCode.HEALTH_ANALYSIS)

    @patch("backend.licensing.feature_gate.license_service")
    def test_requires_feature_async_denied(self, mock_service):
        """Test async function with feature denied."""
        mock_service.has_feature.return_value = False

        @requires_feature(FeatureCode.HEALTH_ANALYSIS)
        async def test_func():
            return "success"

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(test_func())

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error"] == "pro_plus_required"
        assert "health" in exc_info.value.detail["message"]

    @patch("backend.licensing.feature_gate.license_service")
    def test_requires_feature_sync_allowed(self, mock_service):
        """Test sync function with feature allowed."""
        mock_service.has_feature.return_value = True

        @requires_feature(FeatureCode.HEALTH_ANALYSIS)
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"

    @patch("backend.licensing.feature_gate.license_service")
    def test_requires_feature_sync_denied(self, mock_service):
        """Test sync function with feature denied."""
        mock_service.has_feature.return_value = False

        @requires_feature(FeatureCode.HEALTH_ANALYSIS)
        def test_func():
            return "success"

        with pytest.raises(LicenseRequiredError) as exc_info:
            test_func()

        assert "health" in str(exc_info.value)
        assert exc_info.value.feature == "health"

    @patch("backend.licensing.feature_gate.license_service")
    def test_requires_feature_with_string(self, mock_service):
        """Test decorator with string feature code."""
        mock_service.has_feature.return_value = True

        # Use the actual feature code value
        @requires_feature("health")
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"

    def test_requires_feature_invalid_string(self):
        """Test decorator with invalid feature string."""
        with pytest.raises(ValueError) as exc_info:

            @requires_feature("invalid_feature")
            def test_func():
                return "success"

        assert "Unknown feature code" in str(exc_info.value)


class TestCheckModuleLicensedHttp:
    """Tests for _check_module_licensed_http function."""

    @patch("backend.licensing.feature_gate.license_service")
    def test_check_module_licensed_success(self, mock_service):
        """Test when module is licensed."""
        mock_service.has_module.return_value = True
        # Should not raise
        _check_module_licensed_http(ModuleCode.HEALTH_ENGINE)
        mock_service.has_module.assert_called_once_with(ModuleCode.HEALTH_ENGINE)

    @patch("backend.licensing.feature_gate.license_service")
    def test_check_module_licensed_failure(self, mock_service):
        """Test when module is not licensed."""
        mock_service.has_module.return_value = False

        with pytest.raises(HTTPException) as exc_info:
            _check_module_licensed_http(ModuleCode.HEALTH_ENGINE)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error"] == "pro_plus_required"
        assert "health_engine" in exc_info.value.detail["message"]


class TestCheckModuleLoadedHttp:
    """Tests for _check_module_loaded_http function."""

    @patch("backend.licensing.module_loader.module_loader")
    def test_check_module_loaded_success(self, mock_loader):
        """Test when module is loaded."""
        mock_loader.is_module_loaded.return_value = True
        # Should not raise
        _check_module_loaded_http(ModuleCode.HEALTH_ENGINE)

    @patch("backend.licensing.module_loader.module_loader")
    def test_check_module_loaded_failure(self, mock_loader):
        """Test when module is not loaded."""
        mock_loader.is_module_loaded.return_value = False

        with pytest.raises(HTTPException) as exc_info:
            _check_module_loaded_http(ModuleCode.HEALTH_ENGINE)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["error"] == "module_not_available"


class TestCheckModuleLicensedSync:
    """Tests for _check_module_licensed_sync function."""

    @patch("backend.licensing.feature_gate.license_service")
    def test_check_module_licensed_sync_success(self, mock_service):
        """Test when module is licensed."""
        mock_service.has_module.return_value = True
        # Should not raise
        _check_module_licensed_sync(ModuleCode.HEALTH_ENGINE)

    @patch("backend.licensing.feature_gate.license_service")
    def test_check_module_licensed_sync_failure(self, mock_service):
        """Test when module is not licensed."""
        mock_service.has_module.return_value = False

        with pytest.raises(LicenseRequiredError) as exc_info:
            _check_module_licensed_sync(ModuleCode.HEALTH_ENGINE)

        assert exc_info.value.module == "health_engine"


class TestCheckModuleLoadedSync:
    """Tests for _check_module_loaded_sync function."""

    @patch("backend.licensing.module_loader.module_loader")
    def test_check_module_loaded_sync_success(self, mock_loader):
        """Test when module is loaded."""
        mock_loader.is_module_loaded.return_value = True
        # Should not raise
        _check_module_loaded_sync(ModuleCode.HEALTH_ENGINE)

    @patch("backend.licensing.module_loader.module_loader")
    def test_check_module_loaded_sync_failure(self, mock_loader):
        """Test when module is not loaded."""
        mock_loader.is_module_loaded.return_value = False

        with pytest.raises(LicenseRequiredError) as exc_info:
            _check_module_loaded_sync(ModuleCode.HEALTH_ENGINE)

        assert exc_info.value.module == "health_engine"


class TestRequiresModule:
    """Tests for requires_module decorator."""

    @patch("backend.licensing.module_loader.module_loader")
    @patch("backend.licensing.feature_gate.license_service")
    def test_requires_module_async_allowed(self, mock_service, mock_loader):
        """Test async function with module allowed."""
        mock_service.has_module.return_value = True
        mock_loader.is_module_loaded.return_value = True

        @requires_module(ModuleCode.HEALTH_ENGINE)
        async def test_func():
            return "success"

        result = asyncio.get_event_loop().run_until_complete(test_func())
        assert result == "success"

    @patch("backend.licensing.feature_gate.license_service")
    def test_requires_module_async_not_licensed(self, mock_service):
        """Test async function with module not licensed."""
        mock_service.has_module.return_value = False

        @requires_module(ModuleCode.HEALTH_ENGINE)
        async def test_func():
            return "success"

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(test_func())

        assert exc_info.value.status_code == 403

    @patch("backend.licensing.module_loader.module_loader")
    @patch("backend.licensing.feature_gate.license_service")
    def test_requires_module_async_not_loaded(self, mock_service, mock_loader):
        """Test async function with module not loaded."""
        mock_service.has_module.return_value = True
        mock_loader.is_module_loaded.return_value = False

        @requires_module(ModuleCode.HEALTH_ENGINE)
        async def test_func():
            return "success"

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(test_func())

        assert exc_info.value.status_code == 503

    @patch("backend.licensing.module_loader.module_loader")
    @patch("backend.licensing.feature_gate.license_service")
    def test_requires_module_sync_allowed(self, mock_service, mock_loader):
        """Test sync function with module allowed."""
        mock_service.has_module.return_value = True
        mock_loader.is_module_loaded.return_value = True

        @requires_module(ModuleCode.HEALTH_ENGINE)
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"

    @patch("backend.licensing.feature_gate.license_service")
    def test_requires_module_sync_not_licensed(self, mock_service):
        """Test sync function with module not licensed."""
        mock_service.has_module.return_value = False

        @requires_module(ModuleCode.HEALTH_ENGINE)
        def test_func():
            return "success"

        with pytest.raises(LicenseRequiredError):
            test_func()

    @patch("backend.licensing.module_loader.module_loader")
    @patch("backend.licensing.feature_gate.license_service")
    def test_requires_module_sync_not_loaded(self, mock_service, mock_loader):
        """Test sync function with module not loaded."""
        mock_service.has_module.return_value = True
        mock_loader.is_module_loaded.return_value = False

        @requires_module(ModuleCode.HEALTH_ENGINE)
        def test_func():
            return "success"

        with pytest.raises(LicenseRequiredError):
            test_func()

    @patch("backend.licensing.module_loader.module_loader")
    @patch("backend.licensing.feature_gate.license_service")
    def test_requires_module_with_string(self, mock_service, mock_loader):
        """Test decorator with string module code."""
        mock_service.has_module.return_value = True
        mock_loader.is_module_loaded.return_value = True

        @requires_module("health_engine")
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"

    def test_requires_module_invalid_string(self):
        """Test decorator with invalid module string."""
        with pytest.raises(ValueError) as exc_info:

            @requires_module("invalid_module")
            def test_func():
                return "success"

        assert "Unknown module code" in str(exc_info.value)


class TestRequiresProPlus:
    """Tests for requires_pro_plus decorator."""

    @patch("backend.licensing.feature_gate.license_service")
    def test_requires_pro_plus_async_allowed(self, mock_service):
        """Test async function with Pro+ active."""
        mock_service.is_pro_plus_active = True

        @requires_pro_plus()
        async def test_func():
            return "success"

        result = asyncio.get_event_loop().run_until_complete(test_func())
        assert result == "success"

    @patch("backend.licensing.feature_gate.license_service")
    def test_requires_pro_plus_async_denied(self, mock_service):
        """Test async function with Pro+ not active."""
        mock_service.is_pro_plus_active = False

        @requires_pro_plus()
        async def test_func():
            return "success"

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(test_func())

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error"] == "pro_plus_required"

    @patch("backend.licensing.feature_gate.license_service")
    def test_requires_pro_plus_sync_allowed(self, mock_service):
        """Test sync function with Pro+ active."""
        mock_service.is_pro_plus_active = True

        @requires_pro_plus()
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"

    @patch("backend.licensing.feature_gate.license_service")
    def test_requires_pro_plus_sync_denied(self, mock_service):
        """Test sync function with Pro+ not active."""
        mock_service.is_pro_plus_active = False

        @requires_pro_plus()
        def test_func():
            return "success"

        with pytest.raises(LicenseRequiredError) as exc_info:
            test_func()

        assert "Pro+" in str(exc_info.value)
