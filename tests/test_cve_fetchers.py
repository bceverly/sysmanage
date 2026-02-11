"""
Tests for backend/vulnerability/cve_fetchers.py module.
Tests the CVE fetcher wrapper classes for Pro+ vulnerability scanning.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.vulnerability.cve_fetchers import (
    CveFetchers,
    SeverityConverter,
    _get_module,
)
from backend.vulnerability.cve_sources import CveRefreshError


class TestGetModule:
    """Tests for _get_module function."""

    @patch("backend.vulnerability.cve_fetchers.module_loader")
    @patch("backend.vulnerability.cve_fetchers.license_service")
    def test_get_module_no_license(self, mock_license_service, mock_module_loader):
        """Test _get_module when license is not available."""
        mock_license_service.has_module.return_value = False

        result = _get_module()

        assert result is None

    @patch("backend.vulnerability.cve_fetchers.module_loader")
    @patch("backend.vulnerability.cve_fetchers.license_service")
    def test_get_module_success(self, mock_license_service, mock_module_loader):
        """Test _get_module when module is available."""
        mock_license_service.has_module.return_value = True
        mock_vuln_engine = MagicMock()
        mock_module_loader.get_module.return_value = mock_vuln_engine

        result = _get_module()

        assert result == mock_vuln_engine


class TestSeverityConverter:
    """Tests for SeverityConverter class."""

    @patch("backend.vulnerability.cve_fetchers._get_module")
    def test_cvss2_to_severity_success(self, mock_get_module):
        """Test cvss2_to_severity with module available."""
        mock_converter = MagicMock()
        mock_converter.cvss2_to_severity.return_value = "HIGH"
        mock_vuln_engine = MagicMock()
        mock_vuln_engine.SeverityConverter = mock_converter
        mock_get_module.return_value = mock_vuln_engine

        result = SeverityConverter.cvss2_to_severity(7.5)

        assert result == "HIGH"

    @patch("backend.vulnerability.cve_fetchers._get_module")
    def test_cvss2_to_severity_no_module(self, mock_get_module):
        """Test cvss2_to_severity without module."""
        mock_get_module.return_value = None

        with pytest.raises(CveRefreshError) as exc_info:
            SeverityConverter.cvss2_to_severity(7.5)

        assert "vuln_engine module required" in str(exc_info.value)

    @patch("backend.vulnerability.cve_fetchers._get_module")
    def test_cvss3_to_severity_success(self, mock_get_module):
        """Test cvss3_to_severity with module available."""
        mock_converter = MagicMock()
        mock_converter.cvss3_to_severity.return_value = "CRITICAL"
        mock_vuln_engine = MagicMock()
        mock_vuln_engine.SeverityConverter = mock_converter
        mock_get_module.return_value = mock_vuln_engine

        result = SeverityConverter.cvss3_to_severity(9.5)

        assert result == "CRITICAL"

    @patch("backend.vulnerability.cve_fetchers._get_module")
    def test_cvss3_to_severity_no_module(self, mock_get_module):
        """Test cvss3_to_severity without module."""
        mock_get_module.return_value = None

        with pytest.raises(CveRefreshError):
            SeverityConverter.cvss3_to_severity(9.5)

    @patch("backend.vulnerability.cve_fetchers._get_module")
    def test_ubuntu_priority_to_severity_success(self, mock_get_module):
        """Test ubuntu_priority_to_severity with module available."""
        mock_converter = MagicMock()
        mock_converter.ubuntu_priority_to_severity.return_value = "MEDIUM"
        mock_vuln_engine = MagicMock()
        mock_vuln_engine.SeverityConverter = mock_converter
        mock_get_module.return_value = mock_vuln_engine

        result = SeverityConverter.ubuntu_priority_to_severity("medium")

        assert result == "MEDIUM"

    @patch("backend.vulnerability.cve_fetchers._get_module")
    def test_ubuntu_priority_to_severity_no_module(self, mock_get_module):
        """Test ubuntu_priority_to_severity without module."""
        mock_get_module.return_value = None

        with pytest.raises(CveRefreshError):
            SeverityConverter.ubuntu_priority_to_severity("medium")

    @patch("backend.vulnerability.cve_fetchers._get_module")
    def test_debian_urgency_to_severity_success(self, mock_get_module):
        """Test debian_urgency_to_severity with module available."""
        mock_converter = MagicMock()
        mock_converter.debian_urgency_to_severity.return_value = "LOW"
        mock_vuln_engine = MagicMock()
        mock_vuln_engine.SeverityConverter = mock_converter
        mock_get_module.return_value = mock_vuln_engine

        result = SeverityConverter.debian_urgency_to_severity("low")

        assert result == "LOW"

    @patch("backend.vulnerability.cve_fetchers._get_module")
    def test_debian_urgency_to_severity_no_module(self, mock_get_module):
        """Test debian_urgency_to_severity without module."""
        mock_get_module.return_value = None

        with pytest.raises(CveRefreshError):
            SeverityConverter.debian_urgency_to_severity("low")

    @patch("backend.vulnerability.cve_fetchers._get_module")
    def test_severity_converter_no_attribute(self, mock_get_module):
        """Test when module exists but lacks SeverityConverter."""
        mock_vuln_engine = MagicMock(spec=[])  # No SeverityConverter attribute
        mock_get_module.return_value = mock_vuln_engine

        with pytest.raises(CveRefreshError):
            SeverityConverter.cvss2_to_severity(7.5)


class TestCveFetchers:
    """Tests for CveFetchers class."""

    @patch("backend.vulnerability.cve_fetchers._get_module")
    @pytest.mark.asyncio
    async def test_fetch_nvd_data_success(self, mock_get_module):
        """Test fetch_nvd_data with module available."""
        mock_cve_service = MagicMock()
        mock_cve_service.fetch_nvd_data = AsyncMock(return_value={"cves_added": 100})
        mock_vuln_engine = MagicMock()
        mock_vuln_engine._cve_refresh_service = mock_cve_service
        mock_get_module.return_value = mock_vuln_engine

        fetcher = CveFetchers()
        mock_db = MagicMock()
        result = await fetcher.fetch_nvd_data(mock_db, api_key="test-key")

        assert result["cves_added"] == 100

    @patch("backend.vulnerability.cve_fetchers._get_module")
    @pytest.mark.asyncio
    async def test_fetch_nvd_data_no_module(self, mock_get_module):
        """Test fetch_nvd_data without module."""
        mock_get_module.return_value = None

        fetcher = CveFetchers()
        mock_db = MagicMock()

        with pytest.raises(CveRefreshError) as exc_info:
            await fetcher.fetch_nvd_data(mock_db)

        assert "CVE fetching" in str(exc_info.value)

    @patch("backend.vulnerability.cve_fetchers._get_module")
    @pytest.mark.asyncio
    async def test_fetch_ubuntu_data_success(self, mock_get_module):
        """Test fetch_ubuntu_data with module available."""
        mock_cve_service = MagicMock()
        mock_cve_service.fetch_ubuntu_data = AsyncMock(return_value={"cves_added": 50})
        mock_vuln_engine = MagicMock()
        mock_vuln_engine._cve_refresh_service = mock_cve_service
        mock_get_module.return_value = mock_vuln_engine

        fetcher = CveFetchers()
        mock_db = MagicMock()
        result = await fetcher.fetch_ubuntu_data(mock_db)

        assert result["cves_added"] == 50

    @patch("backend.vulnerability.cve_fetchers._get_module")
    @pytest.mark.asyncio
    async def test_fetch_ubuntu_data_no_module(self, mock_get_module):
        """Test fetch_ubuntu_data without module."""
        mock_get_module.return_value = None

        fetcher = CveFetchers()
        mock_db = MagicMock()

        with pytest.raises(CveRefreshError):
            await fetcher.fetch_ubuntu_data(mock_db)

    @patch("backend.persistence.db.get_engine")
    @patch("backend.vulnerability.cve_fetchers._get_module")
    @pytest.mark.asyncio
    async def test_fetch_debian_data_success(self, mock_get_module, mock_get_engine):
        """Test fetch_debian_data with module available."""
        mock_cve_service = MagicMock()
        mock_cve_service.fetch_debian_data = AsyncMock(return_value={"cves_added": 75})
        mock_vuln_engine = MagicMock()
        mock_vuln_engine._cve_refresh_service = mock_cve_service
        mock_get_module.return_value = mock_vuln_engine

        mock_engine = MagicMock()
        mock_get_engine.return_value = mock_engine

        fetcher = CveFetchers()
        mock_db = MagicMock()
        result = await fetcher.fetch_debian_data(mock_db)

        assert result["cves_added"] == 75

    @patch("backend.vulnerability.cve_fetchers._get_module")
    @pytest.mark.asyncio
    async def test_fetch_debian_data_no_module(self, mock_get_module):
        """Test fetch_debian_data without module."""
        mock_get_module.return_value = None

        fetcher = CveFetchers()
        mock_db = MagicMock()

        with pytest.raises(CveRefreshError):
            await fetcher.fetch_debian_data(mock_db)

    @patch("backend.vulnerability.cve_fetchers._get_module")
    @pytest.mark.asyncio
    async def test_fetch_redhat_data_success(self, mock_get_module):
        """Test fetch_redhat_data with module available."""
        mock_cve_service = MagicMock()
        mock_cve_service.fetch_redhat_data = AsyncMock(return_value={"cves_added": 60})
        mock_vuln_engine = MagicMock()
        mock_vuln_engine._cve_refresh_service = mock_cve_service
        mock_get_module.return_value = mock_vuln_engine

        fetcher = CveFetchers()
        mock_db = MagicMock()
        result = await fetcher.fetch_redhat_data(mock_db)

        assert result["cves_added"] == 60

    @patch("backend.vulnerability.cve_fetchers._get_module")
    @pytest.mark.asyncio
    async def test_fetch_redhat_data_no_module(self, mock_get_module):
        """Test fetch_redhat_data without module."""
        mock_get_module.return_value = None

        fetcher = CveFetchers()
        mock_db = MagicMock()

        with pytest.raises(CveRefreshError):
            await fetcher.fetch_redhat_data(mock_db)

    @patch("backend.vulnerability.cve_fetchers._get_module")
    @pytest.mark.asyncio
    async def test_fetch_microsoft_data_success(self, mock_get_module):
        """Test fetch_microsoft_data with module available."""
        mock_cve_service = MagicMock()
        mock_cve_service.fetch_microsoft_data = AsyncMock(
            return_value={"cves_added": 40}
        )
        mock_vuln_engine = MagicMock()
        mock_vuln_engine._cve_refresh_service = mock_cve_service
        mock_get_module.return_value = mock_vuln_engine

        fetcher = CveFetchers()
        mock_db = MagicMock()
        result = await fetcher.fetch_microsoft_data(mock_db)

        assert result["cves_added"] == 40

    @patch("backend.vulnerability.cve_fetchers._get_module")
    @pytest.mark.asyncio
    async def test_fetch_microsoft_data_no_module(self, mock_get_module):
        """Test fetch_microsoft_data without module."""
        mock_get_module.return_value = None

        fetcher = CveFetchers()
        mock_db = MagicMock()

        with pytest.raises(CveRefreshError):
            await fetcher.fetch_microsoft_data(mock_db)

    @patch("backend.vulnerability.cve_fetchers._get_module")
    def test_fetch_freebsd_data_success(self, mock_get_module):
        """Test fetch_freebsd_data with module available."""
        mock_cve_service = MagicMock()
        mock_cve_service.fetch_freebsd_data.return_value = {"cves_added": 25}
        mock_vuln_engine = MagicMock()
        mock_vuln_engine._cve_refresh_service = mock_cve_service
        mock_get_module.return_value = mock_vuln_engine

        fetcher = CveFetchers()
        mock_db = MagicMock()
        result = fetcher.fetch_freebsd_data(mock_db)

        assert result["cves_added"] == 25

    @patch("backend.vulnerability.cve_fetchers._get_module")
    def test_fetch_freebsd_data_no_module(self, mock_get_module):
        """Test fetch_freebsd_data without module."""
        mock_get_module.return_value = None

        fetcher = CveFetchers()
        mock_db = MagicMock()

        with pytest.raises(CveRefreshError):
            fetcher.fetch_freebsd_data(mock_db)

    @patch("backend.vulnerability.cve_fetchers._get_module")
    @pytest.mark.asyncio
    async def test_fetcher_no_cve_service_attribute(self, mock_get_module):
        """Test when module exists but lacks _cve_refresh_service."""
        mock_vuln_engine = MagicMock(spec=[])  # No _cve_refresh_service attribute
        mock_get_module.return_value = mock_vuln_engine

        fetcher = CveFetchers()
        mock_db = MagicMock()

        with pytest.raises(CveRefreshError):
            await fetcher.fetch_nvd_data(mock_db)
