# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The review side of unenrolled asset discovery (Phase 21.6 S3).

What is on the network that SysManage does not manage -- listed with its
evidence, triaged in bulk, and permanently excluded with a reason and an
actor. Plus the part that keeps the list honest: what the agents could NOT
see.

STATUS, IN ONE PLACE
--------------------
  * ``managed``    -- matched to a managed host. Always wins: an exclusion can
                      never hide a host the fleet manages.
  * ``excluded``   -- an operator said "known and fine" (an active exclusion
                      for its identity).
  * ``unmanaged``  -- everything else: the list the page exists for.

WHY THE BLIND SPOTS ARE PART OF THE ANSWER
------------------------------------------
21.6 S0 measured it: passive listening cannot reliably see a silent device,
a Windows agent cannot listen for ARP at all, and an agent that stops
reporting sees nothing. A list presented without those limits reads as
"these are all the unmanaged devices" -- the claim this feature must never
make. ``summary`` returns them beside the counts, so the page can say them.
"""

import ipaddress
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import func, or_

from backend.i18n import _
from backend.persistence.models import (
    DiscoveredAsset,
    DiscoveredAssetExclusion,
    DiscoveredAssetSighting,
    Host,
    NetworkDiscoveryObserver,
)
from backend.persistence.models.asset_discovery import EXCLUSION_CATEGORIES
from backend.services import network_discovery_policy as policy_svc
from backend.services.agent_capability_service import host_supports

STATUSES = ("unmanaged", "managed", "excluded", "all")
MAX_PAGE = 500
MAX_REASON = 1000
# An agent that has not reported for this many intervals is a blind spot too.
STALE_INTERVALS = 3


class ReviewError(ValueError):
    """A request the review API refuses, with a translated message."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _active_exclusions():
    return DiscoveredAssetExclusion.revoked_at.is_(None)


def _excluded_expr(excluded_ids):
    """Excluded by its own identity, or -- for a static address registered
    by IP (a VIP, a load balancer; S5) -- by the address it holds now."""
    return or_(
        DiscoveredAsset.identity.in_(excluded_ids),
        ("ip:" + DiscoveredAsset.last_ip).in_(excluded_ids),
    )


def _status_filter(query, status: str, excluded_ids):
    managed = DiscoveredAsset.managed_host_id.isnot(None)
    excluded = _excluded_expr(excluded_ids)
    if status == "managed":
        return query.filter(managed)
    if status == "excluded":
        return query.filter(~managed, excluded)
    if status == "unmanaged":
        return query.filter(~managed, ~excluded)
    return query


def _excluded_subquery(db):
    return (
        db.query(DiscoveredAssetExclusion.identity)
        .filter(_active_exclusions())
        .scalar_subquery()
    )


def _exclusion_for(asset: DiscoveredAsset, excluded):
    if asset.identity in excluded:
        return excluded[asset.identity] if isinstance(excluded, dict) else True
    key = "ip:" + asset.last_ip if asset.last_ip else None
    if key and key in excluded:
        return excluded[key] if isinstance(excluded, dict) else True
    return None


def status_of(asset: DiscoveredAsset, excluded: Iterable[str]) -> str:
    if asset.managed_host_id is not None:
        return "managed"
    return "excluded" if _exclusion_for(asset, excluded) else "unmanaged"


# ---------------------------------------------------------------------------
# listing
# ---------------------------------------------------------------------------


