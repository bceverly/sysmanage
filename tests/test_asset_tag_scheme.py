# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The asset-tag scheme engine (Phase 23.2 S3)."""

import time

import pytest

from backend.services import asset_tag_scheme as s

GDR = s.Scheme(prefix="GDR", separator="-", digits=6, enforce=True)


def test_the_builder_renders_zero_padded_tags():
    assert s.render(GDR, 42) == "GDR-000042"
    assert s.render(s.Scheme(prefix="", digits=4), 7) == "0007"
    assert (
        s.render(s.Scheme(prefix="IT", separator=".", digits=3, suffix="LT"), 5)
        == "IT.005.LT"
    )


@pytest.mark.parametrize(
    "tag,reason",
    [
        ("GDR-000042", None),
        ("GDR-42", s.NO_MATCH),
        ("GDR-0000042", s.NO_MATCH),
        ("XYZ-000042", s.NO_MATCH),
        ("gdr-000042", s.NO_MATCH),
        ("", s.EMPTY),
        ("   ", s.EMPTY),
        ("GDR 000042", s.BAD_CHARS),
        ("-GDR000042", s.BAD_CHARS),
        ("G" * 200, s.TOO_LONG),
    ],
)
def test_an_enforced_builder_scheme_checks_each_tag(tag, reason):
    assert s.check(GDR, tag) == reason


def test_an_unenforced_scheme_accepts_any_well_formed_tag_but_still_reports():
    lenient = s.Scheme(prefix="GDR", enforce=False)
    assert s.check(lenient, "anything-123") is None
    assert s.check(lenient, "has space") == s.BAD_CHARS
    assert s.nonconforming(lenient, ["GDR-000001", "anything-123"]) == ["anything-123"]


def test_next_free_follows_the_highest_conforming_number():
    tags = ["GDR-000041", "GDR-000007", "legacy-99", "GDR-000002"]
    assert s.next_free(GDR, tags) == "GDR-000042"
    assert s.next_free(GDR, []) == "GDR-000001"
    assert s.next_free(s.Scheme(digits=1), ["9"]) is None  # digits exhausted


def test_examples_pass_and_fail_as_labeled():
    shown = s.examples(GDR)
    assert all(s.conformance(GDR, t) is None for t in shown["pass"])
    assert shown["fail"] and all(
        s.conformance(GDR, t) is not None for t in shown["fail"]
    )


def test_changing_the_scheme_reports_and_never_rewrites():
    tags = ["GDR-000001", "OLD-1"]
    assert s.nonconforming(GDR, tags) == ["OLD-1"]
    assert tags == ["GDR-000001", "OLD-1"]


@pytest.mark.parametrize(
    "scheme,fields",
    [
        (s.Scheme(prefix="G D"), ["prefix"]),
        (s.Scheme(separator="|"), ["separator"]),
        (s.Scheme(digits=0), ["digits"]),
        (s.Scheme(digits=13), ["digits"]),
        (s.Scheme(mode="regex", pattern=""), ["pattern"]),
        (s.Scheme(mode="regex", pattern="([a-z"), ["pattern"]),
        (s.Scheme(mode="nonsense"), ["mode"]),
        (GDR, []),
    ],
)
def test_scheme_problems_name_the_bad_fields(scheme, fields):
    assert s.scheme_problems(scheme) == fields


def test_the_advanced_regex_mode():
    scheme = s.Scheme(mode="regex", pattern=r"[A-Z]{3}-\d{4}", enforce=True)
    assert s.check(scheme, "ABC-1234") is None
    assert s.check(scheme, "ABC-123") == s.NO_MATCH
    assert s.next_free(scheme, ["ABC-1234"]) is None
    assert s.examples(scheme) == {"pass": [], "fail": []}


def test_a_catastrophic_admin_regex_times_out_instead_of_hanging():
    scheme = s.Scheme(mode="regex", pattern=r"(a|aa)+c", enforce=True)
    started = time.monotonic()
    assert s.check(scheme, "a" * 100 + "b") == s.TIMEOUT
    assert time.monotonic() - started < 2


def test_an_explicit_zero_digits_is_rejected_not_defaulted():
    scheme = s.Scheme.from_dict({"prefix": "GDR", "digits": 0})
    assert scheme.digits == 0
    assert s.scheme_problems(scheme) == ["digits"]
