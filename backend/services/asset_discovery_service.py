# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Store one agent's network-discovery report (Phase 21.6 S1).

The engine decides (sanitize, identify, correlate, merge); this module only
reads the rows it needs and writes the result. Three writes per report:

  * ``DiscoveredAsset``            -- one row per DEVICE, upserted by identity;
  * ``DiscoveredAssetSighting``    -- one row per (device, observing agent);
  * ``NetworkDiscoveryObserver``   -- the agent's networks and blind spots.

THE FLEET LOOKUP IS BOUNDED BY THE REPORT
-----------------------------------------
Every agent reports every few minutes, so loading every interface of every host
per report would scale with fleet x fleet. The engine names the MACs and IPs
that could possibly match (``lookup_keys``) and only those interface rows are
read. MACs are stored as the agent sent them -- ``aa:bb:..`` from Linux,
``AA-BB-..`` from Windows -- so each key is queried in every spelling; a
managed Windows host must not appear unmanaged because of a separator.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from backend.persistence.models import (
    DiscoveredAsset,
    DiscoveredAssetSighting,
    NetworkDiscoveryObserver,
    NetworkInterface,
)
from backend.services import asset_discovery_shim as shim
from backend.services import oui

logger = logging.getLogger(__name__)

_CHUNK = 500


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _chunks(items: List[str]) -> Iterable[List[str]]:
    for start in range(0, len(items), _CHUNK):
        yield items[start : start + _CHUNK]


def _spellings(mac: str) -> List[str]:
    dashed = mac.replace(":", "-")
    return [mac, mac.upper(), dashed, dashed.upper()]