def list_devices(
    db,
    status: str = "unmanaged",
    network: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    """One page of devices, newest sighting first, with their evidence."""
    if status not in STATUSES:
        raise ReviewError(_("Unknown device status: %s") % status)
    excluded_ids = _excluded_subquery(db)
    query = _status_filter(db.query(DiscoveredAsset), status, excluded_ids)
    if network:
        query = query.filter(
            db.query(DiscoveredAssetSighting.id)
            .filter(
                DiscoveredAssetSighting.asset_id == DiscoveredAsset.id,
                DiscoveredAssetSighting.network == network,
            )
            .exists()
        )
    if search:
        pattern = "%" + search.strip().lower() + "%"
        query = query.filter(
            or_(
                func.lower(DiscoveredAsset.identity).like(pattern),
                func.lower(DiscoveredAsset.last_ip).like(pattern),
            )
        )
    total = query.count()
    limit = max(1, min(int(limit), MAX_PAGE))
    page = (
        query.order_by(DiscoveredAsset.last_seen_at.desc())
        .offset(max(0, int(offset)))
        .limit(limit)
        .all()
    )
    return {"total": total, "devices": _enrich(db, page)}


def _enrich(db, assets: List[DiscoveredAsset]) -> List[Dict[str, Any]]:
    if not assets:
        return []
    ids = [a.id for a in assets]
    sightings: Dict[Any, List[Tuple[Any, Any]]] = {}
    for row in db.query(
        DiscoveredAssetSighting.asset_id,
        DiscoveredAssetSighting.network,
        DiscoveredAssetSighting.observer_host_id,
    ).filter(DiscoveredAssetSighting.asset_id.in_(ids)):
        sightings.setdefault(row.asset_id, []).append(
            (row.network, row.observer_host_id)
        )
    identities = [a.identity for a in assets]
    identities += ["ip:" + a.last_ip for a in assets if a.last_ip]
    exclusions = {
        e.identity: e
        for e in db.query(DiscoveredAssetExclusion).filter(
            DiscoveredAssetExclusion.identity.in_(identities), _active_exclusions()
        )
    }
    host_ids = {a.managed_host_id for a in assets if a.managed_host_id}
    host_ids |= {obs for rows in sightings.values() for _net, obs in rows}
    fqdn = (
        dict(db.query(Host.id, Host.fqdn).filter(Host.id.in_(host_ids)))
        if host_ids
        else {}
    )
    out = []
    for asset in assets:
        row = asset.to_dict()
        seen = sightings.get(asset.id, [])
        row["status"] = status_of(asset, exclusions)
        row["networks"] = sorted({net for net, _obs in seen if net})
        row["observers"] = sorted({fqdn.get(obs, str(obs)) for _net, obs in seen})
        row["managed_host_fqdn"] = fqdn.get(asset.managed_host_id)
        exclusion = _exclusion_for(asset, exclusions)
        row["exclusion"] = exclusion.to_dict() if exclusion else None
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# summary + blind spots
# ---------------------------------------------------------------------------


def _counts(db) -> Dict[str, int]:
    excluded_ids = _excluded_subquery(db)
    return {
        status: _status_filter(db.query(DiscoveredAsset), status, excluded_ids).count()
        for status in ("unmanaged", "managed", "excluded")
    }


def _networks(db) -> List[Dict[str, Any]]:
    """Unmanaged devices per network: "11 unmanaged devices on 2 segments"."""
    excluded_ids = _excluded_subquery(db)
    rows = (
        db.query(
            DiscoveredAssetSighting.network,
            func.count(func.distinct(DiscoveredAssetSighting.asset_id)),
            func.count(func.distinct(DiscoveredAssetSighting.observer_host_id)),
        )
        .join(DiscoveredAsset, DiscoveredAsset.id == DiscoveredAssetSighting.asset_id)
        .filter(
            DiscoveredAsset.managed_host_id.is_(None),
            ~_excluded_expr(excluded_ids),
            DiscoveredAssetSighting.network.isnot(None),
        )
        .group_by(DiscoveredAssetSighting.network)
        .all()
    )
    return sorted(
        ({"network": net, "unmanaged": devices, "observers": observers}
         for net, devices, observers in rows),  # fmt: skip
        key=lambda r: (-r["unmanaged"], r["network"]),
    )


def _observers(db, interval: int, now: datetime) -> List[Dict[str, Any]]:
    stale_after = timedelta(seconds=interval * STALE_INTERVALS)
    rows = (
        db.query(NetworkDiscoveryObserver, Host.fqdn)
        .join(Host, Host.id == NetworkDiscoveryObserver.host_id)
        .order_by(Host.fqdn)
        .all()
    )
    out = []
    for observer, fqdn in rows:
        methods = observer.methods or {}
        out.append(
            {
                "host_id": str(observer.host_id),
                "fqdn": fqdn,
                "networks": observer.networks or [],
                "last_report_at": observer.last_report_at.isoformat(),
                "stale": now - observer.last_report_at > stale_after,
                # ``sweep`` is not the agent's to report: whether sweeps are
                # allowed is the tenant policy, and each run is its own record.
                "unavailable": {
                    m: v.split(":", 1)[1]
                    for m, v in sorted(methods.items())
                    if m != "sweep"
                    and isinstance(v, str)
                    and v.startswith("unavailable:")
                },
            }
        )
    return out


def _coverage(db) -> Dict[str, int]:
    """How many active hosts CAN take part at all."""
    equipped = not_equipped = unknown = 0
    for host in db.query(Host).filter(
        Host.active.is_(True), Host.approval_status == "approved"
    ):
        verdict = host_supports(host, policy_svc.COMMAND)
        if verdict is True:
            equipped += 1
        elif verdict is False:
            not_equipped += 1
        else:
            unknown += 1
    return {"equipped": equipped, "not_equipped": not_equipped, "unknown": unknown}


def _observed_networks(observers: List[Dict[str, Any]]) -> List[str]:
    return sorted(
        {n["network"] for o in observers for n in o["networks"] if n.get("network")}
    )


def _types(db) -> Dict[str, int]:
    """Unmanaged devices by what they look like (S5): "7 printers"."""
    excluded_ids = _excluded_subquery(db)
    rows = (
        _status_filter(db.query(DiscoveredAsset.device_type), "unmanaged", excluded_ids)
        .with_entities(DiscoveredAsset.device_type, func.count(DiscoveredAsset.id))
        .group_by(DiscoveredAsset.device_type)
        .all()
    )
    return {(kind or "unknown"): count for kind, count in rows}


def summary(db) -> Dict[str, Any]:
    """Counts, per-network totals and every blind spot, for the page header."""
    from backend.services import network_sweep  # noqa: PLC0415 - import cycle

    policy = policy_svc.get_policy(db)
    now = _utcnow()
    observers = _observers(db, policy["report_interval_seconds"], now)
    swept = network_sweep.recently_swept(db, now)
    unswept = [n for n in _observed_networks(observers) if n not in swept]
    networks = _networks(db)
    for row in networks:
        row["swept_at"] = swept.get(row["network"])
    return {
        "policy": policy,
        "counts": _counts(db),
        "types": _types(db),
        "networks": networks,
        "observers": observers,
        "coverage": _coverage(db),
        "blind_spots": {
            # Silent devices are invisible to every passive method; only a
            # recent sweep (S4) covers them, network by network.
            "silent_devices_unseen": bool(unswept) or not swept,
            "unswept_networks": unswept,
            "stale_observers": sum(1 for o in observers if o["stale"]),
            "observers_without_arp": sum(
                1 for o in observers if "arp_listen" in o["unavailable"]
            ),
        },
    }


# ---------------------------------------------------------------------------
# exclusions
# ---------------------------------------------------------------------------


def _clean_reason(reason: Optional[str]) -> str:
    text = (reason or "").strip()
    if len(text) < 3:
        raise ReviewError(_("A reason of at least 3 characters is required"))
    return text[:MAX_REASON]


def exclude(
    db, asset_ids: List[Any], category: str, reason: str, actor: str
) -> Dict[str, Any]:
    """Permanently exclude devices, keyed by identity. Never commits."""
    if category not in EXCLUSION_CATEGORIES:
        raise ReviewError(_("Unknown exclusion category: %s") % category)
    text = _clean_reason(reason)
    assets = db.query(DiscoveredAsset).filter(DiscoveredAsset.id.in_(asset_ids)).all()
    active = {
        e.identity
        for e in db.query(DiscoveredAssetExclusion.identity).filter(
            DiscoveredAssetExclusion.identity.in_([a.identity for a in assets]),
            _active_exclusions(),
        )
    }
    created, already, managed = [], 0, 0
    for asset in assets:
        if asset.managed_host_id is not None:
            managed += 1  # a managed host is not "known and fine" -- it is managed
            continue
        if asset.identity in active:
            already += 1
            continue
        row = DiscoveredAssetExclusion(
            identity=asset.identity,
            category=category,
            reason=text,
            created_by=actor,
            created_at=_utcnow(),
        )
        db.add(row)
        active.add(asset.identity)
        created.append(row)
    db.flush()
    return {
        "excluded": len(created),
        "already_excluded": already,
        "skipped_managed": managed,
        "not_found": len(set(map(str, asset_ids))) - len(assets),
        "exclusions": [e.to_dict() for e in created],
    }


def exclude_address(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    db, address: str, category: str, reason: str, actor: str
) -> Dict[str, Any]:
    """Register a STATIC address as known (a VIP, a load balancer) -- S5.

    Keyed by IP, so it covers whatever device holds that address. Only for
    addresses that never change: 21.6 S0 showed an IP-keyed exclusion of an
    ordinary DHCP device rots on the next lease. Never commits.
    """
    if category not in EXCLUSION_CATEGORIES:
        raise ReviewError(_("Unknown exclusion category: %s") % category)
    text = _clean_reason(reason)
    try:
        ip = ipaddress.ip_address(str(address).strip())
    except ValueError as exc:
        raise ReviewError(_("That is not a valid IP address")) from exc
    identity = "ip:" + str(ip)
    active = (
        db.query(DiscoveredAssetExclusion)
        .filter(DiscoveredAssetExclusion.identity == identity, _active_exclusions())
        .first()
    )
    if active is not None:
        raise ReviewError(_("That address is already registered as known"))
    row = DiscoveredAssetExclusion(
        identity=identity,
        category=category,
        reason=text,
        created_by=actor,
        created_at=_utcnow(),
    )
    db.add(row)
    db.flush()
    return row.to_dict()


def revoke(db, exclusion_id: Any, reason: str, actor: str) -> Dict[str, Any]:
    """Withdraw an exclusion; the row stays as history. Never commits."""
    row = (
        db.query(DiscoveredAssetExclusion)
        .filter(DiscoveredAssetExclusion.id == exclusion_id)
        .first()
    )
    if row is None:
        raise ReviewError(_("Exclusion not found"))
    if row.revoked_at is not None:
        raise ReviewError(_("This exclusion was already revoked"))
    row.revoked_by = actor
    row.revoked_at = _utcnow()
    row.revoke_reason = _clean_reason(reason)
    db.flush()
    return row.to_dict()


def list_exclusions(db, include_revoked: bool = False) -> List[Dict[str, Any]]:
    """Exclusions, newest first, with the device they cover when it is known."""
    query = db.query(DiscoveredAssetExclusion)
    if not include_revoked:
        query = query.filter(_active_exclusions())
    rows = query.order_by(DiscoveredAssetExclusion.created_at.desc()).all()
    devices = {
        a.identity: a
        for a in db.query(DiscoveredAsset).filter(
            DiscoveredAsset.identity.in_([r.identity for r in rows])
        )
    }
    out = []
    for row in rows:
        entry = row.to_dict()
        device = devices.get(row.identity)
        entry["last_ip"] = device.last_ip if device else None
        entry["last_seen_at"] = device.to_dict()["last_seen_at"] if device else None
        out.append(entry)
    return out
