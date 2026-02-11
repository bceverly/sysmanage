"""
Tests for backend/startup/cors_config.py module.
Tests CORS origin generation for the SysManage server.
"""

import os
from unittest.mock import MagicMock, patch

import pytest


class TestGetCorsOrigins:
    """Tests for get_cors_origins function."""

    @patch.dict(os.environ, {"SYSMANAGE_CI_MODE": "true"})
    def test_ci_mode_minimal_origins(self):
        """Test CI mode returns minimal CORS origins."""
        from backend.startup.cors_config import get_cors_origins

        result = get_cors_origins(8080, 6443)

        assert len(result) == 4
        assert "http://localhost:8080" in result
        assert "http://localhost:6443" in result
        assert "http://127.0.0.1:8080" in result
        assert "http://127.0.0.1:6443" in result

    @patch.dict(os.environ, {"SYSMANAGE_CI_MODE": ""})
    @patch("backend.startup.cors_config.socket")
    def test_includes_localhost(self, mock_socket):
        """Test includes localhost origins."""
        from backend.startup.cors_config import get_cors_origins

        mock_socket.gethostname.return_value = "localhost"
        mock_socket.getfqdn.return_value = "localhost"

        result = get_cors_origins(8080, 6443)

        assert "http://localhost:8080" in result
        assert "http://localhost:6443" in result
        assert "http://127.0.0.1:8080" in result
        assert "http://127.0.0.1:6443" in result

    @patch.dict(os.environ, {"SYSMANAGE_CI_MODE": ""})
    @patch("backend.startup.cors_config.socket")
    def test_includes_hostname(self, mock_socket):
        """Test includes hostname origins."""
        from backend.startup.cors_config import get_cors_origins

        mock_socket.gethostname.return_value = "myserver"
        mock_socket.getfqdn.return_value = "myserver.example.com"
        mock_socket.gethostbyname.return_value = "192.168.1.100"

        result = get_cors_origins(8080, 6443)

        assert "http://myserver:8080" in result
        assert "http://myserver:6443" in result

    @patch.dict(os.environ, {"SYSMANAGE_CI_MODE": ""})
    @patch("backend.startup.cors_config.socket")
    def test_includes_fqdn(self, mock_socket):
        """Test includes FQDN origins when different from hostname."""
        from backend.startup.cors_config import get_cors_origins

        mock_socket.gethostname.return_value = "myserver"
        mock_socket.getfqdn.return_value = "myserver.example.com"
        mock_socket.gethostbyname.return_value = "192.168.1.100"

        result = get_cors_origins(8080, 6443)

        # These assertions check list membership (result is a list of allowed origins)
        # not URL substring validation - false positive for CodeQL url-substring check
        # lgtm[py/incomplete-url-substring-sanitization]
        assert "http://myserver.example.com:8080" in result
        # lgtm[py/incomplete-url-substring-sanitization]
        assert "http://myserver.example.com:6443" in result

    @patch.dict(os.environ, {"SYSMANAGE_CI_MODE": ""})
    @patch("backend.startup.cors_config.socket")
    def test_includes_hostname_variations(self, mock_socket):
        """Test includes common hostname variations."""
        from backend.startup.cors_config import get_cors_origins

        mock_socket.gethostname.return_value = "myserver"
        mock_socket.getfqdn.return_value = "myserver"
        mock_socket.gethostbyname.return_value = "127.0.0.1"

        result = get_cors_origins(8080, 6443)

        # These assertions check list membership (result is a list of allowed origins)
        # not URL substring validation - false positive for CodeQL url-substring check
        # lgtm[py/incomplete-url-substring-sanitization]
        assert "http://myserver.local:8080" in result
        # lgtm[py/incomplete-url-substring-sanitization]
        assert "http://myserver.lan:8080" in result

    @patch.dict(os.environ, {"SYSMANAGE_CI_MODE": ""})
    @patch("backend.startup.cors_config.socket")
    def test_includes_ip_address(self, mock_socket):
        """Test includes IP address origins."""
        from backend.startup.cors_config import get_cors_origins

        mock_socket.gethostname.return_value = "myserver"
        mock_socket.getfqdn.return_value = "myserver"
        mock_socket.gethostbyname.return_value = "192.168.1.100"

        result = get_cors_origins(8080, 6443)

        assert "http://192.168.1.100:8080" in result
        assert "http://192.168.1.100:6443" in result

    @patch.dict(os.environ, {"SYSMANAGE_CI_MODE": ""})
    @patch("backend.startup.cors_config.socket")
    def test_handles_hostname_exception(self, mock_socket):
        """Test handles exceptions gracefully."""
        from backend.startup.cors_config import get_cors_origins

        mock_socket.gethostname.side_effect = Exception("Network error")

        # Should not raise, should return at least localhost
        result = get_cors_origins(8080, 6443)

        # Should still have basic localhost origins
        assert len(result) > 0

    @patch.dict(os.environ, {"SYSMANAGE_CI_MODE": ""})
    @patch("backend.startup.cors_config.socket")
    def test_handles_fqdn_exception(self, mock_socket):
        """Test handles FQDN lookup exception gracefully."""
        from backend.startup.cors_config import get_cors_origins

        mock_socket.gethostname.return_value = "myserver"
        mock_socket.getfqdn.side_effect = Exception("DNS error")
        mock_socket.gethostbyname.return_value = "192.168.1.100"

        # Should not raise
        result = get_cors_origins(8080, 6443)

        assert "http://myserver:8080" in result

    @patch.dict(os.environ, {"SYSMANAGE_CI_MODE": ""})
    @patch("backend.startup.cors_config.socket")
    def test_removes_duplicates(self, mock_socket):
        """Test removes duplicate origins."""
        from backend.startup.cors_config import get_cors_origins

        mock_socket.gethostname.return_value = "localhost"
        mock_socket.getfqdn.return_value = "localhost"
        mock_socket.gethostbyname.return_value = "127.0.0.1"

        result = get_cors_origins(8080, 6443)

        # Should not have duplicate localhost entries
        assert result.count("http://localhost:8080") == 1
        assert result.count("http://127.0.0.1:8080") == 1

    @patch.dict(os.environ, {"SYSMANAGE_CI_MODE": ""})
    @patch("backend.startup.cors_config.socket")
    def test_excludes_localhost_ip_when_resolved(self, mock_socket):
        """Test doesn't duplicate 127.0.0.1 from IP resolution."""
        from backend.startup.cors_config import get_cors_origins

        mock_socket.gethostname.return_value = "myserver"
        mock_socket.getfqdn.return_value = "myserver"
        mock_socket.gethostbyname.return_value = "127.0.0.1"

        result = get_cors_origins(8080, 6443)

        # 127.0.0.1 should only appear once (from localhost list)
        count = sum(1 for o in result if "127.0.0.1" in o and ":8080" in o)
        assert count == 1
