# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A host's own temperature warning limit (2026-10-19).

Some hosts run hot by design -- laptops serving with their lids closed sit
at their CPU's "high" mark all day.  An administrator can give such a host
its own warning limit; every temperature sensor on it is then judged against
that instead of the limit the hardware declares.  The device's CRITICAL
limit is never overridden: at or above it a sensor still fails, and a
sensor whose critical limit is at or below the host's keeps its own warning
limit, so it is never pushed from healthy straight to failed.

The agent judged the sensor; this re-judges it on the server from the
reading in its metrics, so no agent change is needed and a new or cleared
limit applies from the next report on.  History is never rewritten.
"""

from typing import Any, Dict, Optional

# The settable range, in C.  Below 30 C nearly every sensor would warn;
# above 125 C is past any CPU's critical limit.
LIMIT_RANGE_C = (30.0, 125.0)

# Marks the limit in a sensor's metrics as the host's, not the device's.
HOST_SOURCE = "host"

_TEMPERATURE_CODES = {"temperature_high", "temperature_critical"}


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _only_temperature_reasons(comp: Dict[str, Any]) -> bool:
    return all(r.get("code") in _TEMPERATURE_CODES for r in comp["reasons"])


def apply_limit(comp: Dict[str, Any], limit: Optional[float]) -> Dict[str, Any]:
    """``comp`` judged against the host's ``limit``; unchanged without one,
    for anything but a temperature sensor, or when it already failed."""
    metrics = comp["metrics"]
    temperature = metrics.get("temperature_c")
    if (
        limit is None
        or comp["kind"] != "sensor"
        or comp["state"] == "failed"
        or not _number(temperature)
        or not _only_temperature_reasons(comp)
    ):
        return comp
    critical = metrics.get("critical_c")
    if _number(critical) and temperature >= critical:
        # Critical is the hardware's and always wins, whoever set a limit.
        reasons = [
            {"code": "temperature_critical", "value": temperature, "limit": critical}
        ]
        return dict(comp, state="failed", reasons=reasons)
    if _number(critical) and limit >= critical:
        # A host limit at or above this sensor's critical point would take
        # it straight from healthy to failed with no warning at all (an
        # NVMe drive critical at 84.8 C under a 95 C laptop limit): it
        # keeps the limit its hardware declares.
        return comp
    judged = dict(metrics, high_c=limit, high_source=HOST_SOURCE)
    if _number(metrics.get("high_c")):
        judged["device_high_c"] = metrics["high_c"]
    if temperature >= limit:
        state = "warning"
        reasons = [{"code": "temperature_high", "value": temperature, "limit": limit}]
    else:
        state, reasons = "ok", []
    return dict(comp, state=state, reasons=reasons, metrics=judged)


def valid_limit(value: Optional[float]) -> bool:
    """None clears the limit; otherwise it must be in ``LIMIT_RANGE_C``."""
    if value is None:
        return True
    return _number(value) and LIMIT_RANGE_C[0] <= value <= LIMIT_RANGE_C[1]
