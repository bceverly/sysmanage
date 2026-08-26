# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The air-gap collection-run state machine.

This worker is the only thing that moves an ``AirgapCollectionRun`` off
QUEUED, and every failure path it has ends the same way -- ``_mark_failed``
writes a string into ``error_message`` and the row stops.  Nothing raises,
nothing pages, and the operator sees a red chip with whatever text happened
to be produced.  So the *text* and the *reachability* of each branch are the
product here, not incidental: a branch that silently stops matching (a
renamed engine builder, a snapshot field that starts arriving NULL) turns
into "the run just sits there", which is the single hardest symptom to
diagnose in this subsystem.

The Pro+ ``airgap_collector_engine`` is a closed Cython module, so it is
faked down to the builders this worker calls.  The DB is faked too: these
tests are about branch selection and the strings each branch writes, not
about persistence.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.services import airgap_run_tick as tick

TICK = "backend.services.airgap_run_tick"
DISPATCH = "backend.services.proplus_dispatch"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        if isinstance(self._result, list):
            return self._result[0] if self._result else None
        return self._result

    def all(self):
        if self._result is None:
            return []
        return self._result if isinstance(self._result, list) else [self._result]


class _FakeDb:
    """Answers ``query(Model)`` from a dict keyed by model class name."""

    def __init__(self, **by_model):
        self._by_model = by_model
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def query(self, model):
        return _FakeQuery(self._by_model.get(model.__name__))

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _mirror(name="ubuntu-mirror", host_id="host-1", **overrides):
    mirror = SimpleNamespace(
        name=name,
        host_id=host_id,
        last_snapshot_message_id=None,
        last_snapshot_status="SUCCESS",
        last_snapshot_error=None,
    )
    for key, value in overrides.items():
        setattr(mirror, key, value)
    return mirror


def _snapshot(snapshot_id="snap-1", size_bytes=1000):
    return SimpleNamespace(snapshot_id=snapshot_id, size_bytes=size_bytes)


def _target(distro="ubuntu", version="24.04", **overrides):
    target = SimpleNamespace(
        distro=distro,
        version=version,
        repos="main, universe",
        mirror_id="m-1",
        mirror=_mirror(),
        source_snapshot=_snapshot(),
    )
    for key, value in overrides.items():
        setattr(target, key, value)
    return target


def _run(**overrides):
    run = SimpleNamespace(
        id="run-1",
        status=tick.STATUS_QUEUED,
        targets=[_target()],
        include_cve=True,
        include_compliance=False,
        iso_label="SYSMANAGE",
        media_size_bytes=4_700_000_000,
        burn_device=None,
        worker_message_id=None,
        error_message=None,
        started_at=None,
        completed_at=None,
    )
    for key, value in overrides.items():
        setattr(run, key, value)
    return run


def _engine(**overrides):
    engine = SimpleNamespace(
        sign_manifest=lambda manifest, pem: {"payload": manifest, "sig": "abc"},
        build_snapshot_collection_run_plan=lambda req, **kw: {
            "commands": [{"argv": ["rsync"]}]
        },
        build_snapshot_multidisc_collection_plan=lambda req, **kw: {
            "commands": [{"argv": ["multidisc"]}]
        },
        build_collection_run_plan=lambda req: {"commands": [{"argv": ["legacy"]}]},
        build_iso_plan=lambda **kw: {"commands": [{"argv": ["xorriso"]}]},
        build_burn_plan=lambda **kw: {"commands": [{"argv": ["cdrecord"]}]},
    )
    for key, value in overrides.items():
        setattr(engine, key, value)
    return engine


def _settings(mirror_root_path="/srv/mirror"):
    return SimpleNamespace(mirror_root_path=mirror_root_path)


class _Dispatch:
    """Stands in for enqueue_apply_plan + register_airgap_run_correlation."""

    def __init__(self, raise_on_enqueue=False):
        self.raise_on_enqueue = raise_on_enqueue
        self.enqueued = []
        self.correlations = []

    def enqueue(self, host_id, plan, timeout):
        if self.raise_on_enqueue:
            raise RuntimeError("queue down")
        self.enqueued.append((host_id, plan, timeout))
        return "msg-1"

    def register(self, msg_id, stage, run_id, host_id):
        self.correlations.append((msg_id, stage, run_id, host_id))

    def patches(self):
        return (
            patch(
                f"{DISPATCH}.enqueue_apply_plan",
                side_effect=self.enqueue,
            ),
            patch(
                f"{DISPATCH}.register_airgap_run_correlation",
                side_effect=self.register,
            ),
        )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestManifestTargets:
    def test_only_distro_and_version_are_embedded(self):
        # The repository re-registers from this list; extra fields would be
        # signed-but-unused, and a missing one breaks ingest registration.
        run = _run(targets=[_target(), _target("debian", "13")])
        assert tick._manifest_targets(run) == [
            {"distro": "ubuntu", "version": "24.04"},
            {"distro": "debian", "version": "13"},
        ]

    def test_a_run_with_no_targets_yields_an_empty_list(self):
        assert tick._manifest_targets(_run(targets=None)) == []


