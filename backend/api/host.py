"""
This module houses the API routes for the host object in SysManage.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from backend.auth.auth_bearer import JWTBearer
from backend.persistence import db, models

router = APIRouter()


class HostRegistration(BaseModel):
    """
    This class represents the JSON payload for agent registration.
    Extends Host with optional fields for agent registration.
    """

    active: bool
    fqdn: str
    hostname: str
    ipv4: Optional[str] = None
    ipv6: Optional[str] = None
    platform: Optional[str] = None
    platform_release: Optional[str] = None
    platform_version: Optional[str] = None
    architecture: Optional[str] = None
    processor: Optional[str] = None


class Host(BaseModel):
    """
    This class represents the JSON payload to the /host POST/PUT requests.
    """

    active: bool
    fqdn: str
    ipv4: str
    ipv6: str


@router.delete("/host/{host_id}", dependencies=[Depends(JWTBearer())])
async def delete_host(host_id: int):
    """
    This function deletes a single host given an id
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # See if we were passed a valid id
        hosts = session.query(models.Host).filter(models.Host.id == host_id).all()

        # Check for failure
        if len(hosts) != 1:
            raise HTTPException(status_code=404, detail="Host not found")

        # Delete the record
        session.query(models.Host).filter(models.Host.id == host_id).delete()
        session.commit()

    return {"result": True}


@router.get("/host/{host_id}", dependencies=[Depends(JWTBearer())])
async def get_host(host_id: int):
    """
    This function retrieves a single host by its id
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        hosts = session.query(models.Host).filter(models.Host.id == host_id).all()

        # Check for failure
        if len(hosts) != 1:
            raise HTTPException(status_code=404, detail="Host not found")

        ret_host = models.Host(
            id=hosts[0].id,
            active=hosts[0].active,
            fqdn=hosts[0].fqdn,
            ipv4=hosts[0].ipv4,
            ipv6=hosts[0].ipv6,
            status=hosts[0].status,
            last_access=hosts[0].last_access,
        )

        return ret_host


@router.get("/host/by_fqdn/{fqdn}", dependencies=[Depends(JWTBearer())])
async def get_host_by_fqdn(fqdn: str):
    """
    This function retrieves a single host by fully qualified domain name
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        hosts = session.query(models.Host).filter(models.Host.fqdn == fqdn).all()

        # Check for failure
        if len(hosts) != 1:
            raise HTTPException(status_code=404, detail="Host not found")

        ret_host = models.Host(
            id=hosts[0].id,
            active=hosts[0].active,
            fqdn=hosts[0].fqdn,
            ipv4=hosts[0].ipv4,
            ipv6=hosts[0].ipv6,
            status=hosts[0].status,
            last_access=hosts[0].last_access,
        )

        return ret_host


@router.get("/hosts", dependencies=[Depends(JWTBearer())])
async def get_all_hosts():
    """
    This function retrieves all hosts in the system
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        result = session.query(models.Host).all()

        ret_hosts = []
        for host in result:
            the_host = models.Host(
                id=host.id,
                active=host.active,
                fqdn=host.fqdn,
                ipv4=host.ipv4,
                ipv6=host.ipv6,
                status=host.status,
                last_access=host.last_access,
            )
            ret_hosts.append(the_host)

        return ret_hosts


@router.post("/host", dependencies=[Depends(JWTBearer())])
async def add_host(new_host: Host):
    """
    This function adds a new host to the system.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    # Add the data to the database
    with session_local() as session:
        # See if we are trying to add a duplicate host
        check_duplicate = (
            session.query(models.Host).filter(models.Host.fqdn == new_host.fqdn).all()
        )
        if len(check_duplicate) > 0:
            raise HTTPException(status_code=409, detail="Host already exists")

        # Host doesn't exist so proceed with adding it
        host = models.Host(
            fqdn=new_host.fqdn,
            active=new_host.active,
            ipv4=new_host.ipv4,
            ipv6=new_host.ipv6,
            last_access=datetime.now(timezone.utc),
        )
        session.add(host)
        session.commit()
        ret_host = models.Host(
            id=host.id,
            active=host.active,
            fqdn=host.fqdn,
            ipv4=host.ipv4,
            ipv6=host.ipv6,
            status=host.status,
            last_access=host.last_access,
        )

        return ret_host


@router.post("/host/register")
async def register_host(registration_data: HostRegistration):
    """
    Register a new host (agent) with the system.
    This endpoint does not require authentication for initial registration.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Check if host already exists by FQDN
        existing_host = (
            session.query(models.Host)
            .filter(models.Host.fqdn == registration_data.fqdn)
            .first()
        )

        if existing_host:
            # Update existing host with new information
            existing_host.active = registration_data.active
            existing_host.ipv4 = registration_data.ipv4
            existing_host.ipv6 = registration_data.ipv6
            existing_host.last_access = datetime.now(timezone.utc)
            session.commit()

            ret_host = models.Host(
                id=existing_host.id,
                active=existing_host.active,
                fqdn=existing_host.fqdn,
                ipv4=existing_host.ipv4,
                ipv6=existing_host.ipv6,
                status=existing_host.status,
                last_access=existing_host.last_access,
            )

            return ret_host

        # Create new host
        host = models.Host(
            fqdn=registration_data.fqdn,
            active=registration_data.active,
            ipv4=registration_data.ipv4,
            ipv6=registration_data.ipv6,
            last_access=datetime.now(timezone.utc),
        )
        session.add(host)
        session.commit()

        ret_host = models.Host(
            id=host.id,
            active=host.active,
            fqdn=host.fqdn,
            ipv4=host.ipv4,
            ipv6=host.ipv6,
            status=host.status,
            last_access=host.last_access,
        )

        return ret_host


@router.put("/host/{host_id}", dependencies=[Depends(JWTBearer())])
async def update_host(host_id: int, host_data: Host):
    """
    This function updates an existing host by id
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    # Update the user
    with session_local() as session:
        # See if we were passed a valid id
        hosts = session.query(models.Host).filter(models.Host.id == host_id).all()

        # Check for failure
        if len(hosts) != 1:
            raise HTTPException(status_code=404, detail="Host not found")

        # Update the values
        session.query(models.Host).filter(models.Host.id == host_id).update(
            {
                models.Host.active: host_data.active,
                models.Host.fqdn: host_data.fqdn,
                models.Host.ipv4: host_data.ipv4,
                models.Host.ipv6: host_data.ipv6,
                models.Host.last_access: datetime.now(timezone.utc),
            }
        )
        session.commit()

        # Get updated host data after commit
        updated_host = (
            session.query(models.Host).filter(models.Host.id == host_id).first()
        )
        ret_host = models.Host(
            id=updated_host.id,
            active=updated_host.active,
            fqdn=updated_host.fqdn,
            ipv4=updated_host.ipv4,
            ipv6=updated_host.ipv6,
            status=updated_host.status,
            last_access=updated_host.last_access,
        )

    return ret_host
