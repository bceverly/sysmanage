"""
This module holds the various models that are persistence backed by the
PostgreSQL database.
"""

from sqlalchemy import Column, BigInteger, Integer, String, DateTime, Boolean
from backend.persistence.db import Base

class User(Base):
    """
    This class holds the object mapping for the user table in the PostgreSQL
    database.
    """
    __tablename__ = "user"
    id = Column(BigInteger, primary_key=True, index=True)
    active = Column(Boolean, unique=False, index=False)
    userid = Column(String)
    hashed_password = Column(String, unique=False, index=False)
    last_access = Column(DateTime)

class BearerToken(Base):
    """
    This class holds the object mapping for the bearer token table in the
    PostgreSQL database.
    """
    __tablename__ = "bearer_token"
    token = Column(String(200), primary_key=True, index=True)
    created_datetime = Column(DateTime)