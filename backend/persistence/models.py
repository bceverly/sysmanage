# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
This module holds the various models that are persistence backed by the
PostgreSQL database.

⚠️  TESTING ARCHITECTURE WARNING ⚠️

When adding new models to this file, you MUST also update:
- /tests/api/conftest.py (if API tests need the model)

Follow SQLite compatibility rules for test models:
- ✅ Use Integer primary keys (not BigInteger) for auto-increment in test models
- ✅ Use String instead of Text in test models for better performance

See README.md and TESTING.md for complete guidelines.
"""

# Import and re-export all models from the models package
# pylint: disable=wildcard-import,unused-wildcard-import