class TestSignManifestOrRaw:
    def test_a_present_key_produces_a_signed_envelope(self):
        with patch(
            "backend.services.airgap_signing_service.get_collector_private_key_pem",
            return_value="PEM",
        ):
            out = tick._sign_manifest_or_raw(_engine(), {"format_version": 1})
        assert out == {"payload": {"format_version": 1}, "sig": "abc"}

    def test_an_engine_without_a_signer_degrades_to_the_bare_manifest(self):
        engine = _engine()
        del engine.sign_manifest
        manifest = {"format_version": 1}
        # Degrade-don't-crash: the ISO still builds, it just won't pass a
        # strict ingest.  Returning the same object is what makes the run
        # survive a key misconfiguration.
        assert tick._sign_manifest_or_raw(engine, manifest) is manifest

    def test_a_missing_collector_key_degrades_to_the_bare_manifest(self):
        manifest = {"format_version": 1}
        with patch(
            "backend.services.airgap_signing_service.get_collector_private_key_pem",
            return_value=None,
        ):
            assert tick._sign_manifest_or_raw(_engine(), manifest) is manifest

    def test_a_signer_that_raises_degrades_rather_than_failing_the_run(self):
        def _boom(manifest, pem):
            raise RuntimeError("bad key")

        manifest = {"format_version": 1}
        with patch(
            "backend.services.airgap_signing_service.get_collector_private_key_pem",
            return_value="PEM",
        ):
            assert (
                tick._sign_manifest_or_raw(_engine(sign_manifest=_boom), manifest)
                is manifest
            )


class TestFindCollectorHost:
    def test_the_fqdn_match_is_preferred(self):
        host = SimpleNamespace(id="host-fqdn")
        db = _FakeDb(Host=host)
        with patch("socket.getfqdn", return_value="a.example.invalid"):
            assert tick._find_collector_host(db) is host

    def test_a_bare_hostname_is_the_fallback(self):
        # Two lookups, first empty: emulate by a db that returns None once.
        class _Db(_FakeDb):
            def __init__(self):
                super().__init__()
                self.calls = 0

            def query(self, model):
                self.calls += 1
                return _FakeQuery(None if self.calls == 1 else SimpleNamespace(id="h"))

        assert tick._find_collector_host(_Db()).id == "h"

    def test_no_registered_host_at_all_returns_none(self):
        assert tick._find_collector_host(_FakeDb()) is None


class TestBuildCollectionRequest:
    def test_the_comma_separated_repo_string_is_split_and_trimmed(self):
        req = tick._build_collection_request(_run())
        assert req["distros"] == [
            {"distro": "ubuntu", "version": "24.04", "repos": ["main", "universe"]}
        ]

    def test_an_empty_repo_string_yields_no_repos(self):
        req = tick._build_collection_request(_run(targets=[_target(repos="")]))
        assert req["distros"][0]["repos"] == []

    def test_blank_entries_between_commas_are_dropped(self):
        req = tick._build_collection_request(_run(targets=[_target(repos="main,,  ,")]))
        assert req["distros"][0]["repos"] == ["main"]

    def test_the_run_level_flags_ride_along(self):
        req = tick._build_collection_request(_run())
        assert req["include_cve"] is True
        assert req["include_compliance"] is False
        assert req["iso_label"] == "SYSMANAGE"
        assert req["media_size_bytes"] == 4_700_000_000