def _fleet_rows(db, keys: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    """The interface rows that could match this report, as plain dicts."""
    columns = (
        NetworkInterface.host_id,
        NetworkInterface.mac_address,
        NetworkInterface.ipv4_address,
        NetworkInterface.ipv6_address,
    )
    rows = []
    macs = [s for mac in keys["macs"] for s in _spellings(mac)]
    for chunk in _chunks(macs):
        rows += db.query(*columns).filter(NetworkInterface.mac_address.in_(chunk)).all()
    # Tap ports: the guest shares everything but the first octet. Few per
    # report (only fe:-prefixed MACs produce one), so one LIKE each is fine.
    for suffix in keys["mac_suffixes"]:
        patterns = ["%" + s for s in (suffix, suffix.replace(":", "-"))]
        rows += (
            db.query(*columns)
            .filter(or_(*[NetworkInterface.mac_address.ilike(p) for p in patterns]))
            .all()
        )
    for chunk in _chunks(keys["ips"]):
        rows += (
            db.query(*columns)
            .filter(
                or_(
                    NetworkInterface.ipv4_address.in_(chunk),
                    NetworkInterface.ipv6_address.in_(chunk),
                )
            )
            .all()
        )
    return [
        {
            "host_id": str(r.host_id),
            "mac_address": r.mac_address,
            "ipv4_address": r.ipv4_address,
            "ipv6_address": r.ipv6_address,
        }
        for r in rows
    ]


def _existing_assets(db, identities: List[str]) -> Dict[str, DiscoveredAsset]:
    found = {}
    for chunk in _chunks(identities):
        for asset in db.query(DiscoveredAsset).filter(
            DiscoveredAsset.identity.in_(chunk)
        ):
            found[asset.identity] = asset
    return found


def _new_asset(db, obs: Dict[str, Any], now: datetime) -> DiscoveredAsset:
    """Insert a device, or pick up the row another agent inserted first."""
    asset = DiscoveredAsset(
        identity=obs["identity"],
        identity_kind=obs["identity_kind"],
        first_seen_at=now,
        last_seen_at=now,
    )
    try:
        with db.begin_nested():
            db.add(asset)
        return asset
    except IntegrityError:
        # Two agents on one segment report the same new device at once.
        return (
            db.query(DiscoveredAsset)
            .filter(DiscoveredAsset.identity == obs["identity"])
            .one()
        )


def _classify(engine, asset) -> None:
    """S5: vendor from the shipped IEEE table, then the engine's labeled guess."""
    asset.vendor = oui.vendor_of(asset.mac)
    classify = getattr(engine, "classify", None)
    if classify is None:  # an engine older than S5
        return
    result = classify(asset.to_dict())
    asset.device_type = result["device_type"]
    asset.classification = {
        "confidence": result["confidence"],
        "reasons": result["reasons"],
    }


def _apply(asset, fields, verdict, now) -> None:
    for key, value in fields.items():
        setattr(asset, key, value)
    host_id = verdict["managed_host_id"]
    asset.managed_host_id = uuid.UUID(host_id) if host_id else None
    asset.managed_reason = verdict["reason"]
    asset.correlated_at = now
    asset.last_seen_at = now


def _sighting(db, asset, observer_id, obs, now) -> None:
    row = (
        db.query(DiscoveredAssetSighting)
        .filter(
            DiscoveredAssetSighting.asset_id == asset.id,
            DiscoveredAssetSighting.observer_host_id == observer_id,
        )
        .first()
    )
    if row is None:
        row = DiscoveredAssetSighting(
            asset_id=asset.id,
            observer_host_id=observer_id,
            sightings=0,
            first_seen_at=now,
        )
        db.add(row)
    row.interface = obs["interface"]
    row.network = obs["network"]
    row.ip = obs["ips"][0] if obs["ips"] else row.ip
    row.methods = sorted(set(row.methods or []) | set(obs["methods"]))
    row.sightings = (row.sightings or 0) + obs["count"]
    row.last_seen_at = now


def _observer(db, observer_id, clean, now) -> None:
    row = (
        db.query(NetworkDiscoveryObserver)
        .filter(NetworkDiscoveryObserver.host_id == observer_id)
        .first()
    )
    if row is None:
        row = NetworkDiscoveryObserver(host_id=observer_id, reports=0)
        db.add(row)
    row.networks = [
        {"interface": i["name"], "network": i["network"]}
        for i in clean["interfaces"]
        if i["network"]
    ]
    row.methods = clean["methods"]
    row.window_seconds = clean["window_seconds"]
    row.reports = (row.reports or 0) + 1
    row.last_report_at = now


def record_report(
    db, host_id: Any, payload: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Store one report. Never commits; the caller owns the transaction."""
    engine = shim.engine()
    if engine is None:
        return {"stored": False, "reason": "engine_unavailable"}
    observer_id = uuid.UUID(str(host_id))
    clean = engine.sanitize_report(payload or {})
    if clean["dropped"] or clean["truncated"]:
        logger.warning(
            "network discovery report from host %s: %d sighting(s) dropped as "
            "malformed or self-referential%s",
            observer_id,
            clean["dropped"],
            ", report TRUNCATED at the engine limit" if clean["truncated"] else "",
        )
    observations = clean["observations"]
    fleet = engine.build_fleet_index(_fleet_rows(db, engine.lookup_keys(observations)))
    existing = _existing_assets(db, [o["identity"] for o in observations])
    now = _utcnow()
    new = managed = 0
    for obs in observations:
        asset = existing.get(obs["identity"])
        if asset is None:
            asset = _new_asset(db, obs, now)
            new += 1
        verdict = engine.correlate(obs, fleet)
        managed += 1 if verdict["managed_host_id"] else 0
        _apply(asset, engine.merge_asset(asset.to_dict(), obs), verdict, now)
        _classify(engine, asset)
        db.flush()
        _sighting(db, asset, observer_id, obs, now)
    _observer(db, observer_id, clean, now)
    sweep = clean.get("sweep")
    if sweep:
        from backend.services import network_sweep  # noqa: PLC0415 - import cycle

        found = sum(1 for o in observations if "sweep" in o["methods"])
        network_sweep.record_result(db, observer_id, sweep, found)
    db.flush()
    return {
        "stored": True,
        "devices": len(observations),
        "new": new,
        "managed": managed,
        "dropped": clean["dropped"],
        "truncated": clean["truncated"],
    }


def _candidates(db, host_id, engine) -> List[DiscoveredAsset]:
    """Devices this host's interfaces could now match -- or stop matching."""
    rows = (
        db.query(NetworkInterface.mac_address, NetworkInterface.ipv4_address,
                 NetworkInterface.ipv6_address)
        .filter(NetworkInterface.host_id == host_id)
        .all()
    )  # fmt: skip
    identities = set()
    for row in rows:
        mac = engine.normalize_mac(row.mac_address)
        if mac:
            identities.update((mac, "fe" + mac[2:]))  # the MAC and its tap port
        for ip in (row.ipv4_address, row.ipv6_address):
            if engine.identity_ip(ip):
                identities.add("ip:" + engine.identity_ip(ip))
    found = {a.id: a for a in _existing_assets(db, sorted(identities)).values()}
    for asset in db.query(DiscoveredAsset).filter(
        DiscoveredAsset.managed_host_id == host_id
    ):
        found[asset.id] = asset
    return list(found.values())


def recorrelate_host(db, host_id: Any) -> int:
    """Re-match the devices a host's (new) interface inventory can affect.

    Called when a host reports its hardware. Without it a device first seen
    BEFORE its host enrolled would stay "unmanaged" until an agent happened to
    report it again, and one whose MAC moved away would stay "managed". Returns
    how many devices changed; never commits.
    """
    engine = shim.engine()
    if engine is None:
        return 0
    host_uuid = uuid.UUID(str(host_id))
    assets = _candidates(db, host_uuid, engine)
    if not assets:
        return 0
    observations = [
        {"mac": a.mac, "ips": list(a.ips or []), "identity": a.identity} for a in assets
    ]
    fleet = engine.build_fleet_index(_fleet_rows(db, engine.lookup_keys(observations)))
    now = _utcnow()
    changed = 0
    for asset, obs in zip(assets, observations):
        verdict = engine.correlate(obs, fleet)
        new_id = (
            uuid.UUID(verdict["managed_host_id"])
            if verdict["managed_host_id"]
            else None
        )
        if (new_id, verdict["reason"]) != (asset.managed_host_id, asset.managed_reason):
            asset.managed_host_id = new_id
            asset.managed_reason = verdict["reason"]
            changed += 1
        asset.correlated_at = now
    db.flush()
    return changed
