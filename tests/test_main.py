"""
This module houses the unit tests for sysmanage
"""
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)

def test_read_main():
    """
    Function to run unit tests
    """
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello World"}