class TestSnapshotPathsForTargets:
    def test_a_resolved_target_maps_to_its_snapshot_directory(self):
        db = _FakeDb(MirrorSettings=_settings())
        paths = tick._snapshot_paths_for_targets(db, _run())
        assert paths == {"ubuntu:24.04": "/srv/mirror/ubuntu-mirror/.snapshots/snap-1/"}

    def test_no_mirror_root_configured_yields_nothing_at_all(self):
        # Wholesale bail-out, not a per-target empty value -- the caller has
        # to check for the empty map itself, which is what it originally got
        # wrong (see the guard in _advance_queued_to_mirroring).
        assert tick._snapshot_paths_for_targets(_FakeDb(), _run()) == {}
        db = _FakeDb(MirrorSettings=_settings(mirror_root_path=""))
        assert tick._snapshot_paths_for_targets(db, _run()) == {}

    @pytest.mark.parametrize("missing", ["mirror", "source_snapshot"])
    def test_a_target_missing_its_mirror_or_snapshot_maps_to_an_empty_path(
        self, missing
    ):
        db = _FakeDb(MirrorSettings=_settings())
        run = _run(targets=[_target(**{missing: None})])
        assert tick._snapshot_paths_for_targets(db, run) == {"ubuntu:24.04": ""}


class TestTargetsSnapshotState:
    def test_a_settled_successful_snapshot_is_ready(self):
        assert tick._targets_snapshot_state(_run()) == (True, [], [])

    def test_an_in_flight_snapshot_holds_the_run_without_failing_it(self):
        run = _run(targets=[_target(mirror=_mirror(last_snapshot_message_id="m-9"))])
        ready, still, failed = tick._targets_snapshot_state(run)
        assert (ready, still, failed) == (False, ["ubuntu-mirror"], [])

    def test_a_failed_snapshot_surfaces_its_error_text(self):
        run = _run(
            targets=[
                _target(
                    mirror=_mirror(
                        last_snapshot_status="FAILED",
                        last_snapshot_error="disk full",
                    )
                )
            ]
        )
        ready, _, failed = tick._targets_snapshot_state(run)
        assert ready is False
        assert failed == [("ubuntu-mirror", "disk full")]

    def test_a_failed_snapshot_with_no_error_text_still_reports_something(self):
        run = _run(targets=[_target(mirror=_mirror(last_snapshot_status="FAILED"))])
        _, _, failed = tick._targets_snapshot_state(run)
        assert failed == [("ubuntu-mirror", "unknown")]

    def test_a_deleted_mirror_is_a_failure_not_a_wait(self):
        run = _run(targets=[_target(mirror=None)])
        ready, still, failed = tick._targets_snapshot_state(run)
        assert (ready, still) == (False, [])
        assert failed == [("<deleted mirror>", "mirror row no longer exists")]

    def test_success_with_no_snapshot_row_is_a_failure(self):
        # SUCCESS + missing row means the FK target vanished; proceeding would
        # rsync from a path built out of None.
        run = _run(targets=[_target(source_snapshot=None)])
        ready, _, failed = tick._targets_snapshot_state(run)
        assert ready is False
        assert failed == [
            ("ubuntu-mirror", "snapshot row missing despite SUCCESS status")
        ]


class TestMarkFailed:
    def test_failing_records_the_reason_and_clears_the_inflight_marker(self):
        run = _run(worker_message_id="m-1")
        tick._mark_failed(run, "because")
        assert run.status == tick.STATUS_FAILED
        assert run.error_message == "because"
        # Left set, the next tick would skip the row forever as "in flight".
        assert run.worker_message_id is None
        assert run.completed_at is not None

    def test_the_reason_is_truncated_rather_than_overflowing_the_column(self):
        run = _run()
        tick._mark_failed(run, "x" * 20000)
        assert len(run.error_message) == 8000

    def test_remarking_preserves_the_first_reason(self):
        run = _run()
        tick._mark_failed(run, "first")
        tick._mark_failed(run, "second")
        assert run.error_message == "first"


