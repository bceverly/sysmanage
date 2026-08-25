# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Agent results → mirror row state.

These handlers are the ONLY writer that clears the ``*_message_id`` in-flight
markers, and the frontend polls on exactly those markers.  A handler that
takes an early return before clearing one leaves the UI spinning forever on a
plan that finished minutes ago -- a bug with no log line, no failed request,
and no way to tell from the outside whether the agent is slow or the result
was dropped.  So the "cleared regardless of outcome" property is asserted
directly, not inferred.

Rows are faked: what matters is which attributes a given (action, status)
pair writes, and every one of those is a plain setattr.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.persistence import models
from backend.services import repo_mirror_result_handlers as handlers

MOD = "backend.services.repo_mirror_result_handlers"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Answers ``query(Model)`` from a dict keyed by model class name."""

    def __init__(self, **by_model):
        self._by_model = {k: list(v) for k, v in by_model.items()}
        self.added = []
        self.deleted = []
        self.committed = 0

    def query(self, model):
        return _FakeQuery(self._by_model.get(model.__name__, []))

    def add(self, row):
        self.added.append(row)

    def delete(self, row):
        self.deleted.append(row)

    def commit(self):
        self.committed += 1

    # Context-manager form, as returned by db.get_session_local()
    def __call__(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _outcome(status="succeeded", **overrides):
    out = {"status": status, "stdout": "", "stderr": "", "error": "", "commands": []}
    out.update(overrides)
    return out


def _mirror_row(**overrides):
    row = SimpleNamespace(id="m-1", consecutive_sync_failures=0)
    for action in (
        "last_sync",
        "last_snapshot",
        "last_restore",
        "last_integrity",
        "last_gc",
    ):
        for suffix in ("_at", "_status", "_error", "_message_id"):
            setattr(row, f"{action}{suffix}", "STALE")
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def _content_row(**overrides):
    row = SimpleNamespace(
        capture_status="DISPATCHED",
        last_capture_at=None,
        error_message="old",
        last_capture_message_id="msg-1",
        updated_at=None,
        registry="docker.io",
        repository="library/nginx",
        tag="1.27",
        digest=None,
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def _setup_row(**overrides):
    row = SimpleNamespace(
        host_id="h-1",
        tools=None,
        platform="Linux",
        distro="Ubuntu",
        last_check_at=None,
        last_check_message_id="msg-1",
        last_check_error="old",
        last_install_at=None,
        last_install_message_id="msg-1",
        last_install_error="old",
        install_status=None,
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


# ---------------------------------------------------------------------------
# Pure parsers
# ---------------------------------------------------------------------------


class TestParseImageDigests:
    def test_well_formed_markers_are_collected(self):
        outcome = _outcome(
            commands=[
                {
                    "stdout": (
                        "IMGDIGEST docker.io|library/nginx|1.27|sha256:aaa\n"
                        "IMGDIGEST ghcr.io|acme/api|v2|sha256:bbb\n"
                    )
                }
            ]
        )
        assert handlers._parse_image_digests(outcome) == {
            ("docker.io", "library/nginx", "1.27"): "sha256:aaa",
            ("ghcr.io", "acme/api", "v2"): "sha256:bbb",
        }

    @pytest.mark.parametrize(
        "line",
        [
            "IMGDIGEST docker.io|library/nginx|1.27",
            "IMGDIGEST docker.io|library/nginx|1.27|md5:aaa",
            "IMGDIGEST a|b|c|d|sha256:aaa",
            "digest docker.io|library/nginx|1.27|sha256:aaa",
            "",
        ],
        ids=["too-few-parts", "not-sha256", "too-many-parts", "no-marker", "blank"],
    )
    def test_malformed_lines_are_ignored_rather_than_pinning_garbage(self, line):
        # A bad pin is worse than no pin: it would be written to the row's
        # ``digest`` and used as the immutable reference from then on.
        assert (
            handlers._parse_image_digests(_outcome(commands=[{"stdout": line}])) == {}
        )

    def test_an_outcome_with_no_commands_yields_nothing(self):
        assert handlers._parse_image_digests(_outcome(commands=None)) == {}
        assert handlers._parse_image_digests({}) == {}

    def test_markers_are_gathered_across_commands(self):
        outcome = _outcome(
            commands=[
                {"stdout": "IMGDIGEST a|b|c|sha256:1"},
                {"stdout": None},
                {"stdout": "  IMGDIGEST d|e|f|sha256:2  "},
            ]
        )
        assert len(handlers._parse_image_digests(outcome)) == 2


class TestParseSetupCheckStdout:
    def test_known_tools_and_metadata_are_extracted(self):
        parsed = handlers._parse_setup_check_stdout(
            "platform=Linux\ndistro=Ubuntu\napt-mirror=present\nrsync=missing\n"
        )
        assert parsed == {
            "tools": {"apt-mirror": "present", "rsync": "missing"},
            "platform": "Linux",
            "distro": "Ubuntu",
        }

    @pytest.mark.parametrize(
        "line",
        ["unknown-tool=present", "rsync=maybe", "no-equals-sign", "  ", "rsync"],
    )
    def test_unrecognised_keys_and_values_are_dropped(self, line):
        # This dict lands in a JSON column, so anything the agent sends that
        # isn't on the allowlist must not be persisted.
        parsed = handlers._parse_setup_check_stdout(line)
        assert parsed["tools"] == {}

    def test_platform_and_distro_are_truncated(self):
        parsed = handlers._parse_setup_check_stdout(f"platform={'x' * 100}")
        assert len(parsed["platform"]) == 40

    def test_empty_or_none_stdout_parses_to_empty(self):
        for value in ("", None):
            assert handlers._parse_setup_check_stdout(value) == {
                "tools": {},
                "platform": "",
                "distro": "",
            }

    def test_a_value_containing_an_equals_sign_survives(self):
        parsed = handlers._parse_setup_check_stdout("distro=Ubuntu=24.04")
        assert parsed["distro"] == "Ubuntu=24.04"


# ---------------------------------------------------------------------------
# Mirror sync/snapshot/restore status
# ---------------------------------------------------------------------------


class TestApplyMirrorSyncStatus:
    @pytest.mark.parametrize(
        "action,prefix",
        [
            ("sync", "last_sync"),
            ("snapshot", "last_snapshot"),
            ("restore", "last_restore"),
            ("integrity_check", "last_integrity"),
            ("gc", "last_gc"),
        ],
    )
    def test_each_action_writes_only_its_own_column_group(self, action, prefix):
        row = _mirror_row()
        session = _FakeSession(MirrorRepository=[row], MirrorSnapshot=[])
        handlers._apply_mirror_sync_status(session, action, "m-1", _outcome())
        assert getattr(row, f"{prefix}_status") == "SUCCESS"
        assert getattr(row, f"{prefix}_error") is None
        assert isinstance(getattr(row, f"{prefix}_at"), datetime)
        # A failed snapshot must not overwrite a good sync -- one chip per
        # action in the UI depends on this.
        others = {
            "last_sync",
            "last_snapshot",
            "last_restore",
            "last_integrity",
            "last_gc",
        } - {prefix}
        for other in others:
            assert getattr(row, f"{other}_status") == "STALE"

    @pytest.mark.parametrize("status", ["succeeded", "failed"])
    def test_the_inflight_marker_is_cleared_either_way(self, status):
        row = _mirror_row()
        session = _FakeSession(MirrorRepository=[row], MirrorSnapshot=[])
        handlers._apply_mirror_sync_status(session, "gc", "m-1", _outcome(status))
        # Left set, the UI spins forever on a finished plan.
        assert row.last_gc_message_id is None

    def test_a_failure_records_the_last_failing_commands_stderr(self):
        row = _mirror_row()
        session = _FakeSession(MirrorRepository=[row], MirrorSnapshot=[])
        outcome = _outcome(
            "failed",
            commands=[
                {"success": True, "stderr": ""},
                {"success": False, "stderr": "disk full"},
            ],
        )
        handlers._apply_mirror_sync_status(session, "gc", "m-1", outcome)
        assert row.last_gc_status == "FAILED"
        assert row.last_gc_error == "disk full"

    def test_consecutive_sync_failures_accumulate_and_reset(self):
        row = _mirror_row(consecutive_sync_failures=2)
        session = _FakeSession(MirrorRepository=[row], MirrorSnapshot=[])
        handlers._apply_mirror_sync_status(session, "sync", "m-1", _outcome("failed"))
        # tick_mirrors backs off on this counter; without the increment a
        # hopeless mirror is redispatched every cron tick forever.
        assert row.consecutive_sync_failures == 3
        handlers._apply_mirror_sync_status(session, "sync", "m-1", _outcome())
        assert row.consecutive_sync_failures == 0

    def test_a_null_failure_counter_starts_at_one(self):
        row = _mirror_row(consecutive_sync_failures=None)
        session = _FakeSession(MirrorRepository=[row], MirrorSnapshot=[])
        handlers._apply_mirror_sync_status(session, "sync", "m-1", _outcome("failed"))
        assert row.consecutive_sync_failures == 1

    def test_only_sync_touches_the_failure_counter(self):
        row = _mirror_row(consecutive_sync_failures=5)
        session = _FakeSession(MirrorRepository=[row], MirrorSnapshot=[])
        handlers._apply_mirror_sync_status(session, "gc", "m-1", _outcome("failed"))
        assert row.consecutive_sync_failures == 5

    def test_a_blank_mirror_id_is_a_no_op(self):
        session = _FakeSession(MirrorRepository=[_mirror_row()])
        handlers._apply_mirror_sync_status(session, "sync", "", _outcome())
        assert session.committed == 0

    def test_a_deleted_mirror_drops_the_result_quietly(self):
        session = _FakeSession(MirrorRepository=[])
        handlers._apply_mirror_sync_status(session, "sync", "m-1", _outcome())
        assert session.added == []

    def test_an_action_with_no_column_group_is_refused(self):
        row = _mirror_row()
        session = _FakeSession(MirrorRepository=[row])
        handlers._apply_mirror_sync_status(session, "teleport", "m-1", _outcome())
        assert row.last_sync_status == "STALE"


class TestPostSnapshotOutcome:
    def test_rsync_stats_fill_the_placeholder_row(self):
        placeholder = SimpleNamespace(size_bytes=None, file_count=None)
        session = _FakeSession(MirrorSnapshot=[placeholder])
        outcome = _outcome(
            commands=[
                {
                    "description": "rsync live tree into snapshot",
                    "success": True,
                    "stdout": "Number of files: 1,234\nTotal file size: 5,678 bytes\n",
                }
            ]
        )
        handlers._post_snapshot_outcome(session, "m-1", True, outcome)
        assert placeholder.file_count == 1234
        # size_bytes feeds the air-gap disc-fit decision; a NULL here makes
        # the whole run fall through to single-disc.
        assert placeholder.size_bytes == 5678

    def test_a_failed_snapshot_deletes_the_placeholder(self):
        placeholder = SimpleNamespace(size_bytes=None, file_count=None)
        session = _FakeSession(MirrorSnapshot=[placeholder])
        handlers._post_snapshot_outcome(session, "m-1", False, _outcome("failed"))
        # Otherwise the snapshots list accumulates ghosts that later runs
        # would FK to and try to rsync from.
        assert session.deleted == [placeholder]

    def test_no_placeholder_row_is_a_no_op(self):
        session = _FakeSession(MirrorSnapshot=[])
        handlers._post_snapshot_outcome(session, "m-1", True, _outcome())
        assert session.deleted == []

    def test_a_failed_rsync_command_contributes_no_stats(self):
        placeholder = SimpleNamespace(size_bytes=None, file_count=None)
        session = _FakeSession(MirrorSnapshot=[placeholder])
        outcome = _outcome(
            commands=[
                {
                    "description": "rsync live tree",
                    "success": False,
                    "stdout": "Number of files: 9\nTotal file size: 9 bytes\n",
                }
            ]
        )
        handlers._post_snapshot_outcome(session, "m-1", True, outcome)
        assert placeholder.size_bytes is None

    def test_unparseable_stats_leave_the_row_untouched(self):
        placeholder = SimpleNamespace(size_bytes=None, file_count=None)
        session = _FakeSession(MirrorSnapshot=[placeholder])
        outcome = _outcome(
            commands=[{"description": "rsync", "success": True, "stdout": "done"}]
        )
        handlers._post_snapshot_outcome(session, "m-1", True, outcome)
        assert (placeholder.size_bytes, placeholder.file_count) == (None, None)

    def test_a_non_rsync_command_is_skipped(self):
        placeholder = SimpleNamespace(size_bytes=None, file_count=None)
        session = _FakeSession(MirrorSnapshot=[placeholder])
        outcome = _outcome(
            commands=[
                {
                    "description": "mkdir snapshot dir",
                    "success": True,
                    "stdout": "Number of files: 7\n",
                }
            ]
        )
        handlers._post_snapshot_outcome(session, "m-1", True, outcome)
        assert placeholder.file_count is None


class TestPostRestoreOutcome:
    def test_it_is_deliberately_a_no_op(self):
        session = _FakeSession()
        handlers._post_restore_outcome(session, "m-1", True)
        assert (session.added, session.deleted, session.committed) == ([], [], 0)


# ---------------------------------------------------------------------------
# Content capture
# ---------------------------------------------------------------------------


class TestApplySnapCaptureResult:
    def test_a_successful_capture_moves_the_whole_dispatched_set(self):
        rows = [_content_row(), _content_row()]
        session = _FakeSession(MirrorSnapContent=rows)
        handlers._apply_snap_capture_result(session, "m-1", _outcome())
        for row in rows:
            assert row.capture_status == "CAPTURED"
            assert row.error_message is None
            assert row.last_capture_message_id is None
            assert isinstance(row.last_capture_at, datetime)

    def test_a_failed_capture_records_the_error_on_every_row(self):
        row = _content_row()
        session = _FakeSession(MirrorSnapContent=[row])
        outcome = _outcome(
            "failed", commands=[{"success": False, "stderr": "snap store 503"}]
        )
        handlers._apply_snap_capture_result(session, "m-1", outcome)
        assert row.capture_status == "FAILED"
        assert row.error_message == "snap store 503"

    def test_a_blank_mirror_id_or_no_dispatched_rows_is_a_no_op(self):
        row = _content_row()
        handlers._apply_snap_capture_result(
            _FakeSession(MirrorSnapContent=[row]), "", _outcome()
        )
        assert row.capture_status == "DISPATCHED"
        handlers._apply_snap_capture_result(
            _FakeSession(MirrorSnapContent=[]), "m-1", _outcome()
        )


class TestApplyImageCaptureResult:
    def test_a_matching_digest_pins_the_row(self):
        row = _content_row()
        session = _FakeSession(MirrorImageContent=[row])
        outcome = _outcome(
            commands=[{"stdout": "IMGDIGEST docker.io|library/nginx|1.27|sha256:aaa"}]
        )
        handlers._apply_image_capture_result(session, "m-1", outcome)
        assert row.capture_status == "CAPTURED"
        assert row.digest == "sha256:aaa"

    def test_an_unmatched_row_keeps_its_previous_pin(self):
        row = _content_row(tag="1.28", digest="sha256:old")
        session = _FakeSession(MirrorImageContent=[row])
        outcome = _outcome(
            commands=[{"stdout": "IMGDIGEST docker.io|library/nginx|1.27|sha256:aaa"}]
        )
        handlers._apply_image_capture_result(session, "m-1", outcome)
        # Overwriting with a digest for a DIFFERENT tag would silently
        # repoint the pin at the wrong image.
        assert row.digest == "sha256:old"

    def test_a_failed_capture_parses_no_digests_at_all(self):
        row = _content_row()
        session = _FakeSession(MirrorImageContent=[row])
        outcome = _outcome(
            "failed",
            error="pull denied",
            commands=[
                {
                    "success": False,
                    "stderr": "unauthorized",
                    "stdout": "IMGDIGEST docker.io|library/nginx|1.27|sha256:aaa",
                }
            ],
        )
        handlers._apply_image_capture_result(session, "m-1", outcome)
        assert row.capture_status == "FAILED"
        # A digest echoed by a plan that then failed is not a valid pin.
        assert row.digest is None
        assert row.error_message == "unauthorized"

    def test_a_silent_command_failure_still_names_the_step(self):
        row = _content_row()
        session = _FakeSession(MirrorImageContent=[row])
        outcome = _outcome(
            "failed",
            error="pull denied",
            commands=[
                {
                    "success": False,
                    "stderr": "",
                    "description": "skopeo copy",
                    "returncode": 1,
                }
            ],
        )
        handlers._apply_image_capture_result(session, "m-1", outcome)
        # The failing STEP wins over the plan-level error: "skopeo copy exited
        # 1" tells the operator where it broke, "pull denied" does not.
        assert row.error_message == "skopeo copy exited 1 with no stderr"

    def test_a_blank_mirror_id_or_no_dispatched_rows_is_a_no_op(self):
        row = _content_row()
        handlers._apply_image_capture_result(
            _FakeSession(MirrorImageContent=[row]), "", _outcome()
        )
        assert row.capture_status == "DISPATCHED"
        handlers._apply_image_capture_result(
            _FakeSession(MirrorImageContent=[]), "m-1", _outcome()
        )


# ---------------------------------------------------------------------------
# Setup check / install
# ---------------------------------------------------------------------------


class TestApplyMirrorSetupCheck:
    def test_an_existing_row_is_updated_in_place(self):
        row = _setup_row()
        session = _FakeSession(MirrorSetupStatus=[row])
        outcome = _outcome(stdout="rsync=present\nplatform=FreeBSD\n")
        handlers._apply_mirror_setup_check(session, "h-1", outcome)
        assert session.added == []
        assert row.tools == {"rsync": "present"}
        assert row.platform == "FreeBSD"
        assert row.last_check_message_id is None
        assert row.last_check_error is None

    def test_a_missing_row_is_created(self):
        session = _FakeSession(MirrorSetupStatus=[])
        handlers._apply_mirror_setup_check(
            session, "h-1", _outcome(stdout="rsync=present")
        )
        assert len(session.added) == 1
        assert isinstance(session.added[0], models.MirrorSetupStatus)

    def test_absent_metadata_does_not_erase_what_was_known(self):
        row = _setup_row(platform="Linux", distro="Ubuntu")
        session = _FakeSession(MirrorSetupStatus=[row])
        handlers._apply_mirror_setup_check(
            session, "h-1", _outcome(stdout="rsync=present")
        )
        # A probe that couldn't report its platform shouldn't blank the field
        # the last successful probe filled in.
        assert (row.platform, row.distro) == ("Linux", "Ubuntu")

    @pytest.mark.parametrize(
        "outcome_kwargs,expected",
        [
            ({"stderr": "no such host"}, "no such host"),
            ({"stderr": "", "error": "timed out"}, "timed out"),
            ({"stderr": "", "error": ""}, "probe failed"),
        ],
    )
    def test_a_failed_probe_always_records_some_error_text(
        self, outcome_kwargs, expected
    ):
        row = _setup_row()
        session = _FakeSession(MirrorSetupStatus=[row])
        handlers._apply_mirror_setup_check(
            session, "h-1", _outcome("failed", stdout="", **outcome_kwargs)
        )
        assert row.last_check_error == expected
        # Cleared even on failure, or the card never leaves "checking...".
        assert row.last_check_message_id is None


class TestApplyMirrorSetupInstall:
    def test_success_stamps_the_status_and_clears_the_error(self):
        row = _setup_row()
        session = _FakeSession(MirrorSetupStatus=[row])
        handlers._apply_mirror_setup_install(session, "h-1", _outcome())
        assert row.install_status == "succeeded"
        assert row.last_install_error is None
        assert row.last_install_message_id is None

    def test_failure_records_the_reason(self):
        row = _setup_row()
        session = _FakeSession(MirrorSetupStatus=[row])
        handlers._apply_mirror_setup_install(
            session, "h-1", _outcome("failed", stderr="", error="apt lock held")
        )
        assert row.install_status == "failed"
        assert row.last_install_error == "apt lock held"

    def test_a_missing_row_is_created(self):
        session = _FakeSession(MirrorSetupStatus=[])
        handlers._apply_mirror_setup_install(session, "h-1", _outcome())
        assert len(session.added) == 1


class TestQueueFollowupSetupCheck:
    def test_the_probe_is_dispatched_correlated_and_stamped(self):
        row = _setup_row()
        session = _FakeSession(MirrorSetupStatus=[row])
        engine = SimpleNamespace(build_mirror_setup_check_plan=lambda: {"commands": []})
        with patch(f"{MOD}.module_loader.get_module", return_value=engine):
            with patch(
                "backend.services.proplus_dispatch.enqueue_apply_plan",
                return_value="msg-9",
            ):
                with patch(
                    "backend.services.proplus_dispatch._register_correlation"
                ) as register:
                    handlers._queue_followup_setup_check("h-1", session)
        register.assert_called_once_with(
            "msg-9", "repo_mirror_op", "setup_check:", "h-1"
        )
        # Without the stamp the frontend's poll loop sees both markers clear
        # and stops before the auto-probe result lands.
        assert row.last_check_message_id == "msg-9"
        assert session.committed == 1

    def test_an_unlicensed_engine_queues_nothing(self):
        session = _FakeSession(MirrorSetupStatus=[_setup_row()])
        with patch(f"{MOD}.module_loader.get_module", return_value=None):
            with patch(
                "backend.services.proplus_dispatch.enqueue_apply_plan"
            ) as enqueue:
                handlers._queue_followup_setup_check("h-1", session)
        enqueue.assert_not_called()

    def test_a_dispatch_failure_is_contained(self):
        session = _FakeSession(MirrorSetupStatus=[_setup_row()])
        engine = SimpleNamespace(build_mirror_setup_check_plan=lambda: {"commands": []})
        with patch(f"{MOD}.module_loader.get_module", return_value=engine):
            with patch(
                "backend.services.proplus_dispatch.enqueue_apply_plan",
                side_effect=RuntimeError("queue down"),
            ):
                # The install itself already succeeded; a failed convenience
                # probe must not turn that into an error.
                handlers._queue_followup_setup_check("h-1", session)

    def test_no_status_row_means_nothing_to_stamp(self):
        session = _FakeSession(MirrorSetupStatus=[])
        engine = SimpleNamespace(build_mirror_setup_check_plan=lambda: {"commands": []})
        with patch(f"{MOD}.module_loader.get_module", return_value=engine):
            with patch(
                "backend.services.proplus_dispatch.enqueue_apply_plan",
                return_value="msg-9",
            ):
                with patch("backend.services.proplus_dispatch._register_correlation"):
                    handlers._queue_followup_setup_check("h-1", session)
        assert session.committed == 0


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


class TestApplyRepoMirrorOpResult:
    def _route(self, primary_id, outcome=None, session=None):
        session = session or _FakeSession()
        with patch(f"{MOD}.db.get_session_local", return_value=session):
            handlers._apply_repo_mirror_op_result(
                primary_id, "h-1", outcome or _outcome()
            )
        return session

    @pytest.mark.parametrize(
        "action", ["sync", "snapshot", "restore", "integrity_check", "gc"]
    )
    def test_the_row_actions_route_to_the_sync_status_handler(self, action):
        with patch(f"{MOD}._apply_mirror_sync_status") as target:
            session = self._route(f"{action}:m-1")
        target.assert_called_once()
        assert target.call_args[0][1:3] == (action, "m-1")
        assert session.committed == 1

    @pytest.mark.parametrize(
        "action,helper",
        [
            ("snap_capture", "_apply_snap_capture_result"),
            ("image_capture", "_apply_image_capture_result"),
        ],
    )
    def test_the_content_actions_route_to_their_handlers(self, action, helper):
        with patch(f"{MOD}.{helper}") as target:
            self._route(f"{action}:m-1")
        assert target.call_args[0][1] == "m-1"

    @pytest.mark.parametrize(
        "action,helper",
        [
            ("setup_check", "_apply_mirror_setup_check"),
            ("setup_install", "_apply_mirror_setup_install"),
        ],
    )
    def test_the_host_actions_route_on_host_id_not_mirror_id(self, action, helper):
        with patch(f"{MOD}.{helper}") as target:
            with patch(f"{MOD}._queue_followup_setup_check"):
                self._route(f"{action}:")
        assert target.call_args[0][1] == "h-1"

    def test_a_primary_id_without_a_colon_is_treated_as_a_bare_action(self):
        with patch(f"{MOD}._apply_mirror_setup_check") as target:
            with patch(f"{MOD}._queue_followup_setup_check"):
                self._route("setup_check")
        target.assert_called_once()

    def test_a_successful_install_chains_a_probe(self):
        with patch(f"{MOD}._apply_mirror_setup_install"):
            with patch(f"{MOD}._queue_followup_setup_check") as followup:
                self._route("setup_install:")
        followup.assert_called_once()

    def test_a_failed_install_chains_nothing(self):
        with patch(f"{MOD}._apply_mirror_setup_install"):
            with patch(f"{MOD}._queue_followup_setup_check") as followup:
                self._route("setup_install:", _outcome("failed"))
        followup.assert_not_called()

    @pytest.mark.parametrize("action", ["default_apply", "default_revert"])
    def test_default_assignment_results_are_informational_only(self, action):
        # The assignment was committed before the plan was queued, so there is
        # nothing to write back -- but the row must still commit cleanly.
        session = self._route(f"{action}:m-1", _outcome("failed", stderr="nope"))
        assert session.committed == 1

    def test_an_unknown_action_commits_nothing(self):
        session = self._route("teleport:m-1")
        assert session.committed == 0
