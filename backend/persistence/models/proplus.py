"""
Pro+ licensing and health analysis models for SysManage.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

# Constants
HOST_ID_FK = "host.id"
CASCADE_DELETE = "CASCADE"


class ProPlusLicense(Base):
    """
    Pro+ license storage model.
    Stores validated license information and phone-home status.
    """

    __tablename__ = "proplus_license"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    license_key_hash = Column(String(128), nullable=False)
    license_id = Column(String(36), nullable=False, unique=True)
    tier = Column(String(20), nullable=False)  # e.g., "professional", "enterprise"
    features = Column(JSON, nullable=False)  # List of enabled feature codes
    modules = Column(JSON, nullable=False)  # List of available module codes
    expires_at = Column(DateTime, nullable=False)
    offline_days = Column(Integer, nullable=False, default=30)
    last_phone_home_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def __repr__(self):
        return f"<ProPlusLicense(id={self.id}, license_id='{self.license_id}', tier='{self.tier}', is_active={self.is_active})>"


class ProPlusLicenseValidationLog(Base):
    """
    Log of license validation attempts for audit purposes.
    """

    __tablename__ = "proplus_license_validation_log"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    license_id = Column(String(36), nullable=True, index=True)
    validation_type = Column(
        String(50), nullable=False
    )  # "local", "phone_home", "revocation_check"
    result = Column(String(20), nullable=False)  # "success", "failure", "error"
    error_message = Column(Text, nullable=True)
    details = Column(JSON, nullable=True)
    validated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        index=True,
    )

    def __repr__(self):
        return f"<ProPlusLicenseValidationLog(id={self.id}, license_id='{self.license_id}', result='{self.result}')>"


class ProPlusModuleCache(Base):
    """
    Cache of downloaded Pro+ Cython modules.
    Tracks downloaded modules with their versions and file hashes.
    """

    __tablename__ = "proplus_module_cache"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    module_code = Column(String(100), nullable=False, index=True)
    version = Column(String(50), nullable=False)
    platform = Column(String(50), nullable=False)  # e.g., "linux", "windows", "darwin"
    architecture = Column(String(20), nullable=False)  # e.g., "x86_64", "aarch64"
    python_version = Column(String(10), nullable=False)  # e.g., "3.11", "3.12"
    file_path = Column(String(500), nullable=False)
    file_hash = Column(String(128), nullable=False)  # SHA-512 hash
    downloaded_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # Unique constraint on module_code + version + platform + architecture + python_version
    __table_args__ = (
        {
            "sqlite_autoincrement": True,
        },
    )

    def __repr__(self):
        return f"<ProPlusModuleCache(module_code='{self.module_code}', version='{self.version}', platform='{self.platform}')>"


class HostHealthAnalysis(Base):
    """
    AI-powered health analysis results for hosts.
    Stores health scores, grades, issues, and recommendations.
    """

    __tablename__ = "host_health_analysis"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    host_id = Column(
        GUID(),
        ForeignKey(HOST_ID_FK, ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    analyzed_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        index=True,
    )
    score = Column(Integer, nullable=False)  # 0-100 health score
    grade = Column(String(2), nullable=False)  # A+, A, B, C, D, F
    issues = Column(JSON, nullable=True)  # List of identified issues
    recommendations = Column(JSON, nullable=True)  # List of recommendations
    analysis_version = Column(
        String(20), nullable=True
    )  # Version of health_engine used
    raw_metrics = Column(JSON, nullable=True)  # Raw metrics used for analysis

    # Relationship to host
    host = relationship("Host", backref="health_analyses")

    def __repr__(self):
        return f"<HostHealthAnalysis(host_id={self.host_id}, score={self.score}, grade='{self.grade}')>"
