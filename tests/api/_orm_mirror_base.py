# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Shared declarative base for the API-test ORM schema mirror.

The API test suite uses a hand-written, SQLite-compatible mirror of the
production ORM (see ``tests/api/conftest.py`` for the rationale).  The mirror
classes are split across ``_orm_mirror_a`` and ``_orm_mirror_b`` for file-size
reasons; they all register on the single ``TestBase`` defined here so that
string-based relationships resolve across both modules.
"""

from sqlalchemy.ext.declarative import declarative_base

TestBase = declarative_base()