class TestResolveDispatchHost:
    def test_a_ready_run_resolves_the_mirrors_host(self):
        host = SimpleNamespace(id="host-1")
        assert tick._resolve_dispatch_host(_FakeDb(Host=host), _run()) is host

    def test_a_run_with_no_targets_fails_with_actionable_text(self):
        run = _run(targets=[])
        assert tick._resolve_dispatch_host(_FakeDb(), run) is None
        assert run.status == tick.STATUS_FAILED
        assert "no targets configured" in run.error_message

    def test_a_target_without_a_mirror_id_fails(self):
        run = _run(targets=[_target(mirror_id=None)])
        assert tick._resolve_dispatch_host(_FakeDb(), run) is None
        assert "mirror_repository row" in run.error_message

    def test_an_in_flight_snapshot_leaves_the_run_queued_to_retry(self):
        run = _run(targets=[_target(mirror=_mirror(last_snapshot_message_id="m"))])
        assert tick._resolve_dispatch_host(_FakeDb(), run) is None
        # Crucially NOT failed -- the next tick picks it up again.
        assert run.status == tick.STATUS_QUEUED
        assert run.error_message is None

    def test_a_failed_snapshot_fails_the_run(self):
        run = _run(
            targets=[
                _target(
                    mirror=_mirror(
                        last_snapshot_status="FAILED", last_snapshot_error="boom"
                    )
                )
            ]
        )
        assert tick._resolve_dispatch_host(_FakeDb(), run) is None
        assert run.status == tick.STATUS_FAILED
        assert "boom" in run.error_message

    def test_a_mirror_with_no_host_id_fails(self):
        run = _run(targets=[_target(mirror=_mirror(host_id=None))])
        assert tick._resolve_dispatch_host(_FakeDb(), run) is None
        assert "no host_id" in run.error_message

    def test_a_host_row_that_no_longer_exists_fails(self):
        run = _run()
        assert tick._resolve_dispatch_host(_FakeDb(), run) is None
        assert "no longer exists" in run.error_message


class TestComputeTargetSizing:
    def test_sizes_are_summed_and_keyed_by_distro_version(self):
        run = _run(
            targets=[
                _target(source_snapshot=_snapshot(size_bytes=10)),
                _target("debian", "13", source_snapshot=_snapshot(size_bytes=32)),
            ]
        )
        sizes, total, unknown = tick._compute_target_sizing(run)
        assert sizes == {("ubuntu", "24.04"): 10, ("debian", "13"): 32}
        assert total == 42
        assert unknown is False

    @pytest.mark.parametrize(
        "target",
        [
            _target(source_snapshot=None),
            _target(source_snapshot=_snapshot(size_bytes=None)),
        ],
        ids=["no-snapshot-row", "null-size"],
    )
    def test_an_unsized_target_flags_the_whole_run_as_unknown(self, target):
        # Unknown size must NOT be treated as zero: that would let an oversize
        # tree pass the disc-fit check and fail hours later at burn time.
        sizes, total, unknown = tick._compute_target_sizing(_run(targets=[target]))
        assert unknown is True
        assert sizes == {} and total == 0


# ---------------------------------------------------------------------------
# Plan builders
# ---------------------------------------------------------------------------


class TestBuildMultidiscPlan:
    def test_a_built_plan_is_returned(self):
        with patch(
            "backend.services.airgap_signing_service.get_collector_private_key_pem",
            return_value="PEM",
        ):
            plan = tick._build_multidisc_plan(
                _engine(), _run(), {}, {}, {("ubuntu", "24.04"): 9}, 9, 4
            )
        assert plan == {"commands": [{"argv": ["multidisc"]}]}

    def test_an_engine_predating_multidisc_fails_with_a_rebuild_instruction(self):
        engine = _engine()
        del engine.build_snapshot_multidisc_collection_plan
        run = _run()
        assert (
            tick._build_multidisc_plan(engine, run, {}, {}, {}, 9_000_000_000, 4)
            is None
        )
        assert run.status == tick.STATUS_FAILED
        assert "Rebuild the Pro+ Cython modules" in run.error_message

    def test_a_builder_that_raises_surfaces_the_message_verbatim(self):
        def _boom(req, **kwargs):
            raise RuntimeError("target ubuntu:24.04 exceeds disc size")

        run = _run()
        with patch(
            "backend.services.airgap_signing_service.get_collector_private_key_pem",
            return_value="PEM",
        ):
            assert (
                tick._build_multidisc_plan(
                    _engine(build_snapshot_multidisc_collection_plan=_boom),
                    run,
                    {},
                    {},
                    {},
                    9,
                    4,
                )
                is None
            )
        # Verbatim so the operator learns WHICH target is too big.
        assert "target ubuntu:24.04 exceeds disc size" in run.error_message

    def test_the_run_id_scopes_both_the_iso_prefix_and_the_staging_root(self):
        captured = {}

        def _build(req, **kwargs):
            captured.update(kwargs)
            return {"commands": []}

        with patch(
            "backend.services.airgap_signing_service.get_collector_private_key_pem",
            return_value="PEM",
        ):
            tick._build_multidisc_plan(
                _engine(build_snapshot_multidisc_collection_plan=_build),
                _run(),
                {},
                {},
                {},
                9,
                4,
            )
        assert captured["iso_path_prefix"] == "run-1"
        assert captured["staging_root"] == "/var/lib/sysmanage/airgap-staging/run-1"


