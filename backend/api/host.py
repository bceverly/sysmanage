"""
This module houses the API routes for the host object in SysManage.
"""
from datetime import datetime, timezone
from fastapi import HTTPException, APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from backend.auth.auth_bearer import JWTBearer
from backend.persistence import db, models
from backend.config import config

router = APIRouter()

class Host(BaseModel):
    """
    This class represents the JSON payload to the /host POST/PUT requests.
    """
    active: bool
    fqdn: str
    ipv4: str
    ipv6: str

@router.delete("/host/{id}", dependencies=[Depends(JWTBearer())])
async def delete_host(id: int):
    """
    This function deletes a single host given an id
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())

    with session_local() as session:
        # See if we were passed a valid id
        hosts = session.query(models.Host).filter(models.Host.id == id).all()

        # Check for failure
        if len(hosts) != 1:
            raise HTTPException(status_code=404, detail="Host not found")

        # Delete the record
        session.query(models.Host).filter(models.Host.id == id).delete()
        session.commit()

    return {
        "result": True
        }

@router.get("/host/{id}", dependencies=[Depends(JWTBearer())])
async def get_host(id: int):
    """
    This function retrieves a single host by its id
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())

    with session_local() as session:
        hosts = session.query(models.Host).filter(models.Host.id == id).all()

        # Check for failure
        if len(hosts) != 1:
            raise HTTPException(status_code=404, detail="Host not found")

        ret_host = models.Host(id=hosts[0].id,
                               active=hosts[0].active,
                               fqdn=hosts[0].fqdn,
                               ipv4=hosts[0].ipv4,
                               ipv6=hosts[0].ipv6)

        return ret_host

@router.get("/host/by_fqdn/{fqdn}", dependencies=[Depends(JWTBearer())])
async def get_host_by_fqdn(fqdn: str):
    """
    This function retrieves a single host by fully qualified domain name
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())

    with session_local() as session:
        hosts = session.query(models.Host).filter(models.Host.fqdn == fqdn).all()

        # Check for failure
        if len(hosts) != 1:
            raise HTTPException(status_code=404, detail="Host not found")

        ret_host = models.Host(id=hosts[0].id,
                               active=hosts[0].active,
                               fqdn=hosts[0].fqdn,
                               ipv4=hosts[0].ipv4,
                               ipv6=hosts[0].ipv6)

        return ret_host

@router.get("/hosts", dependencies=[Depends(JWTBearer())])
async def get_all_hosts():
    """
    This function retrieves all hosts in the system
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())

    with session_local() as session:
        result = session.query(models.Host).all()

        ret_hosts = []
        for host in result:
            the_host = models.Host(id=host.id,
                                   active=host.active,
                                   fqdn=host.fqdn,
                                   ipv4=host.ipv4,
                                   ipv6=host.ipv6)
            ret_hosts.append(the_host)

        return ret_hosts

@router.post("/host", dependencies=[Depends(JWTBearer())])
async def add_host(new_host: Host):
    """
    This function adds a new host to the system.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())

    # Add the data to the database
    with session_local() as session:
        host = models.Host(fqdn=new_host.fqdn,
                           active=new_host.active,
                           ipv4=new_host.ipv4,
                           ipv6=new_host.ipv6,
                           last_access=datetime.now(timezone.utc))
        session.add(host)
        session.commit()
        ret_host = models.Host(id = host.id,
                               active = host.active,
                               fqdn = host.fqdn,
                               ipv4 = host.ipv4,
                               ipv6 = host.ipv6)

        return ret_host

@router.put("/host/{id}", dependencies=[Depends(JWTBearer())])
async def update_host(id: int, host_data: Host):
    """
    This function updates an existing host by id
    """

    # Get the /etc/sysmanage.yaml configuration
    the_config = config.get_config()

    # Get the SQLAlchemy session
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())

    # Update the user
    with session_local() as session:
        # See if we were passed a valid id
        hosts = session.query(models.Host).filter(models.Host.id == id).all()

        # Check for failure
        if len(hosts) != 1:
            raise HTTPException(status_code=404, detail="Host not found")

        # Update the values
        session.query(models.Host).filter(models.Host.id == id).update({models.Host.active: host_data.active,
                                                                        models.Host.fqdn: host_data.fqdn, 
                                                                        models.Host.ipv4: host_data.ipv4,
                                                                        models.Host.ipv6: host_data.ipv6, 
                                                                        models.Host.last_access: datetime.now(timezone.utc)})
        session.commit()

        ret_host = models.Host(id = id,
                               active = host_data.active,
                               fqdn = host_data.fqdn,
                               ipv4 = host_data.ipv4,
                               ipv6 = host_data.ipv6)

    return ret_host
