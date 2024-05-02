"""
This module manages the "db" object which is the gateway into the SQLAlchemy
ORM used by SysManage.
"""
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from config import config

# Get the /etc/sysmanage.yaml configuration
the_config = config.get_config()

DB_USER = the_config["database"]["user"]
DB_PASSWORD = the_config["database"]["password"]
DB_HOST = the_config["database"]["host"]
DB_PORT = the_config["database"]["port"]
DB_NAME = the_config["database"]["name"]

# Build the connection string
SQLALCHEMY_DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# create the database connection
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Get the base model class - we can use this to extend any models
Base = declarative_base()

def get_db():
    """
    Provide a mechanism to retrieve the database from within the rest of the application
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
