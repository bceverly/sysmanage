"""
This module contains all of the unit tests for the /host routes in the 
backend API for SysManage.  The main entry point is a function called
test_host() which in turn runs all of the individual unit tests in this
file.
"""
from random import randint

from fastapi.testclient import TestClient

from backend.main import app
from backend.config import config

# Get the client object
client = TestClient(app)

# Get the /etc/sysmanage.yaml configuration
the_config = config.get_config()

def test_host():
    """
    This test validates that a user can be successfully added to
    the system.  It is non-destructive other than advancing the
    numeric key on the database table.
    """
    # Log into the system
    response = client.post("/login", json={
        "userid": the_config["security"]["admin_userid"],
        "password": the_config["security"]["admin_password"]
    })
    assert response.status_code == 200

    # Get the bearer token
    token = response.json()["X_Reauthorization"]

    # Add a host
    random_host = f"host{randint(100000,999999)}.example.com"
    random_ipv4 = f"{randint(1,255)}.{randint(1,255)}.{randint(1,255)}.{randint(1,255)}"
    random_ipv6 = f"{randint(1,65535):x}.{randint(1,65535):x}.{randint(1,65535):x}.{randint(1,65535):x}.{randint(1,65535):x}.{randint(1,65535):x}.{randint(1,65535):x}.{randint(1,65535):x}"
    response = client.post("/host", headers={
        "Authorization": f"Bearer {token}"
    }, json={
        "active": True,
        "fqdn": random_host,
        "ipv4": random_ipv4,
        "ipv6": random_ipv6
    })
    assert response.status_code == 200

    token = response.headers["X_Reauthorization"]
    the_id = response.json()["id"]

    # Get the host by id
    response = client.get(f"/host/{the_id}", headers={
        "Authorization": f"Bearer {token}"
    })
    assert response.status_code == 200
    assert response.json() == {"id": the_id,
                               "active": True,
                               "fqdn": random_host,
                               "ipv4": random_ipv4,
                               "ipv6": random_ipv6}

    token = response.headers["X_Reauthorization"]

    # Get the host by fqdn
    response = client.get(f"/host/by_fqdn/{random_host}", headers={
        "Authorization": f"Bearer {token}"
    })
    assert response.status_code == 200
    assert response.json() == {"id": the_id,
                               "active": True,
                               "fqdn": random_host,
                               "ipv4": random_ipv4,
                               "ipv6": random_ipv6}

    token = response.headers["X_Reauthorization"]

    # Cleanup
    response = client.delete(f"/host/{the_id}", headers={
        "Authorization": f"Bearer {token}"
    })
    assert response.status_code == 200