class TestBuildSingleDiscPlan:
    def test_the_staging_root_is_scoped_by_run_id(self):
        captured = {}

        def _build(req, **kwargs):
            captured.update(kwargs)
            return {"commands": []}

        tick._build_single_disc_plan(
            _engine(build_snapshot_collection_run_plan=_build), _run(), {}, {"a": "b"}
        )
        # An unscoped root stages into .../airgap-staging/<target>/ while the
        # ISO stage bundles .../airgap-staging/<run.id>/ -- a hollow ISO.
        assert captured["staging_root"] == "/var/lib/sysmanage/airgap-staging/run-1"
        assert captured["source_snapshots"] == {"a": "b"}

    def test_an_engine_without_the_snapshot_builder_falls_back_to_legacy(self):
        engine = _engine()
        del engine.build_snapshot_collection_run_plan
        plan = tick._build_single_disc_plan(engine, _run(), {}, {})
        assert plan == {"commands": [{"argv": ["legacy"]}]}


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


def _queued_to_mirroring(run, engine=None, dispatch=None, db=None):
    dispatch = dispatch or _Dispatch()
    db = db or _FakeDb(Host=SimpleNamespace(id="host-1"), MirrorSettings=_settings())
    enq, reg = dispatch.patches()
    with patch(
        "backend.services.airgap_signing_service.get_collector_private_key_pem",
        return_value="PEM",
    ):
        with enq, reg:
            tick._advance_queued_to_mirroring(db, run, engine or _engine())
    return dispatch


class TestAdvanceQueuedToMirroring:
    def test_a_healthy_run_dispatches_and_moves_to_mirroring(self):
        run = _run()
        dispatch = _queued_to_mirroring(run)
        assert run.status == tick.STATUS_MIRRORING
        assert run.worker_message_id == "msg-1"
        assert run.started_at is not None
        assert dispatch.correlations == [("msg-1", "mirroring", "run-1", "host-1")]
        assert dispatch.enqueued[0][2] == 14400

    def test_an_unresolvable_snapshot_path_fails_before_dispatch(self):
        run = _run()
        dispatch = _queued_to_mirroring(
            run, db=_FakeDb(Host=SimpleNamespace(id="host-1"))
        )
        assert run.status == tick.STATUS_FAILED
        assert "mirror_root_path may be unset" in run.error_message
        assert dispatch.enqueued == []

    def test_a_plan_build_failure_fails_the_run(self):
        def _boom(req, **kwargs):
            raise RuntimeError("engine exploded")

        run = _run()
        _queued_to_mirroring(
            run, engine=_engine(build_snapshot_collection_run_plan=_boom)
        )
        assert run.status == tick.STATUS_FAILED
        assert "plan build failed: engine exploded" in run.error_message

    def test_a_dispatch_failure_fails_the_run_distinctly_from_a_build_failure(self):
        run = _run()
        _queued_to_mirroring(run, dispatch=_Dispatch(raise_on_enqueue=True))
        assert run.status == tick.STATUS_FAILED
        assert "plan dispatch failed" in run.error_message

    def test_an_oversize_burn_run_takes_the_multidisc_path(self):
        run = _run(
            burn_device="/dev/sr0",
            media_size_bytes=100,
            targets=[_target(source_snapshot=_snapshot(size_bytes=500))],
        )
        dispatch = _queued_to_mirroring(run)
        # Multi-disc stages AND builds inline, so it skips MIRRORING entirely.
        assert run.status == tick.STATUS_BUILDING_ISO
        assert dispatch.correlations[0][1] == "multidisc"
        assert dispatch.enqueued[0][2] == 28800

    def test_an_oversize_download_only_run_stays_single_disc(self):
        # No burn device means virtual media -- there is no physical disc to
        # fit, so splitting would fail a run that would have worked.
        run = _run(
            burn_device=None,
            media_size_bytes=100,
            targets=[_target(source_snapshot=_snapshot(size_bytes=500))],
        )
        dispatch = _queued_to_mirroring(run)
        assert run.status == tick.STATUS_MIRRORING
        assert dispatch.correlations[0][1] == "mirroring"

    def test_an_unknown_size_falls_through_to_single_disc(self):
        run = _run(
            burn_device="/dev/sr0",
            media_size_bytes=100,
            targets=[_target(source_snapshot=_snapshot(size_bytes=None))],
        )
        _queued_to_mirroring(run)
        assert run.status == tick.STATUS_MIRRORING

    def test_a_multidisc_build_failure_stops_before_dispatch(self):
        engine = _engine()
        del engine.build_snapshot_multidisc_collection_plan
        run = _run(
            burn_device="/dev/sr0",
            media_size_bytes=100,
            targets=[_target(source_snapshot=_snapshot(size_bytes=500))],
        )
        dispatch = _queued_to_mirroring(run, engine=engine)
        assert run.status == tick.STATUS_FAILED
        assert dispatch.enqueued == []

    def test_a_gated_run_never_reaches_the_plan_builder(self):
        run = _run(targets=[])
        dispatch = _queued_to_mirroring(run)
        assert dispatch.enqueued == []


