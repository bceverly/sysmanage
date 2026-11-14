# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Burning an air-gap disc SET with one optical drive.

A run with a burn device whose mirrors do not fit one disc is built as
``<run>-disc-1.iso`` .. ``<run>-disc-N.iso``.  The burn used to always point
at ``<run>.iso`` -- a file a set never has -- so a set could not be burned at
all.  Now the tick burns disc 1, the result handler parks the run at
AWAITING_MEDIA ("disc 1 of N burned, load a blank disc"), the operator
confirms (POST /runs/{id}/next-disc puts it back at ISO_BUILT), and the tick
burns the next disc, until the last disc makes the run COMPLETE.

These tests pin each hop: which file and which correlation stage the tick
burns, what the result handler does with a success or a failure of disc K,
that a plain ``burning`` result (a plan dispatched before this change) still
completes, and that the tick never dispatches while the run waits for media.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.services import airgap_result_handlers as handlers
from backend.services import airgap_run_tick as tick
from tests.test_airgap_run_tick import (
    TICK,
    _Dispatch,
    _engine,
    _FakeDb,
    _run,
)

ISO = "/var/lib/sysmanage/airgap-iso"


def _burn(run, engine=None):
    """Run ISO_BUILT -> BURNING through the tick with a fake host + queue."""
    captured = {}

    def _build(**kwargs):
        captured.update(kwargs)
        return {"commands": []}

    dispatch = _Dispatch()
    enq, reg = dispatch.patches()
    db = _FakeDb(Host=SimpleNamespace(id="host-1"))
    with patch("socket.getfqdn", return_value="a.example.invalid"), enq, reg:
        tick._advance_iso_built_to_burning(
            db, run, engine or _engine(build_burn_plan=_build)
        )
    return captured, dispatch


class TestBurnStages:
    @pytest.mark.parametrize(
        "stage,disc",
        [
            ("burning", 0),
            ("burning_disc_1", 1),
            ("burning_disc_12", 12),
            ("burning_disc_0", None),
            ("burning_disc_x", None),
            ("mirroring", None),
            ("building_iso", None),
        ],
    )
    def test_the_disc_is_read_back_from_the_stage(self, stage, disc):
        assert tick.parse_burn_stage(stage) == disc

    def test_a_disc_stage_round_trips(self):
        assert tick.parse_burn_stage(tick.burn_disc_stage(3)) == 3


class TestRunDiscCount:
    def test_the_recorded_count_wins(self):
        assert tick.run_disc_count(_run(disc_count=3)) == 3

    def test_an_unrecorded_count_is_read_from_the_disc_files(self, tmp_path):
        for n in (1, 2):
            (tmp_path / f"run-1-disc-{n}.iso").write_bytes(b"")
        with patch(f"{TICK}.ISO_OUTPUT_DIR", str(tmp_path)):
            assert tick.run_disc_count(_run(disc_count=None)) == 2

    def test_no_record_and_no_disc_files_is_one_disc(self, tmp_path):
        with patch(f"{TICK}.ISO_OUTPUT_DIR", str(tmp_path)):
            assert tick.run_disc_count(_run()) == 1


class TestPlanDiscCount:
    def test_a_single_disc_plan_is_one_disc(self):
        assert tick._plan_disc_count({"commands": []}, False) == 1

    def test_the_multidisc_builder_says_how_many_discs(self):
        assert tick._plan_disc_count({"metadata": {"disc_count": 3}}, True) == 3

    @pytest.mark.parametrize(
        "plan", [{}, {"metadata": None}, {"metadata": {"disc_count": "3"}}, None]
    )
    def test_a_plan_that_does_not_say_leaves_it_to_the_disc_files(self, plan):
        assert tick._plan_disc_count(plan, True) == 0

    def test_dispatch_records_the_set_size_and_resets_the_burn_count(self):
        from tests.test_airgap_run_tick import _queued_to_mirroring, _target

        run = _run(
            burn_device="/dev/sr0",
            media_size_bytes=1000,
            targets=[_target(), _target(distro="debian", version="12")],
            burned_disc_count=2,
        )
        engine = _engine(
            build_snapshot_multidisc_collection_plan=lambda req, **kw: {
                "commands": [],
                "metadata": {"disc_count": 2},
            }
        )
        _queued_to_mirroring(run, engine=engine)
        assert run.status == tick.STATUS_BUILDING_ISO
        assert run.disc_count == 2
        assert run.burned_disc_count == 0

    def test_a_single_disc_dispatch_records_one_disc(self):
        from tests.test_airgap_run_tick import _queued_to_mirroring

        run = _run()
        _queued_to_mirroring(run)
        assert run.status == tick.STATUS_MIRRORING
        assert run.disc_count == 1


