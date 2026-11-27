# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Access groups and registration keys live in the tenant's database
(2026-11-27).

Registration looks a registration key up -- and adds the host to the key's
access group -- in the database the host is created in: the enrolling
tenant's.  The screens that make groups and keys wrote them to the
server-wide database instead, so with tenants a key made there was never
found ("Invalid or expired registration key"), a key's site was checked
against the wrong database's federation sites, and an enrollment token's
access group named a group the tenant's database did not have.  Every
endpoint now uses the tenant's database, and audits there.
"""

from backend.api import access_groups
from backend.persistence.db import get_db
from backend.persistence.partitions import get_tenant_db


def _session_dependencies(router):
    found = []
    for route in router.routes:
        for param in route.dependant.dependencies:
            if param.call in (get_db, get_tenant_db):
                found.append((route.path, route.methods, param.call))
    return found


def test_every_endpoint_uses_the_tenant_database():
    for router in (access_groups.groups_router, access_groups.keys_router):
        found = _session_dependencies(router)
        assert found, router.prefix
        for path, methods, call in found:
            assert call is get_tenant_db, (path, methods)


def test_no_entry_is_audited_as_a_server_setting():
    source = access_groups.__file__
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    assert "EntityType.SETTING" not in text
    assert "from backend.persistence.db import get_db" not in text