def _staging_to_iso(run, engine=None, dispatch=None, db=None):
    dispatch = dispatch or _Dispatch()
    db = db or _FakeDb(Host=SimpleNamespace(id="host-1"))
    enq, reg = dispatch.patches()
    with patch(
        "backend.services.airgap_signing_service.get_collector_private_key_pem",
        return_value="PEM",
    ):
        with patch("socket.getfqdn", return_value="a.example.invalid"), enq, reg:
            tick._advance_staging_complete_to_building_iso(db, run, engine or _engine())
    return dispatch


class TestAdvanceStagingCompleteToBuildingIso:
    def test_an_iso_plan_is_dispatched_and_the_run_advances(self):
        run = _run(status=tick.STATUS_STAGING_COMPLETE)
        dispatch = _staging_to_iso(run)
        assert run.status == tick.STATUS_BUILDING_ISO
        assert run.worker_message_id == "msg-1"
        assert dispatch.correlations == [("msg-1", "building_iso", "run-1", "host-1")]
        assert dispatch.enqueued[0][2] == 7200

    def test_the_output_directory_mkdir_is_prepended(self):
        run = _run(status=tick.STATUS_STAGING_COMPLETE)
        dispatch = _staging_to_iso(run)
        commands = dispatch.enqueued[0][1]["commands"]
        # xorriso refuses to create its own output dir, so without this the
        # build fails on any collector that hasn't run one before.
        assert commands[0]["argv"] == [
            "sudo",
            "mkdir",
            "-p",
            "/var/lib/sysmanage/airgap-iso",
        ]
        assert commands[1]["argv"] == ["xorriso"]

    def test_a_plan_shape_without_commands_is_left_alone(self):
        run = _run(status=tick.STATUS_STAGING_COMPLETE)
        dispatch = _staging_to_iso(
            run, engine=_engine(build_iso_plan=lambda **kw: {"steps": []})
        )
        assert dispatch.enqueued[0][1] == {"steps": []}

    def test_the_embedded_manifest_is_signed(self):
        captured = {}

        def _build(**kwargs):
            captured.update(kwargs)
            return {"commands": []}

        _staging_to_iso(
            _run(status=tick.STATUS_STAGING_COMPLETE),
            engine=_engine(build_iso_plan=_build),
        )
        # An unsigned manifest is rejected at the air-gap crossing.
        assert captured["manifest_dict"]["sig"] == "abc"
        assert captured["manifest_dict"]["payload"]["targets"] == [
            {"distro": "ubuntu", "version": "24.04"}
        ]

    def test_no_collector_host_fails_the_run(self):
        run = _run(status=tick.STATUS_STAGING_COMPLETE)
        _staging_to_iso(run, db=_FakeDb())
        assert run.status == tick.STATUS_FAILED
        assert "could not find a registered Host" in run.error_message

    def test_a_build_failure_and_a_dispatch_failure_report_differently(self):
        def _boom(**kwargs):
            raise RuntimeError("no xorriso")

        build_run = _run(status=tick.STATUS_STAGING_COMPLETE)
        _staging_to_iso(build_run, engine=_engine(build_iso_plan=_boom))
        assert "ISO plan build failed" in build_run.error_message

        dispatch_run = _run(status=tick.STATUS_STAGING_COMPLETE)
        _staging_to_iso(dispatch_run, dispatch=_Dispatch(raise_on_enqueue=True))
        assert "ISO plan dispatch failed" in dispatch_run.error_message


