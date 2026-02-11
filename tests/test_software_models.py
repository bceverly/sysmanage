"""
Tests for backend/persistence/models/software.py module.
Tests all software-related models and the CrossPlatformDateTime type.
"""

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest


class TestCrossPlatformDateTime:
    """Tests for CrossPlatformDateTime type decorator."""

    def test_load_dialect_impl_postgresql(self):
        """Test load_dialect_impl returns timezone-aware for PostgreSQL."""
        from backend.persistence.models.software import CrossPlatformDateTime

        cpdt = CrossPlatformDateTime()
        mock_dialect = MagicMock()
        mock_dialect.name = "postgresql"
        mock_dialect.type_descriptor = MagicMock(return_value="pg_datetime")

        result = cpdt.load_dialect_impl(mock_dialect)

        assert result == "pg_datetime"
        mock_dialect.type_descriptor.assert_called_once()

    def test_load_dialect_impl_sqlite(self):
        """Test load_dialect_impl returns plain DateTime for SQLite."""
        from backend.persistence.models.software import CrossPlatformDateTime

        cpdt = CrossPlatformDateTime()
        mock_dialect = MagicMock()
        mock_dialect.name = "sqlite"
        mock_dialect.type_descriptor = MagicMock(return_value="sqlite_datetime")

        result = cpdt.load_dialect_impl(mock_dialect)

        assert result == "sqlite_datetime"
        mock_dialect.type_descriptor.assert_called_once()

    def test_process_bind_param_none(self):
        """Test process_bind_param returns None for None input."""
        from backend.persistence.models.software import CrossPlatformDateTime

        cpdt = CrossPlatformDateTime()
        mock_dialect = MagicMock()
        mock_dialect.name = "sqlite"

        result = cpdt.process_bind_param(None, mock_dialect)

        assert result is None

    def test_process_bind_param_non_datetime(self):
        """Test process_bind_param returns value unchanged for non-datetime."""
        from backend.persistence.models.software import CrossPlatformDateTime

        cpdt = CrossPlatformDateTime()
        mock_dialect = MagicMock()
        mock_dialect.name = "sqlite"

        result = cpdt.process_bind_param("not a datetime", mock_dialect)

        assert result == "not a datetime"

    def test_process_bind_param_sqlite_timezone_aware(self):
        """Test process_bind_param converts timezone-aware to naive for SQLite."""
        from backend.persistence.models.software import CrossPlatformDateTime

        cpdt = CrossPlatformDateTime()
        mock_dialect = MagicMock()
        mock_dialect.name = "sqlite"

        aware_dt = datetime(2024, 1, 15, 12, 30, 0, tzinfo=timezone.utc)
        result = cpdt.process_bind_param(aware_dt, mock_dialect)

        # Should be naive (no tzinfo)
        assert result.tzinfo is None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 12
        assert result.minute == 30

    def test_process_bind_param_sqlite_naive(self):
        """Test process_bind_param returns naive datetime unchanged for SQLite."""
        from backend.persistence.models.software import CrossPlatformDateTime

        cpdt = CrossPlatformDateTime()
        mock_dialect = MagicMock()
        mock_dialect.name = "sqlite"

        naive_dt = datetime(2024, 1, 15, 12, 30, 0)
        result = cpdt.process_bind_param(naive_dt, mock_dialect)

        assert result == naive_dt
        assert result.tzinfo is None

    def test_process_bind_param_postgresql(self):
        """Test process_bind_param keeps datetime as-is for PostgreSQL."""
        from backend.persistence.models.software import CrossPlatformDateTime

        cpdt = CrossPlatformDateTime()
        mock_dialect = MagicMock()
        mock_dialect.name = "postgresql"

        aware_dt = datetime(2024, 1, 15, 12, 30, 0, tzinfo=timezone.utc)
        result = cpdt.process_bind_param(aware_dt, mock_dialect)

        assert result == aware_dt
        assert result.tzinfo == timezone.utc

    def test_process_result_value(self):
        """Test process_result_value returns value unchanged."""
        from backend.persistence.models.software import CrossPlatformDateTime

        cpdt = CrossPlatformDateTime()
        mock_dialect = MagicMock()
        test_value = datetime(2024, 1, 15)

        result = cpdt.process_result_value(test_value, mock_dialect)

        assert result == test_value

    def test_process_literal_param(self):
        """Test process_literal_param returns repr of value."""
        from backend.persistence.models.software import CrossPlatformDateTime

        cpdt = CrossPlatformDateTime()
        mock_dialect = MagicMock()
        test_value = datetime(2024, 1, 15, 12, 30, 0)

        result = cpdt.process_literal_param(test_value, mock_dialect)

        assert result == repr(test_value)

    def test_python_type_property(self):
        """Test python_type property returns datetime."""
        from backend.persistence.models.software import CrossPlatformDateTime

        cpdt = CrossPlatformDateTime()

        assert cpdt.python_type is datetime


