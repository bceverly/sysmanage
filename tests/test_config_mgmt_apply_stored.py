# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Applying a STORED profile (Phase 20.1, Enterprise).

The point of storing a profile is that applying it links back: the run row
records which profile produced it, so history can answer "what did this
profile do across the fleet". That linkage is the behaviour under test.

Ad-hoc apply is open source and must keep working with no licence, so the
gate lives on the stored path only -- not on the route.
"""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.api import config_mgmt_runs as api

PROFILE_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")


def profile(**over):
    base = {
        "id": PROFILE_ID,
        "name": "baseline",
        "engine": "ansible-core",
        "content": "- hosts: all\n",
        "is_active": True,
    }
    base.update(over)
    return SimpleNamespace(**base)


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_a, **_k):
        return self

    def first(self):
        return self._rows[0] if self._rows else None


class _Session:
    def __init__(self, rows):
        self._rows = rows

    def query(self, _entity):
        return _Query(self._rows)


def _licensed():
    """require_module is a no-op when the module is present."""
    return patch.object(api, "require_module", lambda _code: None)


class TestLoadStoredProfile:
    def test_a_missing_profile_is_404(self):
        with _licensed():
            with pytest.raises(HTTPException) as err:
                api._load_stored_profile(_Session([]), str(PROFILE_ID))
        assert err.value.status_code == 404

    def test_a_malformed_id_is_400_not_500(self):
        with _licensed():
            with pytest.raises(HTTPException) as err:
                api._load_stored_profile(_Session([]), "not-a-uuid")
        assert err.value.status_code == 400

    def test_an_inactive_profile_is_refused(self):
        # Otherwise the active flag is decorative: somebody took this profile
        # out of service and it would still run.
        with _licensed():
            with pytest.raises(HTTPException) as err:
                api._load_stored_profile(
                    _Session([profile(is_active=False)]), str(PROFILE_ID)
                )
        assert err.value.status_code == 400

    def test_the_stored_path_demands_the_licence(self):
        def refuse(_code):
            raise HTTPException(status_code=402, detail="unlicensed")

        with patch.object(api, "require_module", refuse):
            with pytest.raises(HTTPException) as err:
                api._load_stored_profile(_Session([profile()]), str(PROFILE_ID))
        assert err.value.status_code == 402

    def test_an_active_profile_comes_back(self):
        with _licensed():
            got = api._load_stored_profile(_Session([profile()]), str(PROFILE_ID))
        assert got.name == "baseline"


class TestDscResources:
    def test_a_non_dsc_profile_has_none(self):
        assert api._dsc_resources(profile()) is None

    def test_a_dsc_body_is_parsed_into_a_list(self):
        body = json.dumps([{"type": "Microsoft.Windows/Registry"}])
        got = api._dsc_resources(profile(engine="dsc", content=body))
        assert isinstance(got, list)
        assert got[0]["type"] == "Microsoft.Windows/Registry"

    def test_unparsable_json_is_a_400_naming_the_profile(self):
        # Failing here beats failing on the host hours later with no context.
        with pytest.raises(HTTPException) as err:
            api._dsc_resources(profile(engine="dsc", content="{not json"))
        assert err.value.status_code == 400
        assert "baseline" in err.value.detail

    def test_a_json_object_is_refused_because_dsc_wants_an_array(self):
        with pytest.raises(HTTPException) as err:
            api._dsc_resources(profile(engine="dsc", content='{"a": 1}'))
        assert err.value.status_code == 400
        assert "baseline" in err.value.detail
