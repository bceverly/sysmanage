"""
This module holds the various models that are persistence backed by the
PostgreSQL database.
"""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String

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
    This class holds the object mapping for the user table in the PostgreSQL
    database.
    """

    __tablename__ = "host"
    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    active = Column(Boolean, unique=False, index=False)
    fqdn = Column(String, index=True)
    ipv4 = Column(String)
    ipv6 = Column(String)
    last_access = Column(DateTime)
    status = Column(String(20), nullable=False, server_default="up")


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
    last_access = Column(DateTime)
    # Account locking fields
    is_locked = Column(Boolean, default=False, nullable=False)
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_at = Column(DateTime, nullable=True)
