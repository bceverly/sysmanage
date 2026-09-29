# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""21.6 migrations q13assetdisc (S1), q14netdiscpolicy (S2) and q15assetexcl (S3).

Runs the tenant chain on scratch SQLite, checks the tables exist and that the
ORM agrees with them (a row of each round-trips, and deleting the managed host
turns the asset back into an unmanaged one), and that the migration is
idempotent and reversible.
"""

import contextlib
import os
import sqlite3
import subprocess
import sys
import tempfile
import uuid

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.persistence import models

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_TABLES = {
    "discovered_asset",
    "discovered_asset_sighting",
    "network_discovery_observer",
    "network_discovery_policy",  # q14netdiscpolicy (S2)
    "network_discovery_dispatch",
    "discovered_asset_exclusion",  # q15assetexcl (S3)
    "network_sweep_run",  # q16netsweep (S4)
}
_ROLE = "Manage Network Discovery"


def _role_count(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM security_roles WHERE name = ?", (_ROLE,)
        ).fetchone()[0]
    finally:
        conn.close()


def _alembic(args, db_path):
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}
    result = None
    for _attempt in range(4):  # a negative rc is a signal-kill flake
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=_REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode >= 0:
            break
    assert result.returncode == 0, f"alembic {args} failed:\n{result.stderr}"


def _tables(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()


def _host(session):
    host = models.Host(
        id=uuid.uuid4(),
        fqdn="observer.example.com",
        ipv4="10.0.0.5",
        active=True,
        status="up",
        approval_status="approved",
    )
    session.add(host)
    session.flush()
    return host


def test_tenant_chain_creates_the_tables_and_the_orm_agrees():
    fd, db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(db)
    try:
        _alembic(["--name", "shared", "upgrade", "head"], db)
        _alembic(["upgrade", "head"], db)
        assert _TABLES <= _tables(db)

        engine = create_engine(f"sqlite:///{db}")

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _record):  # SQLite enforces FKs only when asked
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        with sessionmaker(bind=engine)() as s:
            observer = _host(s)
            asset = models.DiscoveredAsset(
                identity="aa:bb:cc:00:00:01",
                identity_kind=models.IDENTITY_MAC,
                mac="aa:bb:cc:00:00:01",
                mac_locally_administered=False,
                managed_host_id=observer.id,
                managed_reason="mac",
            )
            s.add(asset)
            s.flush()
            s.add(
                models.DiscoveredAssetSighting(
                    asset_id=asset.id,
                    observer_host_id=observer.id,
                    network="10.0.0.0/24",
                    methods=["arp_listen"],
                    sightings=1,
                )
            )
            s.add(
                models.NetworkDiscoveryObserver(
                    host_id=observer.id, methods={"arp_listen": "ok"}, reports=1
                )
            )
            s.commit()
            assert s.query(models.DiscoveredAsset).one().to_dict()["managed_reason"]

            # The managed host goes away: its asset row must survive as an
            # UNMANAGED device (SET NULL), while the host's own sightings and
            # observer row go with it (CASCADE).
            s.delete(observer)
            s.commit()
            s.expire_all()
            survivor = s.query(models.DiscoveredAsset).one()
            assert survivor.managed_host_id is None
            assert s.query(models.DiscoveredAssetSighting).count() == 0
            assert s.query(models.NetworkDiscoveryObserver).count() == 0
        engine.dispose()

        assert _role_count(db) == 1

        conn = sqlite3.connect(db)
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(discovered_asset)")}
            policy_cols = {
                r[1]
                for r in conn.execute("PRAGMA table_info(network_discovery_policy)")
            }
        finally:
            conn.close()
        assert {"vendor", "device_type", "classification"} <= cols  # q17 (S5)
        assert "retention_days" in policy_cols

        # Idempotent: re-running over existing tables is a no-op, and the role
        # is not seeded twice.
        _alembic(["stamp", "q12builtinmetric"], db)
        _alembic(["upgrade", "head"], db)
        assert _role_count(db) == 1
        # Reversible.
        _alembic(["downgrade", "q12builtinmetric"], db)
        assert not _TABLES & _tables(db)
        assert _role_count(db) == 0
    finally:
        with contextlib.suppress(OSError):
            os.unlink(db)
