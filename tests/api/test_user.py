"""
This module contains all of the unit tests for the /user routes in the 
backend API for SysManage.  The main entry point is a function called
test_user_all() which in turn runs all of the individual unit tests in this
file.
"""

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
    token = response.json()["access_token"]

    # Add a user
    response = client.post("/user", headers={
        "Authorization": f"Bearer {token}"
    }, json={
        "active": True,
        "userid": "test123456@example.com",
        "password": "password"
    })
    assert response.status_code == 200

    token = response.headers["reauthorization"]
    the_id = response.json()["id"]

    # Get the user by id
    response = client.get(f"/user/{the_id}", headers={
        "Authorization": f"Bearer {token}"
    })
    assert response.status_code == 200
    assert response.json() == {"id": the_id,
                               "active": True,
                               "userid": "test123456@example.com"}

    token = response.headers["reauthorization"]

    # Get the user by userid
    response = client.get("/user/by_userid/test123456@example.com", headers={
        "Authorization": f"Bearer {token}"
    })
    assert response.status_code == 200
    assert response.json() == {"id": the_id,
                               "active": True,
                               "userid": "test123456@example.com"}

    token = response.headers["reauthorization"]

    # Cleanup
    response = client.delete(f"/user/{the_id}", headers={
        "Authorization": f"Bearer {token}"
    })
    assert response.status_code == 200

def test_user_get_by_id():
    """
    This test validates that a user can be succesfully found by
    its primary key.  It is non-destructive other than advancing
    the numberic key on the database table.
    """
    assert True

def test_user_get_by_userid():
    """
    This test validates that a user can be successfully found by
    its userid.  It is non-destructive other than advancing the
    numeric key on the database table.
    """
    assert True

def test_user_get_all():
    """
    This test validates that multiple users can be successfully
    retrieved 
    """
    assert True
