# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The server caps glibc's malloc arenas, and only on glibc."""

from unittest import mock

from backend.startup import malloc_arenas


def test_operator_setting_is_left_alone(monkeypatch):
    monkeypatch.setenv("MALLOC_ARENA_MAX", "8")
    with mock.patch.object(malloc_arenas.ctypes, "CDLL") as cdll:
        assert malloc_arenas.cap_arenas() is False
    cdll.assert_not_called()


def test_not_glibc_is_left_alone(monkeypatch):
    monkeypatch.delenv("MALLOC_ARENA_MAX", raising=False)
    with mock.patch.object(
        malloc_arenas.platform, "system", return_value="OpenBSD"
    ), mock.patch.object(malloc_arenas.ctypes, "CDLL") as cdll:
        assert malloc_arenas.cap_arenas() is False
    cdll.assert_not_called()


def test_glibc_gets_two_arenas(monkeypatch):
    monkeypatch.delenv("MALLOC_ARENA_MAX", raising=False)
    libc = mock.Mock()
    libc.mallopt.return_value = 1
    with mock.patch.object(
        malloc_arenas.platform, "system", return_value="Linux"
    ), mock.patch.object(
        malloc_arenas.platform, "libc_ver", return_value=("glibc", "2.39")
    ), mock.patch.object(
        malloc_arenas.ctypes, "CDLL", return_value=libc
    ):
        assert malloc_arenas.cap_arenas() is True
    libc.mallopt.assert_called_once_with(malloc_arenas.M_ARENA_MAX, 2)


def test_no_mallopt_is_not_an_error(monkeypatch):
    monkeypatch.delenv("MALLOC_ARENA_MAX", raising=False)
    with mock.patch.object(
        malloc_arenas.platform, "system", return_value="Linux"
    ), mock.patch.object(
        malloc_arenas.platform, "libc_ver", return_value=("glibc", "2.39")
    ), mock.patch.object(
        malloc_arenas.ctypes, "CDLL", side_effect=OSError("no libc")
    ):
        assert malloc_arenas.cap_arenas() is False