class TestTickBurnsTheNextDisc:
    def test_a_single_disc_still_burns_the_runs_own_iso(self):
        captured, dispatch = _burn(
            _run(status=tick.STATUS_ISO_BUILT, burn_device="/dev/sr0", disc_count=1)
        )
        assert captured["iso_path"] == f"{ISO}/run-1.iso"
        assert dispatch.correlations[0][1] == "burning"

    def test_a_set_burns_disc_one_first(self):
        run = _run(
            status=tick.STATUS_ISO_BUILT,
            burn_device="/dev/sr0",
            disc_count=3,
            burned_disc_count=0,
        )
        captured, dispatch = _burn(run)
        assert captured == {"iso_path": f"{ISO}/run-1-disc-1.iso", "device": "/dev/sr0"}
        assert dispatch.correlations == [("msg-1", "burning_disc_1", "run-1", "host-1")]
        assert run.status == tick.STATUS_BURNING
        assert run.worker_message_id == "msg-1"

    def test_after_two_discs_the_third_is_burned(self):
        run = _run(
            status=tick.STATUS_ISO_BUILT,
            burn_device="/dev/sr0",
            disc_count=3,
            burned_disc_count=2,
        )
        captured, dispatch = _burn(run)
        assert captured["iso_path"] == f"{ISO}/run-1-disc-3.iso"
        assert dispatch.correlations[0][1] == "burning_disc_3"

    def test_a_set_that_is_all_burned_completes_instead_of_burning_again(self):
        run = _run(
            status=tick.STATUS_ISO_BUILT,
            burn_device="/dev/sr0",
            disc_count=2,
            burned_disc_count=2,
        )
        with patch(f"{TICK}._advance_iso_built_to_burning") as burn:
            tick._dispatch_run_advance(_FakeDb(), run, _engine())
        burn.assert_not_called()
        assert run.status == tick.STATUS_COMPLETE

    def test_a_run_awaiting_media_is_never_dispatched(self):
        run = _run(
            status=tick.STATUS_AWAITING_MEDIA,
            burn_device="/dev/sr0",
            disc_count=2,
            burned_disc_count=1,
        )
        with patch(f"{TICK}._advance_iso_built_to_burning") as burn:
            tick._dispatch_run_advance(_FakeDb(), run, _engine())
        burn.assert_not_called()
        assert run.status == tick.STATUS_AWAITING_MEDIA

    def test_the_tick_query_leaves_awaiting_media_out(self):
        seen = {}

        class _Query:
            def filter(self, clause):
                seen["values"] = set(clause.right.value)
                return self

            def all(self):
                return []

        db = SimpleNamespace(query=lambda model: _Query(), close=lambda: None)
        with patch(f"{TICK}.module_loader.get_module", return_value=_engine()):
            with patch(f"{TICK}.get_db", return_value=iter([db])):
                tick._run_one_tick()
        assert tick.STATUS_ISO_BUILT in seen["values"]
        assert tick.STATUS_AWAITING_MEDIA not in seen["values"]
        assert tick.STATUS_BURNING not in seen["values"]


# ---------------------------------------------------------------------------
# Result handler
# ---------------------------------------------------------------------------


class _Session:
    def __init__(self, run):
        self.run = run
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def query(self, _model):
        return self

    def filter(self, *_args):
        return self

    def first(self):
        return self.run

    def commit(self):
        self.committed = True


def _result(run, stage, succeeded=True, stderr="growisofs: no media"):
    outcome = {"status": "succeeded" if succeeded else "failed"}
    if not succeeded:
        outcome["commands"] = [{"success": False, "stderr": stderr}]
    session = _Session(run)
    with patch.object(handlers.db, "get_session_local", return_value=lambda: session):
        handlers._apply_airgap_run_result(f"{stage}:{run.id}", "host-1", outcome)
    return session


def _burning(**overrides):
    base = {
        "status": tick.STATUS_BURNING,
        "burn_device": "/dev/sr0",
        "worker_message_id": "msg-1",
        "disc_count": 3,
        "burned_disc_count": 0,
    }
    base.update(overrides)
    return _run(**base)


class TestBurnResults:
    def test_disc_one_of_three_waits_for_the_next_blank_disc(self):
        run = _burning()
        session = _result(run, "burning_disc_1")
        assert run.status == tick.STATUS_AWAITING_MEDIA
        assert run.burned_disc_count == 1
        assert run.worker_message_id is None
        assert run.completed_at is None
        assert session.committed is True

    def test_the_last_disc_completes_the_run(self):
        run = _burning(burned_disc_count=2)
        _result(run, "burning_disc_3")
        assert run.status == tick.STATUS_COMPLETE
        assert run.burned_disc_count == 3
        assert run.completed_at is not None

    def test_a_single_disc_burn_completes_and_counts_its_disc(self):
        run = _burning(disc_count=1)
        _result(run, "burning")
        assert run.status == tick.STATUS_COMPLETE
        assert run.burned_disc_count == 1

    def test_a_plain_burning_result_from_before_disc_by_disc_still_completes(self):
        # A plan dispatched by the previous release carries plain
        # ``burning`` even on a set; it must finish the run as it used to.
        run = _burning(disc_count=None)
        _result(run, "burning")
        assert run.status == tick.STATUS_COMPLETE
        assert run.completed_at is not None

    def test_a_late_duplicate_result_never_lowers_the_burn_count(self):
        run = _burning(burned_disc_count=2)
        _result(run, "burning_disc_1")
        assert run.burned_disc_count == 2
        assert run.status == tick.STATUS_AWAITING_MEDIA

    def test_a_failed_disc_fails_the_run_and_names_the_disc(self):
        run = _burning(burned_disc_count=1)
        _result(run, "burning_disc_2", succeeded=False)
        assert run.status == "FAILED"
        assert run.error_message == ("burn of disc 2 of 3 failed: growisofs: no media")
        assert run.burned_disc_count == 1
        assert run.completed_at is not None
        assert run.worker_message_id is None

    def test_a_failed_single_disc_burn_keeps_the_agent_text_alone(self):
        run = _burning(disc_count=1)
        _result(run, "burning", succeeded=False)
        assert run.status == "FAILED"
        assert run.error_message == "growisofs: no media"

    def test_a_failed_iso_build_is_not_mistaken_for_a_burn(self):
        run = _burning(status=tick.STATUS_BUILDING_ISO)
        _result(run, "building_iso", succeeded=False)
        assert run.error_message == "growisofs: no media"