class TestIsoBuiltTransitions:
    def test_no_burn_device_completes_the_run_in_place(self):
        run = _run(status=tick.STATUS_ISO_BUILT, worker_message_id=None)
        tick._advance_iso_built_to_complete(run)
        assert run.status == tick.STATUS_COMPLETE
        assert run.completed_at is not None
        assert run.worker_message_id is None

    def test_a_burn_device_dispatches_a_burn_plan(self):
        run = _run(status=tick.STATUS_ISO_BUILT, burn_device="/dev/sr0")
        dispatch = _Dispatch()
        enq, reg = dispatch.patches()
        db = _FakeDb(Host=SimpleNamespace(id="host-1"))
        with patch("socket.getfqdn", return_value="a.example.invalid"), enq, reg:
            tick._advance_iso_built_to_burning(db, run, _engine())
        assert run.status == tick.STATUS_BURNING
        assert dispatch.correlations == [("msg-1", "burning", "run-1", "host-1")]

    def test_the_burn_plan_targets_the_runs_own_iso_and_device(self):
        captured = {}

        def _build(**kwargs):
            captured.update(kwargs)
            return {"commands": []}

        run = _run(status=tick.STATUS_ISO_BUILT, burn_device="/dev/sr0")
        dispatch = _Dispatch()
        enq, reg = dispatch.patches()
        db = _FakeDb(Host=SimpleNamespace(id="host-1"))
        with patch("socket.getfqdn", return_value="a.example.invalid"), enq, reg:
            tick._advance_iso_built_to_burning(db, run, _engine(build_burn_plan=_build))
        assert captured == {
            "iso_path": "/var/lib/sysmanage/airgap-iso/run-1.iso",
            "device": "/dev/sr0",
        }

    def test_no_collector_host_fails_the_burn(self):
        run = _run(status=tick.STATUS_ISO_BUILT, burn_device="/dev/sr0")
        tick._advance_iso_built_to_burning(_FakeDb(), run, _engine())
        assert run.status == tick.STATUS_FAILED
        assert "burn plan" in run.error_message

    def test_burn_build_and_dispatch_failures_report_differently(self):
        def _boom(**kwargs):
            raise RuntimeError("no cdrecord")

        db = _FakeDb(Host=SimpleNamespace(id="host-1"))
        build_run = _run(status=tick.STATUS_ISO_BUILT, burn_device="/dev/sr0")
        with patch("socket.getfqdn", return_value="a.example.invalid"):
            tick._advance_iso_built_to_burning(
                db, build_run, _engine(build_burn_plan=_boom)
            )
        assert "burn plan build failed" in build_run.error_message

        dispatch_run = _run(status=tick.STATUS_ISO_BUILT, burn_device="/dev/sr0")
        dispatch = _Dispatch(raise_on_enqueue=True)
        enq, reg = dispatch.patches()
        with patch("socket.getfqdn", return_value="a.example.invalid"), enq, reg:
            tick._advance_iso_built_to_burning(db, dispatch_run, _engine())
        assert "burn plan dispatch failed" in dispatch_run.error_message


class TestDispatchRunAdvance:
    @pytest.mark.parametrize(
        "status,helper",
        [
            (tick.STATUS_QUEUED, "_advance_queued_to_mirroring"),
            (tick.STATUS_STAGING_COMPLETE, "_advance_staging_complete_to_building_iso"),
        ],
    )
    def test_each_status_routes_to_its_transition(self, status, helper):
        run = _run(status=status)
        with patch(f"{TICK}.{helper}") as target:
            tick._dispatch_run_advance("db", run, "engine")
        target.assert_called_once_with("db", run, "engine")

    def test_iso_built_branches_on_the_burn_device(self):
        with patch(f"{TICK}._advance_iso_built_to_burning") as burn:
            tick._dispatch_run_advance(
                "db", _run(status=tick.STATUS_ISO_BUILT, burn_device="/dev/sr0"), "e"
            )
        burn.assert_called_once()

        with patch(f"{TICK}._advance_iso_built_to_complete") as complete:
            tick._dispatch_run_advance("db", _run(status=tick.STATUS_ISO_BUILT), "e")
        complete.assert_called_once()

    @pytest.mark.parametrize(
        "status",
        [tick.STATUS_MIRRORING, tick.STATUS_BUILDING_ISO, tick.STATUS_BURNING],
    )
    def test_in_flight_statuses_are_left_to_the_result_handler(self, status):
        run = _run(status=status)
        tick._dispatch_run_advance(_FakeDb(), run, _engine())
        assert run.status == status


