"""
This module houses the unit tests for sysmanage
"""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_main():
    """
    Function to run unit tests
    """

    assert True
