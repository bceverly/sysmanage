"""
Tests for backend.api.package_host_selector.

Pure helper module — score_host / select_best_host need no DB; find_hosts_for_os
needs only a mocked db.query chain.
"""

import json
from unittest.mock import MagicMock, patch

from backend.api.package_host_selector import (
    find_hosts_for_os,
    score_host,
    select_best_host,
)

# ---------------------------------------------------------------------------
# score_host
# ---------------------------------------------------------------------------


def _host(enabled_shells=None):
    h = MagicMock()
    h.enabled_shells = enabled_shells
    return h


class TestScoreHost:
    def test_no_shells_field_returns_base_score(self):
        assert score_host(_host(None)) == 1

    def test_invalid_json_falls_back_to_base_score(self):
        assert score_host(_host("<<not json>>")) == 1

    def test_each_recognised_optional_manager_adds_one(self):
        shells = ["bash", "homebrew", "snap", "pip", "ruby"]
        # 3 recognised optional managers → base 1 + 3 = 4.
        assert score_host(_host(json.dumps(shells))) == 4

    def test_unrecognised_shells_give_only_base(self):
        shells = ["bash", "zsh", "fish"]
        assert score_host(_host(json.dumps(shells))) == 1

    def test_case_insensitive_match(self):
        # "CHOCO" should match "choco" pattern.
        assert score_host(_host(json.dumps(["CHOCO"]))) == 2


# ---------------------------------------------------------------------------
# select_best_host
# ---------------------------------------------------------------------------


class TestSelectBestHost:
    def test_empty_list_returns_none(self):
        assert select_best_host([]) is None

    def test_single_host_returns_that_host(self):
        h = _host()
        assert select_best_host([h]) is h

    def test_picks_highest_scoring_when_random_at_top(self):
        # Force random to choose the last cumulative bucket.
        a = _host(json.dumps([]))  # score 1
        b = _host(json.dumps(["snap"]))  # score 2
        with patch(
            "backend.api.package_host_selector.random.uniform",
            return_value=2.5,  # > 1+score_a = 1, falls into b's bucket.
        ):
            assert select_best_host([a, b]) is b

    def test_zero_total_score_falls_back_to_random_choice(self):
        # Both hosts have score 0 — but score_host always returns at least 1.
        # We patch score_host to force the zero-total branch.
        a = _host()
        b = _host()
        with patch(
            "backend.api.package_host_selector.score_host", return_value=0
        ), patch("backend.api.package_host_selector.random.choice", return_value=a):
            assert select_best_host([a, b]) is a

    def test_returns_first_host_when_random_picks_lowest_bucket(self):
        a = _host(json.dumps([]))  # score 1
        b = _host(json.dumps([]))  # score 1
        with patch(
            "backend.api.package_host_selector.random.uniform", return_value=0.0
        ):
            # uniform=0 should fall into a's bucket.
            assert select_best_host([a, b]) is a


# ---------------------------------------------------------------------------
# find_hosts_for_os
# ---------------------------------------------------------------------------


def _query_returning(rows):
    """Make db.query(...).filter(...).filter(...).all() return rows."""
    db = MagicMock()
    chain = db.query.return_value.filter.return_value
    chain.filter.return_value.all.return_value = rows
    chain.all.return_value = rows
    return db


class TestFindHostsForOs:
    def test_ubuntu_path(self):
        host = MagicMock()
        db = _query_returning([host])
        assert find_hosts_for_os(db, "Ubuntu", "24.04") == [host]

    def test_macos_path(self):
        host = MagicMock()
        db = _query_returning([host])
        assert find_hosts_for_os(db, "macOS", "15.6") == [host]

    def test_freebsd_path(self):
        host = MagicMock()
        db = _query_returning([host])
        assert find_hosts_for_os(db, "FreeBSD", "14.2") == [host]

    def test_windows_path(self):
        host = MagicMock()
        db = _query_returning([host])
        assert find_hosts_for_os(db, "Windows", "11") == [host]

    def test_unknown_os_falls_through_to_direct_match(self):
        host = MagicMock()
        db = _query_returning([host])
        assert find_hosts_for_os(db, "Plan9", "4ed") == [host]

    def test_no_matches_returns_empty(self):
        db = _query_returning([])
        assert find_hosts_for_os(db, "Ubuntu", "24.04") == []