class TestAdvanceOneRun:
    def _summary(self):
        return {"advanced": 0, "failed": 0, "skipped_inflight": 0}

    def test_a_row_still_carrying_a_message_id_is_skipped(self):
        summary = self._summary()
        run = _run(worker_message_id="m-1")
        with patch(f"{TICK}._dispatch_run_advance") as advance:
            tick._advance_one_run(_FakeDb(), run, _engine(), summary)
        # Re-dispatching a row whose result is still in flight would run the
        # plan twice on the agent.
        advance.assert_not_called()
        assert summary["skipped_inflight"] == 1

    def test_a_successful_transition_is_tallied_as_advanced(self):
        summary = self._summary()
        with patch(f"{TICK}._dispatch_run_advance"):
            tick._advance_one_run(_FakeDb(), _run(), _engine(), summary)
        assert summary == {"advanced": 1, "failed": 0, "skipped_inflight": 0}

    def test_a_transition_that_marked_the_run_failed_is_tallied_as_failed(self):
        summary = self._summary()
        run = _run()

        def _fail(db, r, engine):
            r.status = tick.STATUS_FAILED

        with patch(f"{TICK}._dispatch_run_advance", side_effect=_fail):
            tick._advance_one_run(_FakeDb(), run, _engine(), summary)
        assert summary["failed"] == 1

    def test_an_unexpected_exception_fails_the_row_instead_of_the_batch(self):
        summary = self._summary()
        run = _run()
        with patch(f"{TICK}._dispatch_run_advance", side_effect=RuntimeError("kaboom")):
            tick._advance_one_run(_FakeDb(), run, _engine(), summary)
        assert run.status == tick.STATUS_FAILED
        assert "tick exception: kaboom" in run.error_message
        assert summary["failed"] == 1


class TestRunOneTick:
    def test_an_unlicensed_collector_engine_does_nothing_at_all(self):
        with patch(f"{TICK}.module_loader.get_module", return_value=None):
            assert tick._run_one_tick() == {
                "advanced": 0,
                "failed": 0,
                "skipped_inflight": 0,
            }

    def test_every_ready_row_is_advanced_and_the_batch_is_committed_once(self):
        rows = [_run(id="a"), _run(id="b")]
        db = _FakeDb(AirgapCollectionRun=rows)
        with patch(f"{TICK}.module_loader.get_module", return_value=_engine()):
            with patch(f"{TICK}.get_db", return_value=iter([db])):
                with patch(f"{TICK}._advance_one_run") as advance:
                    summary = tick._run_one_tick()
        assert advance.call_count == 2
        assert db.committed is True
        assert db.closed is True
        assert summary["advanced"] == 0  # the fake never tallies

    def test_no_ready_rows_means_no_commit_but_still_a_close(self):
        db = _FakeDb(AirgapCollectionRun=[])
        with patch(f"{TICK}.module_loader.get_module", return_value=_engine()):
            with patch(f"{TICK}.get_db", return_value=iter([db])):
                tick._run_one_tick()
        assert db.committed is False
        assert db.closed is True

    def test_a_batch_level_failure_rolls_back_and_still_closes(self):
        db = _FakeDb(AirgapCollectionRun=[_run()])
        with patch(f"{TICK}.module_loader.get_module", return_value=_engine()):
            with patch(f"{TICK}.get_db", return_value=iter([db])):
                with patch(
                    f"{TICK}._advance_one_run", side_effect=RuntimeError("db gone")
                ):
                    summary = tick._run_one_tick()
        # A leaked session here would exhaust the pool within minutes at a
        # 30-second cadence.
        assert db.rolled_back is True
        assert db.closed is True
        assert summary == {"advanced": 0, "failed": 0, "skipped_inflight": 0}


class TestTickService:
    @pytest.mark.asyncio
    async def test_a_tick_failure_backs_off_instead_of_killing_the_loop(self):
        calls = {"n": 0}

        def _tick():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("boom")
            return {"advanced": 1, "failed": 0, "skipped_inflight": 0}

        async def _sleep(seconds):
            if calls["n"] >= 2:
                raise _Stop()

        class _Stop(Exception):
            pass

        with patch(f"{TICK}._run_one_tick", side_effect=_tick):
            with patch(f"{TICK}.asyncio.sleep", side_effect=_sleep):
                with pytest.raises(_Stop):
                    await tick.airgap_run_tick_service()
        # Second iteration proves the first exception didn't poison the loop.
        assert calls["n"] == 2

    @pytest.mark.asyncio
    async def test_cancellation_propagates_rather_than_being_swallowed(self):
        import asyncio as _asyncio

        with patch(f"{TICK}._run_one_tick", side_effect=_asyncio.CancelledError):
            with pytest.raises(_asyncio.CancelledError):
                await tick.airgap_run_tick_service()
