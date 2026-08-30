# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Which database each Pro+ engine's routes read and write (Phase 13.1).

Every licensed engine used to be mounted with ``Depends(get_db)`` -- the
BOOTSTRAP session -- while the rest of the API used ``get_tenant_db``. In a
multi-tenant deployment that meant a licensed engine served, and wrote, the
wrong database: a tenant user's alert rule was stored in bootstrap, and the
evaluator then looked for drift findings that live in the tenant DB and found
none. Nothing errored. Found 2026-08-29 while verifying the ``config_drift``
alert condition end to end.

WHY THE SWAP IS SAFE RATHER THAN RISKY
--------------------------------------
``get_tenant_db`` -> ``get_request_engine`` falls back to ``db.get_engine()``
-- the very engine ``get_db`` binds -- whenever multi-tenancy is off OR no
tenant is in scope. So it is behaviourally identical to ``get_db`` in every
case where ``get_db`` was already right, and differs only where it was wrong.

WHY THREE ENGINES ARE MOUNTED WITH ``get_db`` AND THAT IS CORRECT
----------------------------------------------------------------
``advisory``, ``vuln`` and ``lifecycle`` read BOTH per-host data and the SHARED
partition (``shared_advisory*``, ``shared_vulnerability*``,
``shared_os_lifecycle*`` -- CVE and errata data is global platform truth, one
copy for every tenant). Rather than take a single session, each engine's router
SELF-ROUTES: it imports ``get_tenant_db`` and ``get_shared_db`` itself and binds
each endpoint to the right one.

So the ``db_dependency`` we pass them is used ONLY as the fallback when
``backend.persistence.partitions`` cannot be imported -- and in that case
``get_db`` is exactly the right answer. Mounting them with ``get_db`` is
therefore correct, not an instance of the bug above.