class TestSoftwarePackageModel:
    """Tests for SoftwarePackage model."""

    def test_table_name(self):
        """Test SoftwarePackage table name."""
        from backend.persistence.models.software import SoftwarePackage

        assert SoftwarePackage.__tablename__ == "software_package"

    def test_columns_exist(self):
        """Test SoftwarePackage has expected columns."""
        from backend.persistence.models.software import SoftwarePackage

        assert hasattr(SoftwarePackage, "id")
        assert hasattr(SoftwarePackage, "host_id")
        assert hasattr(SoftwarePackage, "package_name")
        assert hasattr(SoftwarePackage, "package_version")
        assert hasattr(SoftwarePackage, "package_description")
        assert hasattr(SoftwarePackage, "package_manager")
        assert hasattr(SoftwarePackage, "architecture")
        assert hasattr(SoftwarePackage, "size_bytes")
        assert hasattr(SoftwarePackage, "vendor")
        assert hasattr(SoftwarePackage, "category")
        assert hasattr(SoftwarePackage, "license")
        assert hasattr(SoftwarePackage, "install_path")
        assert hasattr(SoftwarePackage, "install_date")
        assert hasattr(SoftwarePackage, "is_system_package")
        assert hasattr(SoftwarePackage, "created_at")
        assert hasattr(SoftwarePackage, "updated_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.software import SoftwarePackage

        pkg = SoftwarePackage()
        pkg.id = uuid.uuid4()
        pkg.host_id = uuid.uuid4()
        pkg.package_name = "nginx"
        pkg.package_version = "1.18.0"

        repr_str = repr(pkg)

        assert "SoftwarePackage" in repr_str
        assert "nginx" in repr_str
        assert "1.18.0" in repr_str


class TestPackageUpdateModel:
    """Tests for PackageUpdate model."""

    def test_table_name(self):
        """Test PackageUpdate table name."""
        from backend.persistence.models.software import PackageUpdate

        assert PackageUpdate.__tablename__ == "package_update"

    def test_columns_exist(self):
        """Test PackageUpdate has expected columns."""
        from backend.persistence.models.software import PackageUpdate

        assert hasattr(PackageUpdate, "id")
        assert hasattr(PackageUpdate, "host_id")
        assert hasattr(PackageUpdate, "package_name")
        assert hasattr(PackageUpdate, "bundle_id")
        assert hasattr(PackageUpdate, "current_version")
        assert hasattr(PackageUpdate, "available_version")
        assert hasattr(PackageUpdate, "package_manager")
        assert hasattr(PackageUpdate, "update_type")
        assert hasattr(PackageUpdate, "priority")
        assert hasattr(PackageUpdate, "requires_reboot")
        assert hasattr(PackageUpdate, "status")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.software import PackageUpdate

        update = PackageUpdate()
        update.id = uuid.uuid4()
        update.host_id = uuid.uuid4()
        update.package_name = "openssl"
        update.current_version = "1.1.1"
        update.available_version = "1.1.2"

        repr_str = repr(update)

        assert "PackageUpdate" in repr_str
        assert "openssl" in repr_str
        assert "1.1.1" in repr_str
        assert "1.1.2" in repr_str


class TestAvailablePackageModel:
    """Tests for AvailablePackage model."""

    def test_table_name(self):
        """Test AvailablePackage table name."""
        from backend.persistence.models.software import AvailablePackage

        assert AvailablePackage.__tablename__ == "available_packages"

    def test_columns_exist(self):
        """Test AvailablePackage has expected columns."""
        from backend.persistence.models.software import AvailablePackage

        assert hasattr(AvailablePackage, "id")
        assert hasattr(AvailablePackage, "package_name")
        assert hasattr(AvailablePackage, "package_version")
        assert hasattr(AvailablePackage, "package_description")
        assert hasattr(AvailablePackage, "package_manager")
        assert hasattr(AvailablePackage, "os_name")
        assert hasattr(AvailablePackage, "os_version")
        assert hasattr(AvailablePackage, "last_updated")
        assert hasattr(AvailablePackage, "created_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.software import AvailablePackage

        pkg = AvailablePackage()
        pkg.id = uuid.uuid4()
        pkg.package_name = "vim"
        pkg.package_version = "8.2"
        pkg.os_name = "Ubuntu"
        pkg.os_version = "22.04"

        repr_str = repr(pkg)

        assert "AvailablePackage" in repr_str
        assert "vim" in repr_str
        assert "8.2" in repr_str
        assert "Ubuntu" in repr_str
        assert "22.04" in repr_str


class TestSoftwareInstallationLogModel:
    """Tests for SoftwareInstallationLog model."""

    def test_table_name(self):
        """Test SoftwareInstallationLog table name."""
        from backend.persistence.models.software import SoftwareInstallationLog

        assert SoftwareInstallationLog.__tablename__ == "software_installation_log"

    def test_columns_exist(self):
        """Test SoftwareInstallationLog has expected columns."""
        from backend.persistence.models.software import SoftwareInstallationLog

        assert hasattr(SoftwareInstallationLog, "id")
        assert hasattr(SoftwareInstallationLog, "host_id")
        assert hasattr(SoftwareInstallationLog, "package_name")
        assert hasattr(SoftwareInstallationLog, "package_manager")
        assert hasattr(SoftwareInstallationLog, "requested_version")
        assert hasattr(SoftwareInstallationLog, "requested_by")
        assert hasattr(SoftwareInstallationLog, "installation_id")
        assert hasattr(SoftwareInstallationLog, "status")
        assert hasattr(SoftwareInstallationLog, "requested_at")
        assert hasattr(SoftwareInstallationLog, "queued_at")
        assert hasattr(SoftwareInstallationLog, "started_at")
        assert hasattr(SoftwareInstallationLog, "completed_at")
        assert hasattr(SoftwareInstallationLog, "installed_version")
        assert hasattr(SoftwareInstallationLog, "success")
        assert hasattr(SoftwareInstallationLog, "error_message")
        assert hasattr(SoftwareInstallationLog, "installation_log")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.software import SoftwareInstallationLog

        log = SoftwareInstallationLog()
        log.id = uuid.uuid4()
        log.host_id = uuid.uuid4()
        log.installation_id = "abc-123-def"
        log.package_name = "htop"
        log.status = "completed"

        repr_str = repr(log)

        assert "SoftwareInstallationLog" in repr_str
        assert "abc-123-def" in repr_str
        assert "htop" in repr_str
        assert "completed" in repr_str


class TestInstallationRequestModel:
    """Tests for InstallationRequest model."""

    def test_table_name(self):
        """Test InstallationRequest table name."""
        from backend.persistence.models.software import InstallationRequest

        assert InstallationRequest.__tablename__ == "installation_requests"

    def test_columns_exist(self):
        """Test InstallationRequest has expected columns."""
        from backend.persistence.models.software import InstallationRequest

        assert hasattr(InstallationRequest, "id")
        assert hasattr(InstallationRequest, "host_id")
        assert hasattr(InstallationRequest, "requested_by")
        assert hasattr(InstallationRequest, "requested_at")
        assert hasattr(InstallationRequest, "completed_at")
        assert hasattr(InstallationRequest, "status")
        assert hasattr(InstallationRequest, "operation_type")
        assert hasattr(InstallationRequest, "result_log")
        assert hasattr(InstallationRequest, "created_at")
        assert hasattr(InstallationRequest, "updated_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.software import InstallationRequest

        req = InstallationRequest()
        req.id = uuid.uuid4()
        req.host_id = uuid.uuid4()
        req.status = "pending"
        req.requested_by = "admin"

        repr_str = repr(req)

        assert "InstallationRequest" in repr_str
        assert "pending" in repr_str
        assert "admin" in repr_str


class TestInstallationPackageModel:
    """Tests for InstallationPackage model."""

    def test_table_name(self):
        """Test InstallationPackage table name."""
        from backend.persistence.models.software import InstallationPackage

        assert InstallationPackage.__tablename__ == "installation_packages"

    def test_columns_exist(self):
        """Test InstallationPackage has expected columns."""
        from backend.persistence.models.software import InstallationPackage

        assert hasattr(InstallationPackage, "id")
        assert hasattr(InstallationPackage, "installation_request_id")
        assert hasattr(InstallationPackage, "package_name")
        assert hasattr(InstallationPackage, "package_manager")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.software import InstallationPackage

        pkg = InstallationPackage()
        pkg.id = uuid.uuid4()
        pkg.installation_request_id = uuid.uuid4()
        pkg.package_name = "git"

        repr_str = repr(pkg)

        assert "InstallationPackage" in repr_str
        assert "git" in repr_str


class TestThirdPartyRepositoryModel:
    """Tests for ThirdPartyRepository model."""

    def test_table_name(self):
        """Test ThirdPartyRepository table name."""
        from backend.persistence.models.software import ThirdPartyRepository

        assert ThirdPartyRepository.__tablename__ == "third_party_repository"

    def test_columns_exist(self):
        """Test ThirdPartyRepository has expected columns."""
        from backend.persistence.models.software import ThirdPartyRepository

        assert hasattr(ThirdPartyRepository, "id")
        assert hasattr(ThirdPartyRepository, "host_id")
        assert hasattr(ThirdPartyRepository, "name")
        assert hasattr(ThirdPartyRepository, "type")
        assert hasattr(ThirdPartyRepository, "url")
        assert hasattr(ThirdPartyRepository, "enabled")
        assert hasattr(ThirdPartyRepository, "file_path")
        assert hasattr(ThirdPartyRepository, "last_updated")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.software import ThirdPartyRepository

        repo = ThirdPartyRepository()
        repo.id = uuid.uuid4()
        repo.host_id = uuid.uuid4()
        repo.name = "docker-ce"
        repo.type = "ppa"
        repo.enabled = True

        repr_str = repr(repo)

        assert "ThirdPartyRepository" in repr_str
        assert "docker-ce" in repr_str
        assert "ppa" in repr_str
        assert "True" in repr_str


class TestAntivirusDefaultModel:
    """Tests for AntivirusDefault model."""

    def test_table_name(self):
        """Test AntivirusDefault table name."""
        from backend.persistence.models.software import AntivirusDefault

        assert AntivirusDefault.__tablename__ == "antivirus_default"

    def test_columns_exist(self):
        """Test AntivirusDefault has expected columns."""
        from backend.persistence.models.software import AntivirusDefault

        assert hasattr(AntivirusDefault, "id")
        assert hasattr(AntivirusDefault, "os_name")
        assert hasattr(AntivirusDefault, "antivirus_package")
        assert hasattr(AntivirusDefault, "created_at")
        assert hasattr(AntivirusDefault, "updated_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.software import AntivirusDefault

        default = AntivirusDefault()
        default.id = uuid.uuid4()
        default.os_name = "Ubuntu"
        default.antivirus_package = "clamav"

        repr_str = repr(default)

        assert "AntivirusDefault" in repr_str
        assert "Ubuntu" in repr_str
        assert "clamav" in repr_str


class TestAntivirusStatusModel:
    """Tests for AntivirusStatus model."""

    def test_table_name(self):
        """Test AntivirusStatus table name."""
        from backend.persistence.models.software import AntivirusStatus

        assert AntivirusStatus.__tablename__ == "antivirus_status"

    def test_columns_exist(self):
        """Test AntivirusStatus has expected columns."""
        from backend.persistence.models.software import AntivirusStatus

        assert hasattr(AntivirusStatus, "id")
        assert hasattr(AntivirusStatus, "host_id")
        assert hasattr(AntivirusStatus, "software_name")
        assert hasattr(AntivirusStatus, "install_path")
        assert hasattr(AntivirusStatus, "version")
        assert hasattr(AntivirusStatus, "enabled")
        assert hasattr(AntivirusStatus, "last_updated")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.software import AntivirusStatus

        status = AntivirusStatus()
        status.id = uuid.uuid4()
        status.host_id = uuid.uuid4()
        status.software_name = "ClamAV"
        status.enabled = True

        repr_str = repr(status)

        assert "AntivirusStatus" in repr_str
        assert "ClamAV" in repr_str
        assert "True" in repr_str


class TestCommercialAntivirusStatusModel:
    """Tests for CommercialAntivirusStatus model."""

    def test_table_name(self):
        """Test CommercialAntivirusStatus table name."""
        from backend.persistence.models.software import CommercialAntivirusStatus

        assert CommercialAntivirusStatus.__tablename__ == "commercial_antivirus_status"

    def test_columns_exist(self):
        """Test CommercialAntivirusStatus has expected columns."""
        from backend.persistence.models.software import CommercialAntivirusStatus

        assert hasattr(CommercialAntivirusStatus, "id")
        assert hasattr(CommercialAntivirusStatus, "host_id")
        assert hasattr(CommercialAntivirusStatus, "product_name")
        assert hasattr(CommercialAntivirusStatus, "product_version")
        assert hasattr(CommercialAntivirusStatus, "service_enabled")
        assert hasattr(CommercialAntivirusStatus, "antispyware_enabled")
        assert hasattr(CommercialAntivirusStatus, "antivirus_enabled")
        assert hasattr(CommercialAntivirusStatus, "realtime_protection_enabled")
        assert hasattr(CommercialAntivirusStatus, "full_scan_age")
        assert hasattr(CommercialAntivirusStatus, "quick_scan_age")
        assert hasattr(CommercialAntivirusStatus, "full_scan_end_time")
        assert hasattr(CommercialAntivirusStatus, "quick_scan_end_time")
        assert hasattr(CommercialAntivirusStatus, "signature_last_updated")
        assert hasattr(CommercialAntivirusStatus, "signature_version")
        assert hasattr(CommercialAntivirusStatus, "tamper_protection_enabled")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.software import CommercialAntivirusStatus

        status = CommercialAntivirusStatus()
        status.id = uuid.uuid4()
        status.host_id = uuid.uuid4()
        status.product_name = "Microsoft Defender"
        status.antivirus_enabled = True

        repr_str = repr(status)

        assert "CommercialAntivirusStatus" in repr_str
        assert "Microsoft Defender" in repr_str
        assert "True" in repr_str


class TestFirewallStatusModel:
    """Tests for FirewallStatus model."""

    def test_table_name(self):
        """Test FirewallStatus table name."""
        from backend.persistence.models.software import FirewallStatus

        assert FirewallStatus.__tablename__ == "firewall_status"

    def test_columns_exist(self):
        """Test FirewallStatus has expected columns."""
        from backend.persistence.models.software import FirewallStatus

        assert hasattr(FirewallStatus, "id")
        assert hasattr(FirewallStatus, "host_id")
        assert hasattr(FirewallStatus, "firewall_name")
        assert hasattr(FirewallStatus, "enabled")
        assert hasattr(FirewallStatus, "tcp_open_ports")
        assert hasattr(FirewallStatus, "udp_open_ports")
        assert hasattr(FirewallStatus, "ipv4_ports")
        assert hasattr(FirewallStatus, "ipv6_ports")
        assert hasattr(FirewallStatus, "last_updated")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.software import FirewallStatus

        status = FirewallStatus()
        status.id = uuid.uuid4()
        status.host_id = uuid.uuid4()
        status.firewall_name = "ufw"
        status.enabled = True

        repr_str = repr(status)

        assert "FirewallStatus" in repr_str
        assert "ufw" in repr_str
        assert "True" in repr_str


class TestDefaultRepositoryModel:
    """Tests for DefaultRepository model."""

    def test_table_name(self):
        """Test DefaultRepository table name."""
        from backend.persistence.models.software import DefaultRepository

        assert DefaultRepository.__tablename__ == "default_repository"

    def test_columns_exist(self):
        """Test DefaultRepository has expected columns."""
        from backend.persistence.models.software import DefaultRepository

        assert hasattr(DefaultRepository, "id")
        assert hasattr(DefaultRepository, "os_name")
        assert hasattr(DefaultRepository, "package_manager")
        assert hasattr(DefaultRepository, "repository_url")
        assert hasattr(DefaultRepository, "created_at")
        assert hasattr(DefaultRepository, "created_by")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.software import DefaultRepository

        repo = DefaultRepository()
        repo.id = uuid.uuid4()
        repo.os_name = "Fedora"
        repo.package_manager = "dnf"
        repo.repository_url = "https://download.docker.com/linux/fedora"

        repr_str = repr(repo)

        assert "DefaultRepository" in repr_str
        assert "Fedora" in repr_str
        assert "dnf" in repr_str
        assert "docker.com" in repr_str


class TestEnabledPackageManagerModel:
    """Tests for EnabledPackageManager model."""

    def test_table_name(self):
        """Test EnabledPackageManager table name."""
        from backend.persistence.models.software import EnabledPackageManager

        assert EnabledPackageManager.__tablename__ == "enabled_package_manager"

    def test_columns_exist(self):
        """Test EnabledPackageManager has expected columns."""
        from backend.persistence.models.software import EnabledPackageManager

        assert hasattr(EnabledPackageManager, "id")
        assert hasattr(EnabledPackageManager, "os_name")
        assert hasattr(EnabledPackageManager, "package_manager")
        assert hasattr(EnabledPackageManager, "created_at")
        assert hasattr(EnabledPackageManager, "created_by")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.software import EnabledPackageManager

        pm = EnabledPackageManager()
        pm.id = uuid.uuid4()
        pm.os_name = "Ubuntu"
        pm.package_manager = "snap"

        repr_str = repr(pm)

        assert "EnabledPackageManager" in repr_str
        assert "Ubuntu" in repr_str
        assert "snap" in repr_str


class TestFirewallRoleModel:
    """Tests for FirewallRole model."""

    def test_table_name(self):
        """Test FirewallRole table name."""
        from backend.persistence.models.software import FirewallRole

        assert FirewallRole.__tablename__ == "firewall_role"

    def test_columns_exist(self):
        """Test FirewallRole has expected columns."""
        from backend.persistence.models.software import FirewallRole

        assert hasattr(FirewallRole, "id")
        assert hasattr(FirewallRole, "name")
        assert hasattr(FirewallRole, "created_at")
        assert hasattr(FirewallRole, "created_by")
        assert hasattr(FirewallRole, "updated_at")
        assert hasattr(FirewallRole, "updated_by")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.software import FirewallRole

        role = FirewallRole()
        role.id = uuid.uuid4()
        role.name = "web-server"

        repr_str = repr(role)

        assert "FirewallRole" in repr_str
        assert "web-server" in repr_str


class TestFirewallRoleOpenPortModel:
    """Tests for FirewallRoleOpenPort model."""

    def test_table_name(self):
        """Test FirewallRoleOpenPort table name."""
        from backend.persistence.models.software import FirewallRoleOpenPort

        assert FirewallRoleOpenPort.__tablename__ == "firewall_role_open_port"

    def test_columns_exist(self):
        """Test FirewallRoleOpenPort has expected columns."""
        from backend.persistence.models.software import FirewallRoleOpenPort

        assert hasattr(FirewallRoleOpenPort, "id")
        assert hasattr(FirewallRoleOpenPort, "firewall_role_id")
        assert hasattr(FirewallRoleOpenPort, "port_number")
        assert hasattr(FirewallRoleOpenPort, "tcp")
        assert hasattr(FirewallRoleOpenPort, "udp")
        assert hasattr(FirewallRoleOpenPort, "ipv4")
        assert hasattr(FirewallRoleOpenPort, "ipv6")

    def test_repr_tcp_only(self):
        """Test __repr__ with TCP only."""
        from backend.persistence.models.software import FirewallRoleOpenPort

        port = FirewallRoleOpenPort()
        port.id = uuid.uuid4()
        port.firewall_role_id = uuid.uuid4()
        port.port_number = 443
        port.tcp = True
        port.udp = False
        port.ipv4 = True
        port.ipv6 = True

        repr_str = repr(port)

        assert "FirewallRoleOpenPort" in repr_str
        assert "443" in repr_str
        assert "TCP" in repr_str
        assert "UDP" not in repr_str
        assert "IPv4" in repr_str
        assert "IPv6" in repr_str

    def test_repr_udp_only(self):
        """Test __repr__ with UDP only."""
        from backend.persistence.models.software import FirewallRoleOpenPort

        port = FirewallRoleOpenPort()
        port.id = uuid.uuid4()
        port.firewall_role_id = uuid.uuid4()
        port.port_number = 53
        port.tcp = False
        port.udp = True
        port.ipv4 = True
        port.ipv6 = False

        repr_str = repr(port)

        assert "FirewallRoleOpenPort" in repr_str
        assert "53" in repr_str
        assert "UDP" in repr_str
        assert "TCP" not in repr_str
        assert "IPv4" in repr_str
        assert "IPv6" not in repr_str

    def test_repr_both_protocols(self):
        """Test __repr__ with both TCP and UDP."""
        from backend.persistence.models.software import FirewallRoleOpenPort

        port = FirewallRoleOpenPort()
        port.id = uuid.uuid4()
        port.firewall_role_id = uuid.uuid4()
        port.port_number = 53
        port.tcp = True
        port.udp = True
        port.ipv4 = True
        port.ipv6 = True

        repr_str = repr(port)

        assert "TCP" in repr_str
        assert "UDP" in repr_str
        assert "IPv4" in repr_str
        assert "IPv6" in repr_str


class TestHostFirewallRoleModel:
    """Tests for HostFirewallRole model."""

    def test_table_name(self):
        """Test HostFirewallRole table name."""
        from backend.persistence.models.software import HostFirewallRole

        assert HostFirewallRole.__tablename__ == "host_firewall_role"

    def test_columns_exist(self):
        """Test HostFirewallRole has expected columns."""
        from backend.persistence.models.software import HostFirewallRole

        assert hasattr(HostFirewallRole, "id")
        assert hasattr(HostFirewallRole, "host_id")
        assert hasattr(HostFirewallRole, "firewall_role_id")
        assert hasattr(HostFirewallRole, "created_at")
        assert hasattr(HostFirewallRole, "created_by")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.software import HostFirewallRole

        hfr = HostFirewallRole()
        hfr.id = uuid.uuid4()
        hfr.host_id = uuid.uuid4()
        hfr.firewall_role_id = uuid.uuid4()

        repr_str = repr(hfr)

        assert "HostFirewallRole" in repr_str
        assert str(hfr.host_id) in repr_str
        assert str(hfr.firewall_role_id) in repr_str


class TestSoftwareModuleConstants:
    """Tests for module constants."""

    def test_constants_exist(self):
        """Test module-level constants exist."""
        from backend.persistence.models.software import (
            HOST_ID_FK,
            CASCADE_DELETE_ORPHAN,
            SET_NULL_ACTION,
            USER_ID_FK,
        )

        assert HOST_ID_FK == "host.id"
        assert CASCADE_DELETE_ORPHAN == "all, delete-orphan"
        assert SET_NULL_ACTION == "SET NULL"
        assert USER_ID_FK == "user.id"
