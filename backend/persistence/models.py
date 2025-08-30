"""
This module holds the various models that are persistence backed by the
PostgreSQL database.
"""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String, Text

from backend.persistence.db import Base


class BearerToken(Base):
    """
    This class holds the object mapping for the bearer token table in the
    PostgreSQL database.
    """

    __tablename__ = "bearer_token"
    token = Column(String(200), primary_key=True, index=True)
    created_datetime = Column(DateTime)


class Host(Base):
    """
    This class holds the object mapping for the host table in the PostgreSQL
    database.
    """

    __tablename__ = "host"
    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    active = Column(Boolean, unique=False, index=False)
    fqdn = Column(String, index=True)
    ipv4 = Column(String)
    ipv6 = Column(String)
    last_access = Column(DateTime(timezone=True))
    status = Column(String(20), nullable=False, server_default="up")
    approval_status = Column(String(20), nullable=False, server_default="pending")
    client_certificate = Column(Text, nullable=True)
    certificate_serial = Column(String(64), nullable=True)
    certificate_issued_at = Column(DateTime(timezone=True), nullable=True)
    # OS Version fields
    platform = Column(String(50), nullable=True)
    platform_release = Column(String(100), nullable=True)
    platform_version = Column(Text, nullable=True)
    machine_architecture = Column(String(50), nullable=True)  # x86_64, arm64, etc.
    processor = Column(String(100), nullable=True)
    os_details = Column(Text, nullable=True)  # JSON field for additional OS info
    os_version_updated_at = Column(DateTime(timezone=True), nullable=True)
    # Hardware inventory fields
    cpu_vendor = Column(String(100), nullable=True)
    cpu_model = Column(String(200), nullable=True)
    cpu_cores = Column(Integer, nullable=True)
    cpu_threads = Column(Integer, nullable=True)
    cpu_frequency_mhz = Column(Integer, nullable=True)
    memory_total_mb = Column(BigInteger, nullable=True)
    storage_details = Column(Text, nullable=True)  # JSON field for storage devices
    network_details = Column(Text, nullable=True)  # JSON field for network interfaces
    hardware_details = Column(
        Text, nullable=True
    )  # JSON field for additional hardware info
    hardware_updated_at = Column(DateTime(timezone=True), nullable=True)


class User(Base):
    """
    This class holds the object mapping for the user table in the PostgreSQL
    database.
    """

    __tablename__ = "user"
    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    active = Column(Boolean, unique=False, index=False)
    userid = Column(String)
    hashed_password = Column(String, unique=False, index=False)
    last_access = Column(DateTime(timezone=True))
    # Account locking fields
    is_locked = Column(Boolean, default=False, nullable=False)
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_at = Column(DateTime, nullable=True)
