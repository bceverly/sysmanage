"""
This module contains all of the unit tests for the /user routes in the 
backend API for SysManage.  The main entry point is a function called
test_user() which in turn runs all of the individual unit tests in this
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

def test_user():
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
    token = response.json()["Reauthorization"]

    # Add a user
    random_email = f"test{randint(100000,999999)}@example.com"
    response = client.post("/user", headers={
        "Authorization": f"Bearer {token}"
    }, json={
        "active": True,
        "userid": random_email,
        "password": "password"
    })
    assert response.status_code == 200

    token = response.headers["Reauthorization"]
    the_id = response.json()["id"]

    # Get the user by id
    response = client.get(f"/user/{the_id}", headers={
        "Authorization": f"Bearer {token}"
    })
    assert response.status_code == 200
    assert response.json() == {"id": the_id,
                               "active": True,
                               "userid": random_email}

    token = response.headers["Reauthorization"]

    # Get the user by userid
    response = client.get(f"/user/by_userid/{random_email}", headers={
        "Authorization": f"Bearer {token}"
    })
    assert response.status_code == 200
    assert response.json() == {"id": the_id,
                               "active": True,
                               "userid": random_email}

    token = response.headers["Reauthorization"]

    # Cleanup
    response = client.delete(f"/user/{the_id}", headers={
        "Authorization": f"Bearer {token}"
    })
    assert response.status_code == 200
