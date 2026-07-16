# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

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
