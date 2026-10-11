# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
The asset-tag naming scheme (Phase 23.2 S3).

Admins describe their scheme with a BUILDER -- prefix, separator, a zero-padded
number of N digits, optional suffix -- not a regex box: "GDR-000042".  An
advanced mode takes a regex for schemes the builder cannot express.

Changing the scheme REPORTS the tags that no longer conform; it never rewrites
them.  Every check returns a reason code (the UI renders it in the user's
language), never prose.

The advanced regex is an admin's own text run on the server, so it is matched
with the ``regex`` module and a hard timeout: a pattern with catastrophic
backtracking costs one refused check, not a stalled worker.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List, Optional

import regex  # timeout-capable matching for admin-supplied patterns

MODE_BUILDER = "builder"
MODE_REGEX = "regex"

MAX_TAG_LENGTH = 128
MAX_AFFIX_LENGTH = 32
MAX_PATTERN_LENGTH = 256
MIN_DIGITS, MAX_DIGITS = 1, 12
SEPARATORS = ("", "-", "_", ".")
REGEX_TIMEOUT_SECONDS = 0.05

# Every tag, whatever the scheme: printable, no spaces, starts with a letter
# or digit -- it is typed, printed on labels and searched for.
_TAG_CHARS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_AFFIX_CHARS = re.compile(r"^[A-Za-z0-9]*$")

# Reason codes.
OK = None
EMPTY = "empty"
TOO_LONG = "too_long"
BAD_CHARS = "bad_characters"
NO_MATCH = "does_not_match_scheme"
TIMEOUT = "scheme_timeout"


@dataclass
class Scheme:
    """One tenant's scheme.  ``enforce`` False: report only, accept anything
    that passes the basic character rules."""

    mode: str = MODE_BUILDER
    prefix: str = ""
    separator: str = "-"
    digits: int = 6
    suffix: str = ""
    pattern: str = ""
    enforce: bool = False

    @classmethod
    def from_dict(cls, data: Optional[Dict]) -> "Scheme":
        data = data or {}
        return cls(
            mode=str(data.get("mode") or MODE_BUILDER),
            prefix=str(data.get("prefix") or ""),
            separator=str(
                data.get("separator") if data.get("separator") is not None else "-"
            ),
            # ``or 6`` would turn an explicit 0 into 6 and hide an invalid scheme.
            digits=int(data["digits"]) if data.get("digits") is not None else 6,
            suffix=str(data.get("suffix") or ""),
            pattern=str(data.get("pattern") or ""),
            enforce=bool(data.get("enforce", False)),
        )

    def to_dict(self) -> Dict:
        return asdict(self)


def scheme_problems(scheme: Scheme) -> List[str]:
    """Why ``scheme`` cannot be saved, as field codes; [] when it can."""
    problems: List[str] = []
    if scheme.mode not in (MODE_BUILDER, MODE_REGEX):
        problems.append("mode")
        return problems
    if scheme.mode == MODE_BUILDER:
        for name, value in (("prefix", scheme.prefix), ("suffix", scheme.suffix)):
            if len(value) > MAX_AFFIX_LENGTH or not _AFFIX_CHARS.match(value):
                problems.append(name)
        if scheme.separator not in SEPARATORS:
            problems.append("separator")
        if not MIN_DIGITS <= scheme.digits <= MAX_DIGITS:
            problems.append("digits")
        if len(render(scheme, 0)) > MAX_TAG_LENGTH:
            problems.append("too_long")
    else:
        if not scheme.pattern or len(scheme.pattern) > MAX_PATTERN_LENGTH:
            problems.append("pattern")
        else:
            try:
                regex.compile(scheme.pattern)
            except regex.error:
                problems.append("pattern")
    return problems


def _builder_regex(scheme: Scheme) -> "re.Pattern[str]":
    # Built from validated, escaped parts: no admin text is a regex here.
    tail = (
        f"{re.escape(scheme.separator)}{re.escape(scheme.suffix)}"
        if scheme.suffix
        else ""
    )
    return re.compile(
        f"^{re.escape(scheme.prefix)}{re.escape(scheme.separator) if scheme.prefix else ''}"
        f"(\\d{{{scheme.digits}}}){tail}$"
    )


def render(scheme: Scheme, number: int) -> str:
    """The builder's tag for ``number`` ("GDR-000042")."""
    head = f"{scheme.prefix}{scheme.separator}" if scheme.prefix else ""
    tail = f"{scheme.separator}{scheme.suffix}" if scheme.suffix else ""
    return f"{head}{number:0{scheme.digits}d}{tail}"


def check(scheme: Scheme, tag: Optional[str]) -> Optional[str]:
    """None when ``tag`` is acceptable under ``scheme``; else a reason code.

    The character rules always apply; the scheme itself only when enforced."""
    text = (tag or "").strip()
    if not text:
        return EMPTY
    if len(text) > MAX_TAG_LENGTH:
        return TOO_LONG
    if not _TAG_CHARS.match(text):
        return BAD_CHARS
    if not scheme.enforce:
        return OK
    return conformance(scheme, text)


def conformance(scheme: Scheme, tag: str) -> Optional[str]:
    """None when ``tag`` matches the scheme, enforced or not; else a code."""
    if scheme.mode == MODE_REGEX:
        try:
            matched = regex.fullmatch(
                scheme.pattern, tag, timeout=REGEX_TIMEOUT_SECONDS
            )
        except TimeoutError:
            return TIMEOUT
        except regex.error:
            return NO_MATCH
        return OK if matched else NO_MATCH
    return OK if _builder_regex(scheme).match(tag) else NO_MATCH


def number_of(scheme: Scheme, tag: str) -> Optional[int]:
    """The sequence number in a builder-scheme tag; None if it does not fit."""
    if scheme.mode != MODE_BUILDER:
        return None
    match = _builder_regex(scheme).match(tag or "")
    return int(match.group(1)) if match else None


def next_free(scheme: Scheme, tags: Iterable[str]) -> Optional[str]:
    """The tag after the highest one in use; None in regex mode (there is no
    number to count) or when the digits are exhausted."""
    if scheme.mode != MODE_BUILDER:
        return None
    used = [n for n in (number_of(scheme, t) for t in tags) if n is not None]
    following = (max(used) + 1) if used else 1
    if following >= 10**scheme.digits:
        return None
    return render(scheme, following)


def examples(scheme: Scheme) -> Dict[str, List[str]]:
    """Tags that pass and tags that fail, to show beside the builder."""
    if scheme.mode != MODE_BUILDER:
        return {"pass": [], "fail": []}
    head = f"{scheme.prefix}{scheme.separator}" if scheme.prefix else ""
    tail = f"{scheme.separator}{scheme.suffix}" if scheme.suffix else ""
    failing = [f"{head}{'4' * (scheme.digits + 1)}{tail}"]  # a digit too many
    if scheme.digits > 1:
        failing.append(f"{head}{'4' * (scheme.digits - 1)}{tail}")  # one too few
    if scheme.prefix:
        failing.append(render(Scheme(**{**scheme.to_dict(), "prefix": "XYZ"}), 42))
    return {
        "pass": [render(scheme, 1), render(scheme, 42)],
        # Only genuine failures, in case a choice of affix makes one pass.
        "fail": [t for t in failing if conformance(scheme, t) is not OK],
    }


def nonconforming(scheme: Scheme, tags: Iterable[str]) -> List[str]:
    """Existing tags the scheme rejects -- reported, never rewritten."""
    return [t for t in tags if t and conformance(scheme, t) is not OK]
