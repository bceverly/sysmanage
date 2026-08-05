# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Tests for the per-channel agent-install mirror API (Phase 12).

The engine is mocked, but deliberately NOT with a bare ``MagicMock``: the
whole point of this endpoint is that it defers the channel list and the URL
validation to the provisioning engine — the same code that renders the install
commands — so a permissive mock would let the tests pass while the real
pairing was broken.  ``_engine()`` therefore stands in a fake with the real
engine's semantics.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from backend.api import airgap_agent_mirrors as mirrors_module

_CHANNELS = [
    "apk",
    "brew",
    "copr",
    "freebsd-pkg",
    "netbsd-pkgin",
    "obs",
    "openbsd-pkg",
    "ppa",
    "sysmanage-apt",
    "winget",
]
_SAFE = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._~:/?#@%+=-"
)
_APT = "https://mirror.corp.example/sysmanage/apt"


@contextmanager
def _engine(loaded=True):
    fake = MagicMock()
    fake.agent_mirror_channels.return_value = list(_CHANNELS)
    fake.is_valid_mirror_url.side_effect = (
        lambda u: bool(u)
        and u.startswith(("http://", "https://", "ftp://", "file://"))
        and not (set(u) - _SAFE)
    )

    def _resolver(name):
        if name == "provisioning_engine" and loaded:
            return fake
        return None

    with patch.object(
        mirrors_module.module_loader, "get_module", side_effect=_resolver
    ):
        yield


class TestAuth:
    def test_anonymous_rejected(self, client):
        r = client.get("/api/v1/airgap/agent-mirrors")
        assert r.status_code in (401, 403)


class TestList:
    def test_empty_list_still_advertises_configurable_channels(
        self, client, auth_headers
    ):
        with _engine():
            r = client.get("/api/v1/airgap/agent-mirrors", headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["mirrors"] == []
        assert "copr" in body["available_channels"]

    def test_aur_is_never_offered(self, client, auth_headers):
        """An Arch package is built on the target — there is nothing to
        mirror, and offering it would look like a working air-gap config."""
        with _engine():
            r = client.get("/api/v1/airgap/agent-mirrors", headers=auth_headers)
        assert "aur" not in r.json()["available_channels"]

    def test_no_engine_advertises_nothing_rather_than_a_hardcoded_list(
        self, client, auth_headers
    ):
        """A fallback list here would let an operator configure channels that
        nothing will ever read."""
        with _engine(loaded=False):
            r = client.get("/api/v1/airgap/agent-mirrors", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["available_channels"] == []


class TestUpsert:
    def test_create_then_read_back(self, client, auth_headers):
        with _engine():
            r = client.put(
                "/api/v1/airgap/agent-mirrors/copr",
                json={"mirror_url": _APT, "channel": "copr"},
                headers=auth_headers,
            )
            assert r.status_code == 200, r.text
            assert r.json()["mirror_url"] == _APT

            listed = client.get(
                "/api/v1/airgap/agent-mirrors", headers=auth_headers
            ).json()["mirrors"]
        assert [m["channel"] for m in listed] == ["copr"]

    def test_second_put_updates_rather_than_duplicating(self, client, auth_headers):
        """One row per channel — a second row would make which mirror wins
        depend on row order."""
        second = "https://other.corp.example/rpm"
        with _engine():
            for url in (_APT, second):
                client.put(
                    "/api/v1/airgap/agent-mirrors/obs",
                    json={"mirror_url": url, "channel": "obs"},
                    headers=auth_headers,
                )
            listed = client.get(
                "/api/v1/airgap/agent-mirrors", headers=auth_headers
            ).json()["mirrors"]
        rows = [m for m in listed if m["channel"] == "obs"]
        assert len(rows) == 1
        assert rows[0]["mirror_url"] == second

    def test_unmirrorable_channel_rejected(self, client, auth_headers):
        with _engine():
            r = client.put(
                "/api/v1/airgap/agent-mirrors/aur",
                json={"mirror_url": _APT, "channel": "aur"},
                headers=auth_headers,
            )
        assert r.status_code == 400

    def test_shell_unsafe_url_rejected_at_config_time(self, client, auth_headers):
        """This URL would otherwise be interpolated into a root shell command
        on every host the site provisions.  Catching it when the operator
        types it is the difference between a form error and RCE."""
        with _engine():
            r = client.put(
                "/api/v1/airgap/agent-mirrors/ppa",
                json={
                    "mirror_url": "https://mirror.example/a; rm -rf /",
                    "channel": "ppa",
                },
                headers=auth_headers,
            )
        assert r.status_code == 400

    def test_scheme_relative_url_rejected(self, client, auth_headers):
        with _engine():
            r = client.put(
                "/api/v1/airgap/agent-mirrors/ppa",
                json={"mirror_url": "mirror.example/apt", "channel": "ppa"},
                headers=auth_headers,
            )
        assert r.status_code == 400

    def test_402_without_the_engine(self, client, auth_headers):
        with _engine(loaded=False):
            r = client.put(
                "/api/v1/airgap/agent-mirrors/ppa",
                json={"mirror_url": _APT, "channel": "ppa"},
                headers=auth_headers,
            )
        assert r.status_code == 402


class TestDelete:
    def test_delete_removes_the_row(self, client, auth_headers):
        with _engine():
            client.put(
                "/api/v1/airgap/agent-mirrors/apk",
                json={"mirror_url": _APT, "channel": "apk"},
                headers=auth_headers,
            )
            r = client.delete("/api/v1/airgap/agent-mirrors/apk", headers=auth_headers)
            assert r.status_code == 200
            listed = client.get(
                "/api/v1/airgap/agent-mirrors", headers=auth_headers
            ).json()["mirrors"]
        assert [m for m in listed if m["channel"] == "apk"] == []

    def test_delete_unknown_channel_is_404(self, client, auth_headers):
        with _engine():
            r = client.delete(
                "/api/v1/airgap/agent-mirrors/winget", headers=auth_headers
            )
        assert r.status_code == 404
