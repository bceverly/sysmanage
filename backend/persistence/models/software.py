"""
Software management models for SysManage - packages, updates, and installations.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from backend.persistence.db import Base


class SoftwarePackage(Base):
    """
    This class holds the object mapping for the software_package table in the
    PostgreSQL database.
    """

    __tablename__ = "software_package"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    host_id = Column(
        BigInteger, ForeignKey("host.id", ondelete="CASCADE"), nullable=False
    )
    package_name = Column(String(255), nullable=False, index=True)
    package_version = Column(String(100), nullable=False)
    package_description = Column(Text, nullable=True)
    package_manager = Column(String(50), nullable=False)  # apt, yum, brew, etc.
    architecture = Column(String(50), nullable=True)
    size_bytes = Column(BigInteger, nullable=True)
    vendor = Column(String(255), nullable=True)
    category = Column(String(100), nullable=True)
    license = Column(String(255), nullable=True)
    install_path = Column(String(500), nullable=True)
    install_date = Column(DateTime(timezone=True), nullable=True)
    is_system_package = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Relationship back to Host
    host = relationship("Host", back_populates="software_packages")

    def __repr__(self):
        return f"<SoftwarePackage(id={self.id}, package_name='{self.package_name}', version='{self.package_version}', host_id={self.host_id})>"


class PackageUpdate(Base):
    """
    This class holds the object mapping for the package_update table in the
    PostgreSQL database. It tracks available updates for installed packages.
    """

    __tablename__ = "package_update"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    host_id = Column(
        BigInteger, ForeignKey("host.id", ondelete="CASCADE"), nullable=False
    )
    package_name = Column(String(255), nullable=False, index=True)
    current_version = Column(String(100), nullable=False)
    available_version = Column(String(100), nullable=False)
    package_manager = Column(String(50), nullable=False)
    update_type = Column(String(20), nullable=False)  # security, bugfix, enhancement
    priority = Column(String(20), nullable=True)  # low, medium, high, critical
    description = Column(Text, nullable=True)
    size_bytes = Column(BigInteger, nullable=True)
    requires_reboot = Column(Boolean, nullable=False, default=False)
    discovered_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Relationship back to Host
    host = relationship("Host", back_populates="package_updates")

    def __repr__(self):
        return f"<PackageUpdate(id={self.id}, package_name='{self.package_name}', current='{self.current_version}', available='{self.available_version}', host_id={self.host_id})>"


class AvailablePackage(Base):
    """
    This class holds the object mapping for the available_packages table in the
    PostgreSQL database. It stores packages available for installation from
    configured repositories on each host.
    """

    __tablename__ = "available_packages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    package_name = Column(String(255), nullable=False, index=True)
    package_version = Column(String(100), nullable=False)
    package_description = Column(Text, nullable=True)
    package_manager = Column(String(50), nullable=False, index=True)
    os_name = Column(String(100), nullable=False, index=True)
    os_version = Column(String(100), nullable=False, index=True)
    last_updated = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)

    def __repr__(self):
        return f"<AvailablePackage(id={self.id}, package_name='{self.package_name}', version='{self.package_version}', os='{self.os_name} {self.os_version}')>"


class SoftwareInstallationLog(Base):
    """
    This class holds the object mapping for the software_installation_log table in the
    PostgreSQL database. Tracks package installation requests and their execution.
    """

    __tablename__ = "software_installation_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    host_id = Column(Integer, ForeignKey("host.id", ondelete="CASCADE"), nullable=False)

    # Installation request details
    package_name = Column(String(255), nullable=False)
    package_manager = Column(String(50), nullable=False)
    requested_version = Column(String(100), nullable=True)
    requested_by = Column(
        String(100), nullable=False
    )  # User who requested installation

    # Request tracking
    installation_id = Column(
        String(36), nullable=False, unique=True, index=True
    )  # UUID for tracking
    status = Column(
        String(20), nullable=False, server_default="pending", index=True
    )  # pending, queued, installing, completed, failed, cancelled

    # Timestamps
    requested_at = Column(DateTime(timezone=True), nullable=False, index=True)
    queued_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Installation results
    installed_version = Column(String(100), nullable=True)
    success = Column(Boolean, nullable=True)
    error_message = Column(Text, nullable=True)
    installation_log = Column(Text, nullable=True)  # Command output/logs

    # Metadata
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Relationships
    host = relationship("Host", back_populates="software_installation_logs")

    def __repr__(self):
        return (
            f"<SoftwareInstallationLog(id={self.id}, installation_id='{self.installation_id}', "
            f"package_name='{self.package_name}', status='{self.status}', host_id={self.host_id})>"
        )


class InstallationRequest(Base):
    """
    Primary table for tracking package installation requests.
    Each row represents one user request which may include multiple packages.
    """

    __tablename__ = "installation_requests"

    id = Column(String(36), primary_key=True)  # UUID
    host_id = Column(Integer, ForeignKey("host.id", ondelete="CASCADE"), nullable=False)

    # Request metadata
    requested_by = Column(
        String(100), nullable=False
    )  # User who requested installation
    requested_at = Column(DateTime(timezone=True), nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Status tracking
    status = Column(
        String(20), nullable=False, server_default="pending", index=True
    )  # pending, in_progress, completed, failed

    # Operation type - install or uninstall
    operation_type = Column(
        String(20), nullable=False, server_default="install", index=True
    )  # install, uninstall

    # Results
    result_log = Column(Text, nullable=True)  # Captured output from agent

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Relationships
    host = relationship("Host")
    packages = relationship(
        "InstallationPackage",
        back_populates="installation_request",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return (
            f"<InstallationRequest(id='{self.id}', status='{self.status}', "
            f"requested_by='{self.requested_by}', host_id={self.host_id})>"
        )


class InstallationPackage(Base):
    """
    Secondary table for tracking individual packages within an installation request.
    Many-to-one relationship with InstallationRequest.
    """

    __tablename__ = "installation_packages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    installation_request_id = Column(
        String(36),
        ForeignKey("installation_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Package details
    package_name = Column(String(255), nullable=False)
    package_manager = Column(String(50), nullable=False)

    # Relationships
    installation_request = relationship(
        "InstallationRequest", back_populates="packages"
    )

    def __repr__(self):
        return (
            f"<InstallationPackage(id={self.id}, package_name='{self.package_name}', "
            f"installation_request_id='{self.installation_request_id}')>"
        )
