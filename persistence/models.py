"""
This module holds the various models that are persistence backed by the
PostgreSQL database.
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean
from persistence.db import Base

class User(Base):
    """
    This class holds the object mapping for the user table in the PostgreSQL
    database.
    """
    __tablename__ = "user"
    id = Column(Integer, primary_key=True, index=True)
    active = Column(Boolean, unique=False, index=False)
    userid = Column(String)
    hashed_password = Column(String, unique=False, index=False)
    last_access = Column(DateTime)
