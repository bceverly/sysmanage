# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""GeoLite2 download (production, 2026-10-17): MaxMind answers with a 302 to
signed storage, which was never followed, so no database ever arrived; and
httpx logged the full URL -- license key included -- at INFO."""

import logging
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import httpx

from backend.services import geolocation_service as geo
from backend.startup import logging_config

KEY = "SECRET-LICENSE-KEY"


class _Response:
    status_code = 200

    @staticmethod
    def iter_bytes(chunk_size=65536):  # pylint: disable=unused-argument
        yield b"tarball-bytes"


def test_the_download_follows_maxmind_redirects(tmp_path):
    seen = {}

    @contextmanager
    def fake_stream(method, url, **kwargs):
        seen.update(kwargs, method=method, url=url)
        yield _Response()

    with patch.object(geo.httpx, "stream", fake_stream):
        path = geo._download_maxmind_tarball(  # pylint: disable=protected-access
            geo._MAXMIND_DOWNLOAD_URL.format(key=KEY),
            str(tmp_path),  # pylint: disable=protected-access
        )
    assert seen["follow_redirects"] is True
    assert path and Path(path).read_bytes() == b"tarball-bytes"


def test_a_network_error_never_logs_the_key(tmp_path, caplog):
    def broken_stream(*_args, **_kwargs):
        raise httpx.ConnectError(f"cannot reach https://x/?license_key={KEY}")

    with patch.object(geo.httpx, "stream", broken_stream), caplog.at_level(
        logging.WARNING
    ):
        assert (
            geo._download_maxmind_tarball(  # pylint: disable=protected-access
                geo._MAXMIND_DOWNLOAD_URL.format(key=KEY),
                str(tmp_path),  # pylint: disable=protected-access
            )
            is None
        )
    assert KEY not in caplog.text
    assert "ConnectError" in caplog.text


def test_http_client_request_urls_are_not_logged_at_info():
    logging_config.configure_logging()
    for name in logging_config.QUIET_HTTP_LOGGERS:
        assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING
