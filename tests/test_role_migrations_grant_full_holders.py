# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A new security role reaches everyone who already holds them all.

q38clockbound, q39clockresync and q42hwhealth granted their roles only to
``is_admin`` users, so the production operator -- every other role, admin flag
off -- held 102 of 105 roles and could not resync a clock (2026-10-17).
``backend.persistence.role_grants`` grants to admins AND full holders;
q44rolegrants repairs the three roles already shipped; and the scan at the end
fails any new migration that grants a role without the helper."""

import os
import re
import tempfile
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence import models
from backend.persistence.role_grants import grant_new_role_to_full_holders
from tests.test_machine_migration import _alembic, _grants

_REPAIRED = ("Manage Time Sync", "Resync Host Clock", "Manage Hardware Health")
_VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
# Role migrations written before the helper existed.  Never edited (they have
# run in production); q44rolegrants repairs the admin-only ones.
_LEGACY_ROLE_MIGRATIONS = {
    "54fcacb0e742_add_security_roles_and_permissions.py",
    "85d271dc0e7f_add_view_and_edit_user_security_roles.py",
    "o12mgttenant_add_manage_tenants_role.py",
    "p13rmpkgrole_add_remove_package_role.py",
    "q36assettagrole_grant_manage_asset_tags.py",
    "q38clockbound_add_clock_bounds.py",
    "q39clockresync_add_clock_resync.py",
    "q42hwhealth_add_hardware_health.py",
}


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    yield path
    if os.path.exists(path):
        os.unlink(path)


def _user(session, userid, is_admin=False):
    user = models.User(id=uuid.uuid4(), userid=userid, active=True, is_admin=is_admin)
    session.add(user)
    session.flush()
    return user


def _give(session, user, role_names):
    for role in session.query(models.SecurityRole).filter(
        models.SecurityRole.name.in_(list(role_names))
    ):
        session.add(models.UserSecurityRole(user_id=user.id, role_id=role.id))


def _populate(db_path):
    """A production-shaped bootstrap: an operator with every role but the three
    admin-only ones, a partial holder, and an admin.  Returns the userids."""
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with sessionmaker(bind=engine)() as session:
            names = [r.name for r in session.query(models.SecurityRole)]
            assert set(_REPAIRED) <= set(names), "the three roles must exist"
            operator = _user(session, "operator@example.com")
            _give(session, operator, [n for n in names if n not in _REPAIRED])
            partial = _user(session, "partial@example.com")
            _give(session, partial, [n for n in names if n not in _REPAIRED][:3])
            _user(session, "admin@example.com", is_admin=True)
            session.commit()
    finally:
        engine.dispose()


def _roles_of(db_path, userid):
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with sessionmaker(bind=engine)() as session:
            user = session.query(models.User).filter_by(userid=userid).one()
            return {
                r.name
                for r in session.query(models.SecurityRole)
                .join(
                    models.UserSecurityRole,
                    models.UserSecurityRole.role_id == models.SecurityRole.id,
                )
                .filter(models.UserSecurityRole.user_id == user.id)
            }
    finally:
        engine.dispose()


def test_q44_gives_the_three_roles_to_the_operator_and_not_the_partial(db_path):
    _alembic(["--name", "shared", "upgrade", "head"], db_path)
    _alembic(["upgrade", "q43hwtools"], db_path)
    _populate(db_path)
    assert not set(_REPAIRED) & _roles_of(db_path, "operator@example.com")

    _alembic(["upgrade", "head"], db_path)
    assert set(_REPAIRED) <= _roles_of(db_path, "operator@example.com")
    assert not set(_REPAIRED) & _roles_of(db_path, "partial@example.com")
    # created after q38-q42 ran, so the admin did not get them then; q44 does
    assert set(_REPAIRED) <= _roles_of(db_path, "admin@example.com")
    counts = {role: _grants(db_path, role) for role in _REPAIRED}

    # round trip: downgrade is a no-op, a second upgrade adds nothing
    _alembic(["downgrade", "q43hwtools"], db_path)
    _alembic(["upgrade", "head"], db_path)
    assert {role: _grants(db_path, role) for role in _REPAIRED} == counts


def test_the_helper_grants_admins_and_full_holders_only_once(db_path):
    _alembic(["--name", "shared", "upgrade", "head"], db_path)
    _alembic(["upgrade", "head"], db_path)
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with sessionmaker(bind=engine)() as session:
            names = [r.name for r in session.query(models.SecurityRole)]
            new = names[0]
            others = names[1:]
            session.query(models.UserSecurityRole).delete()
            full = _user(session, "full@example.com")
            _give(session, full, others)
            partial = _user(session, "partial@example.com")
            _give(session, partial, others[:-1])
            _user(session, "admin@example.com", is_admin=True)
            _user(session, "nobody@example.com")
            session.commit()
        with engine.begin() as conn:
            assert grant_new_role_to_full_holders(conn, new) == 2
        with engine.begin() as conn:
            assert grant_new_role_to_full_holders(conn, new) == 0  # idempotent
    finally:
        engine.dispose()
    assert new in _roles_of(db_path, "full@example.com")
    assert new in _roles_of(db_path, "admin@example.com")
    assert new not in _roles_of(db_path, "partial@example.com")
    assert new not in _roles_of(db_path, "nobody@example.com")


def test_new_role_migrations_use_the_helper():
    """A migration that grants roles must reach full holders, not only admins."""
    offenders = []
    for path in sorted(_VERSIONS.glob("*.py")):
        if path.name in _LEGACY_ROLE_MIGRATIONS:
            continue
        text = path.read_text(encoding="utf-8")
        grants = re.search(r"INSERT\s+INTO\s+user_security_roles", text, re.I)
        if grants and "grant_new_role_to_full_holders" not in text:
            offenders.append(path.name)
    assert not offenders, (
        f"{offenders} insert into user_security_roles directly; seed the role and "
        "call backend.persistence.role_grants.grant_new_role_to_full_holders so "
        "operators who hold every role get it too (not only is_admin users)"
    )
