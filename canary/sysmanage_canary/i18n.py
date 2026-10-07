# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The canary's messages in its configured language.  Small JSON catalogs
ship inside the package (``locales/<language>.json``); a key missing from a
language falls back to English, and a missing value placeholder never makes
a message fail to render (an alert must always go out)."""

import json
import os
from typing import Dict

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")
_CACHE: Dict[str, Dict[str, str]] = {}


def _catalog(language: str) -> Dict[str, str]:
    if language not in _CACHE:
        try:
            with open(
                os.path.join(_DIR, f"{language}.json"), encoding="utf-8"
            ) as handle:
                _CACHE[language] = json.load(handle)
        except (OSError, ValueError):
            _CACHE[language] = {}
    return _CACHE[language]


class _Lenient(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def t(language: str, key: str, **params) -> str:
    """Message ``key`` in ``language`` (English when missing), formatted."""
    text = _catalog(language).get(key) or _catalog("en").get(key) or key
    try:
        return text.format_map(_Lenient(params))
    except (ValueError, IndexError):
        return text
