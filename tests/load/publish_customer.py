# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""One simulated customer server for the license-publish scenario.

Runs the REAL engine update path of the server under test
(``ModuleLoader.update_modules``: versions call, download, hash check,
staging, swap, cache record, load) against the scenario's fake license
server, in a process of its own with its own database and modules
directory -- exactly what a customer server has.  The one stand-in is the
signature check: test bundles cannot carry the release signature, and that
check is tested on its own (``tests/test_licensing_module_update_safety.py``).

Prints one JSON line per sample to stdout: whether the engine is loaded and
its cached file is on disk, the cached version, and update results.  Usage
(the scenario starts it): publish_customer.py CONFIG MODULE CYCLE_SECONDS
[legacy]

``legacy`` is the negative control: before each download the customer does
what the code did before Phase 22.4 -- unload the engine and delete its
cached copy -- so the scenario can show it would catch that.
"""

import asyncio
import json
import os
import random
import sys
import time
from unittest.mock import patch


async def main(config_path: str, module_code: str, cycle: float, legacy: bool) -> None:
    os.environ["SYSMANAGE_CONFIG_PATH"] = config_path
    os.environ["SYSMANAGE_MULTITENANCY"] = "false"
    os.environ["SYSMANAGE_DISABLE_EMAIL"] = "true"
    os.environ["OTEL_ENABLED"] = "false"
    # pylint: disable=import-outside-toplevel
    from backend.licensing.module_loader import ModuleLoader
    from backend.persistence import db
    from backend.persistence.models import ProPlusModuleCache

    ProPlusModuleCache.__table__.create(bind=db.get_engine(), checkfirst=True)
    loader = ModuleLoader()
    started = time.monotonic()

    def emit(**fields):
        fields["t"] = round(time.monotonic() - started, 2)
        print(json.dumps(fields), flush=True)

    async def sample():
        while True:
            path = loader._get_cached_module_path(  # pylint: disable=protected-access
                module_code
            )
            emit(
                kind="sample",
                loaded=loader.get_module(module_code) is not None,
                on_disk=bool(path and os.path.exists(path)),
                version=loader._get_cached_module_version(  # pylint: disable=protected-access
                    module_code
                ),
            )
            await asyncio.sleep(0.25)

    if legacy:
        download = loader._download_and_cache_module  # pylint: disable=protected-access

        async def delete_first(code, version=None):
            if loader._get_cached_module_version(
                code
            ):  # pylint: disable=protected-access
                loader.unload_module(code)
                loader._remove_cached_module(code)  # pylint: disable=protected-access
            return await download(code, version)

        loader._download_and_cache_module = (
            delete_first  # pylint: disable=protected-access
        )

    sampler = asyncio.create_task(sample())
    with patch("backend.licensing.module_loader.verify_module_dir"):
        while True:
            try:
                results = await loader.update_modules()
                emit(
                    kind="cycle",
                    results={
                        k: v for k, v in results.items() if not k.endswith("_plugin")
                    },
                )
            except Exception as exc:  # pylint: disable=broad-except
                emit(kind="cycle", error=str(exc))
            # Each customer on its own clock, as the 22.4 jitter makes them.
            await asyncio.sleep(cycle * random.uniform(0.75, 1.25))  # nosec B311
    sampler.cancel()  # pragma: no cover


if __name__ == "__main__":
    asyncio.run(
        main(sys.argv[1], sys.argv[2], float(sys.argv[3]), "legacy" in sys.argv[4:])
    )
