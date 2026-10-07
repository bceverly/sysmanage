# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""``sysmanage-canary`` command line.

sysmanage-canary [--config PATH]          run (the service does this)
sysmanage-canary --check-config           validate the file and exit
sysmanage-canary --test-email             send a test email and exit
sysmanage-canary --once                   run every enabled check once
"""

import argparse
import logging
import sys

from sysmanage_canary import __version__, alerts, checks, config as cfg
from sysmanage_canary.i18n import t
from sysmanage_canary.runner import Canary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="sysmanage-canary",
        description="An outside watcher for a SysManage server.",
    )
    parser.add_argument("--config", default=cfg.DEFAULT_PATH)
    parser.add_argument("--check-config", action="store_true")
    parser.add_argument("--test-email", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    try:
        config = cfg.load(args.config)
    except cfg.ConfigError as exc:
        # A bad file is refused as a whole, never half-applied.
        print(t("en", "cli.config_bad"), file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2
    lang = config["language"]
    warning = cfg.permission_warning(args.config)
    if warning:
        print(f"WARNING: {warning}", file=sys.stderr)
    enabled = [n for n, c in config["checks"].items() if c.get("enabled")]

    if args.check_config:
        print(t(lang, "cli.config_ok", checks=len(enabled)))
        return 0
    if args.test_email:
        try:
            alerts.send(config, t(lang, "email.test.subject", server=config["server_name"]),
                        t(lang, "email.test.body"))  # fmt: skip
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(t(lang, "cli.test_failed", error=exc), file=sys.stderr)
            return 1
        print(t(lang, "cli.test_sent", to=", ".join(alerts.recipients(config))))
        return 0
    if args.once:
        failed = 0
        for name in enabled:
            result = checks.run(name, config)
            failed += not result.ok
            mark = "ok  " if result.ok else "FAIL"
            print(
                f"[{mark}] {t(lang, f'check.{name}')}: {t(lang, result.key, **result.params)}"
            )
        return 1 if failed else 0
    Canary(config).forever()
    return 0  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main())