(Corrected 2026-08-29: an earlier pass here claimed these engines were reading
per-host data from the wrong database. They were not. The tests below assert
the self-routing directly, so the claim is checked rather than asserted in
prose.)
"""

import re
from pathlib import Path

import pytest

MOUNT_FILES = (
    Path("backend/api/proplus_routes.py"),
    Path("backend/api/proplus_routes_mounts.py"),
)

# Data-plane engines: everything they touch is partitioned per tenant.
TENANT_SCOPED = {
    "mount_alerting_routes",
    "mount_audit_routes",
    "mount_automation_routes",
    "mount_av_management_routes",
    "mount_compliance_routes",
    "mount_container_routes",
    "mount_federation_controller_routes",
    "mount_federation_site_routes",
    "mount_firewall_orchestration_routes",
    "mount_fleet_routes",
    "mount_health_routes",
    "mount_observability_routes",
    "mount_provisioning_routes",
    "mount_reporting_routes",
    "mount_secrets_routes",
    "mount_virtualization_routes",
}

# Engines that ALSO read the shared partition. See the module docstring.
SHARED_PARTITION_READERS = {
    "mount_advisory_routes",
    "mount_lifecycle_routes",
    "mount_vulnerability_routes",
}


def _dependency_map():
    """``{mount_function: {"get_db" | "get_tenant_db", ...}}`` as mounted."""
    found = {}
    for path in MOUNT_FILES:
        current = None
        for line in path.read_text(encoding="utf-8").split("\n"):
            match = re.match(r"def (mount_\w+)\(", line)
            if match:
                current = match.group(1)
            for dep in ("get_tenant_db", "get_db"):
                if f"Depends({dep})" in line and current:
                    found.setdefault(current, set()).add(dep)
                    break
    return found


class TestEveryMountIsClassified:
    def test_the_mount_files_are_where_we_think_they_are(self):
        for path in MOUNT_FILES:
            assert path.exists(), f"{path} moved; this audit is now blind"

    def test_no_mount_is_left_unclassified(self):
        # A NEW engine mounted with get_db would otherwise inherit the bug
        # silently. Adding one must mean making a decision here.
        classified = TENANT_SCOPED | SHARED_PARTITION_READERS
        unknown = set(_dependency_map()) - classified
        assert not unknown, (
            f"unclassified Pro+ route mounts: {sorted(unknown)}. Decide whether "
            "each is tenant data-plane (use get_tenant_db) or reads the shared "
            "partition (document why it stays on get_db), then list it above."
        )

    def test_every_classified_mount_actually_exists(self):
        # Guards the reverse drift: a renamed mount silently dropping out of
        # the audit.
        present = set(_dependency_map())
        missing = (TENANT_SCOPED | SHARED_PARTITION_READERS) - present
        assert not missing, f"listed but no longer mounted: {sorted(missing)}"


class TestDataPlaneEnginesAreTenantScoped:
    @pytest.mark.parametrize("mount", sorted(TENANT_SCOPED))
    def test_it_uses_the_tenant_session(self, mount):
        deps = _dependency_map().get(mount, set())
        assert "get_tenant_db" in deps, (
            f"{mount} is mounted on the bootstrap session; in multi-tenancy it "
            "will serve and write the wrong database, silently"
        )

    @pytest.mark.parametrize("mount", sorted(TENANT_SCOPED))
    def test_it_does_not_also_take_the_bootstrap_session(self, mount):
        # A leftover get_db alongside the tenant one means half the routes are
        # still wrong, which is harder to spot than all of them being wrong.
        assert "get_db" not in _dependency_map().get(mount, set())


class TestSharedPartitionEnginesSelfRoute:
    @pytest.mark.parametrize("mount", sorted(SHARED_PARTITION_READERS))
    def test_it_is_mounted_with_the_bootstrap_fallback(self, mount):
        deps = _dependency_map().get(mount, set())
        assert "get_db" in deps, (
            f"{mount} passes a dependency the engine uses only when partitions "
            "cannot be imported; get_db is the correct fallback there"
        )

    @pytest.mark.parametrize("mount", sorted(SHARED_PARTITION_READERS))
    def test_the_reason_is_written_down_next_to_it(self, mount):
        # A bare get_db here is indistinguishable from the bug. The comment is
        # what tells the next reader this one is deliberate.
        blob = "\n".join(p.read_text(encoding="utf-8") for p in MOUNT_FILES)
        body = blob.split(f"def {mount}(")[1].split("\ndef ")[0]
        assert "self-routing" in body.lower(), (
            f"{mount} passes get_db with no explanation; say why, or it reads "
            "as the multi-tenancy bug rather than a deliberate fallback"
        )


class TestTheSharedPartitionClaimIsTrue:
    """The classification above rests on where these tables actually live."""

    def test_shared_readers_really_do_map_to_shared_tables(self):
        from backend.persistence import models  # noqa: PLC0415

        # One representative model per shared-partition engine.
        for cls_name in ("SharedAdvisory", "Vulnerability", "SharedOsLifecycle"):
            table = getattr(models, cls_name).__tablename__
            assert table.startswith("shared_"), (
                f"{cls_name} is no longer a shared-partition table ({table}); "
                "re-run the audit -- its engine may now be tenant-scopable"
            )

    def test_a_tenant_scoped_engines_table_is_not_shared(self):
        from backend.persistence import models  # noqa: PLC0415

        # Alerting is the engine this whole audit started from.
        assert models.AlertRule.__tablename__ == "alert_rule"
        assert not models.AlertRule.__tablename__.startswith(("shared_", "registry_"))


class TestFleetHostProviderSpansEveryDatabase:
    """The fleet scheduler resolves its selectors against this host list.

    Reading only the bootstrap database returns an EMPTY fleet for every
    tenant, so a scheduled fleet operation "fires" against nothing and reports
    success while touching no host -- the same silent shape as the other
    background workers fixed on 2026-08-29.
    """

    @staticmethod
    def _session(hosts, boom=False):
        class _S:
            closed = False

            def query(self, _model):
                if boom:
                    raise RuntimeError("tenant database unreachable")
                return self

            def all(self):
                return list(hosts)

            def close(self):
                self.closed = True

        return _S()

    def test_hosts_from_every_database_are_returned(self):
        from unittest.mock import patch  # noqa: PLC0415

        from backend.services import proplus_dispatch  # noqa: PLC0415

        a, b = self._session(["h1"]), self._session(["h2", "h3"])
        with patch(
            "backend.persistence.partitions.iter_host_databases",
            lambda: iter([("boot", None, a), ("t1", "t", b)]),
        ):
            provider = proplus_dispatch.build_host_provider(lambda: iter([a]))
            assert provider() == ["h1", "h2", "h3"]

    def test_every_session_is_closed(self):
        from unittest.mock import patch  # noqa: PLC0415

        from backend.services import proplus_dispatch  # noqa: PLC0415

        a, b = self._session(["h1"]), self._session([])
        with patch(
            "backend.persistence.partitions.iter_host_databases",
            lambda: iter([("boot", None, a), ("t1", "t", b)]),
        ):
            proplus_dispatch.build_host_provider(lambda: iter([a]))()
        assert a.closed and b.closed

    def test_one_unreachable_tenant_does_not_empty_the_fleet(self):
        from unittest.mock import patch  # noqa: PLC0415

        from backend.services import proplus_dispatch  # noqa: PLC0415

        bad, good = self._session([], boom=True), self._session(["h2"])
        with patch(
            "backend.persistence.partitions.iter_host_databases",
            lambda: iter([("bad", None, bad), ("good", "t", good)]),
        ):
            provider = proplus_dispatch.build_host_provider(lambda: iter([good]))
            assert provider() == ["h2"]
        assert bad.closed and good.closed


class TestTheSelfRoutingClaimIsChecked:
    """Prove the three engines really do bind their own partition sessions.

    The claim above ("they self-route, so get_db is only a fallback") is what
    makes mounting them with the bootstrap session correct. If a rebuild ever
    dropped that self-routing, the mounts would silently become the very bug
    this module exists to prevent -- and every other test here would still
    pass. So the claim gets checked against the loaded engine, not trusted.

    Skips when the licensed engine is not installed: the OSS suite must not
    depend on Pro+ artifacts being present.
    """

    ENGINES = {
        "advisory_engine": "get_advisory_router",
        "vuln_engine": "get_vulnerability_router",
        "lifecycle_engine": "get_lifecycle_router",
    }

    @pytest.mark.parametrize("code,factory", sorted(ENGINES.items()))
    def test_the_router_factory_binds_partition_sessions_itself(self, code, factory):
        import inspect  # noqa: PLC0415

        from backend.licensing.module_loader import module_loader  # noqa: PLC0415

        engine = module_loader.get_module(code)
        if engine is None or not hasattr(engine, factory):
            pytest.skip(f"{code} not installed; nothing to verify here")

        doc = (inspect.getdoc(getattr(engine, factory)) or "").lower()
        assert "get_tenant_db" in doc and "get_shared_db" in doc, (
            f"{code}.{factory} no longer documents binding both partition "
            "sessions itself. If it now uses the db_dependency we pass, the "
            "mount must switch to get_tenant_db + a shared session."
        )
