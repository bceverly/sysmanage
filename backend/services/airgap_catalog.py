# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The security catalog across an air gap (2026-11-23).

An air-gapped repository server reaches no feed, so until now it had no
CVEs and no vendor advisories at all: the collector curled a few raw CVE
feeds onto the media, but nothing on the far side ever read them (and a
single page of the NVD API is not the catalog anyway).

The collector already HOLDS the catalog -- it is a connected SysManage
server whose CVE and advisory refreshes fill the shared tables.  So this
carries those tables, as they are, in one file:

COLLECTOR   ``export`` writes ``security-catalog.jsonl.gz`` (one JSON record
            per line: a header, then every CVE with its package mappings,
            then every advisory with its packages and CVE ids) beside the
            run, and ``stage_plan`` copies it into the staging tree, checked
            by ``sha256sum``.  Its name, SHA-256 and counts go into the
            signed manifest (``security_catalog``).

REPOSITORY  ``ingest`` finds the file in the copied payload, refuses it
            unless its SHA-256 is the one the signed manifest names, and
            loads it: CVEs upserted by CVE id (a host finding's soft
            reference to a CVE row keeps working), each CVE's package
            mappings replaced, advisories upserted by (source, id) with their
            packages and CVEs replaced.  Ingestion-log rows say where the
            catalog came from and when the collector made it.

A repository server never refreshes online (``cve_refresh_service`` and
``advisory_tick`` skip it): the media is its only source.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import posixpath
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

from sqlalchemy import insert
from sqlalchemy.orm import Session

from backend.persistence import models

logger = logging.getLogger(__name__)

FORMAT_VERSION = 1
CATALOG_DIR = "security-catalog"
CATALOG_FILE = "security-catalog.jsonl.gz"
EXPORT_ROOT = "/var/lib/sysmanage/airgap-catalog"
ENTRY_FILE = "entry.json"
SOURCE = "airgap"
_BATCH = 2000

_VULN_FIELDS = (
    "cve_id", "description", "cvss_score", "cvss_version", "severity",
    "published_date", "modified_date", "references", "affected_systems",
)  # fmt: skip
_MAPPING_FIELDS = (
    "package_name", "package_manager", "vulnerable_versions", "fixed_version",
    "advisory_ids", "source", "release",
)  # fmt: skip
_ADVISORY_SKIP = ("id", "created_at", "updated_at")
_ADV_PACKAGE_SKIP = ("id", "advisory_row_id", "created_at", "updated_at")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _plain(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _when(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _columns(model) -> List[str]:
    return [c.name for c in model.__table__.columns]


def _fit(model, values: Dict[str, Any]) -> Dict[str, Any]:
    """Each string cut to its column's length: PostgreSQL refuses a longer
    one (a SUSE title is 600+ characters into a VARCHAR(500)) where the
    collector's own database may not have (2026-11-23)."""
    out = {}
    for name, value in values.items():
        column = model.__table__.columns.get(name)
        length = getattr(getattr(column, "type", None), "length", None)
        if isinstance(value, str) and length and len(value) > length:
            value = value[: length - 3] + "..."
        out[name] = value
    return out


# --- the collector side --------------------------------------------------------


def export_dir(run_id: Any) -> str:
    return posixpath.join(EXPORT_ROOT, str(run_id))


def _records(db: Session) -> Iterator[Dict[str, Any]]:
    """Every CVE (with its package mappings), then every advisory."""
    mappings: Dict[Any, List[Dict[str, Any]]] = {}
    for row in db.query(models.PackageVulnerability).yield_per(_BATCH):
        mappings.setdefault(row.vulnerability_id, []).append(
            {f: _plain(getattr(row, f, None)) for f in _MAPPING_FIELDS}
        )
    for row in db.query(models.Vulnerability).yield_per(_BATCH):
        record = {f: _plain(getattr(row, f, None)) for f in _VULN_FIELDS}
        record["kind"] = "cve"
        record["id"] = str(row.id)
        record["packages"] = mappings.pop(row.id, [])
        yield record
    packages: Dict[Any, List[Dict[str, Any]]] = {}
    pkg_cols = [
        c for c in _columns(models.SharedAdvisoryPackage) if c not in _ADV_PACKAGE_SKIP
    ]
    for row in db.query(models.SharedAdvisoryPackage).yield_per(_BATCH):
        packages.setdefault(row.advisory_row_id, []).append(
            {c: _plain(getattr(row, c)) for c in pkg_cols}
        )
    cves: Dict[Any, List[str]] = {}
    for row in db.query(models.SharedAdvisoryCve).yield_per(_BATCH):
        cves.setdefault(row.advisory_row_id, []).append(row.cve_id)
    adv_cols = [c for c in _columns(models.SharedAdvisory) if c not in _ADVISORY_SKIP]
    for row in db.query(models.SharedAdvisory).yield_per(_BATCH):
        record = {c: _plain(getattr(row, c)) for c in adv_cols}
        record["kind"] = "advisory"
        record["id"] = str(row.id)
        record["packages"] = packages.pop(row.id, [])
        record["cves"] = sorted(set(cves.pop(row.id, [])))
        yield record


def export(db: Session, out_dir: str) -> Dict[str, Any]:
    """Write the catalog file into ``out_dir``; its manifest entry
    ``{name, sha256, generated_at, cves, mappings, advisories}`` (also kept
    there as ``entry.json`` for the manifest builder)."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, CATALOG_FILE)
    counts = {"cves": 0, "mappings": 0, "advisories": 0}
    generated = _now().isoformat()
    with gzip.open(path, "wt", encoding="utf-8") as out:
        out.write(json.dumps({"kind": "header", "format_version": FORMAT_VERSION,
                              "generated_at": generated}) + "\n")  # fmt: skip
        for record in _records(db):
            if record["kind"] == "cve":
                counts["cves"] += 1
                counts["mappings"] += len(record["packages"])
            else:
                counts["advisories"] += 1
            out.write(json.dumps(record, separators=(",", ":")) + "\n")
    entry = {
        "name": CATALOG_FILE,
        "sha256": _sha256(path),
        "generated_at": generated,
        **counts,
    }
    with open(os.path.join(out_dir, ENTRY_FILE), "w", encoding="utf-8") as fh:
        json.dump(entry, fh)
    return entry


def manifest_entry(run_id: Any) -> Optional[Dict[str, Any]]:
    """The exported catalog's manifest entry for a run, or None."""
    try:
        with open(os.path.join(export_dir(run_id), ENTRY_FILE), encoding="utf-8") as fh:
            entry = json.load(fh)
    except (OSError, ValueError):
        return None
    return entry if isinstance(entry, dict) and entry.get("sha256") else None


def check_file(staging_dir: str, name: str) -> str:
    """Where a collection's ``sha256sum -c`` list goes: beside the staging
    tree, not in it (not on the disc).  Its paths are absolute -- the
    agent runs plan commands from its own directory, and the disc's
    SHA256SUMS (bare names, for checking on the disc itself) could never
    be checked from there (2026-11-24)."""
    return f"{staging_dir.rstrip('/')}.checks/{name}.sha256"


def stage_plan(run_id: Any, staging_dir: str, entry: Dict[str, Any]) -> Dict[str, List]:
    """``{files, commands}`` the collector host's agent runs: the catalog
    copied into the staging tree and checked.  The collection plan runs on
    the collector itself, so the export is a local file.  Errors ignored: a
    missing catalog never fails the operating-system mirror run -- the
    repository side loads only a file whose hash the signed manifest names.

    Copied with ``install``, which the agent's sudoers grants on every
    platform; ``cp`` it does not, and a copy that sudo refused left a disc
    whose manifest named a catalog it did not carry (2026-11-24)."""
    folder = f"{staging_dir}/{CATALOG_DIR}"
    source = posixpath.join(export_dir(run_id), CATALOG_FILE)
    dest = f"{folder}/{entry['name']}"
    check = check_file(staging_dir, "security-catalog")
    return {
        "files": [{"path": f"{folder}/SHA256SUMS",
                   "content": f"{entry['sha256']}  {entry['name']}\n",
                   "permissions": "0644", "owner_uid": 0, "owner_gid": 0},
                  {"path": check, "content": f"{entry['sha256']}  {dest}\n",
                   "permissions": "0644", "owner_uid": 0, "owner_gid": 0}],
        "commands": [
            _cmd(["sudo", "mkdir", "-p", folder], 60, "security catalog folder"),
            _cmd(["sudo", "install", "-m", "0644", "-o", "0", "-g", "0", "--", source, dest],
                 600, "copy the security catalog"),
            _cmd(["sudo", "sha256sum", "-c", "--quiet", check], 600,
                 "check the security catalog"),
        ],
    }  # fmt: skip


def _cmd(argv, timeout, description) -> Dict[str, Any]:
    return {"argv": argv, "timeout": timeout, "ignore_errors": True,
            "description": description}  # fmt: skip


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --- the repository side ------------------------------------------------------


def _read(path: str) -> Iterator[Dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def _insert(db: Session, model, rows: List[Dict[str, Any]]) -> None:
    """One bulk INSERT per batch: an ORM object per row took over an hour
    for a full catalog on a 4 GB repository server (lab, 2026-11-23)."""
    if rows:
        db.execute(insert(model.__table__), rows)


def _load_cves(
    db: Session, records: List[Dict[str, Any]], existing: Dict[str, Any]
) -> int:
    """Upsert CVEs by CVE id (``existing``: CVE id -> row id, kept current);
    replace their package mappings."""
    vuln_cols = set(_columns(models.Vulnerability))
    now = _now()
    new_rows, updates, mappings = [], [], []
    for record in records:
        values = _fit(models.Vulnerability,
                      {f: record.get(f) for f in _VULN_FIELDS if f in vuln_cols})  # fmt: skip
        for field in ("published_date", "modified_date"):
            values[field] = _when(values.get(field))
        vid = existing.get(record["cve_id"])
        if vid is None:
            vid = uuid.UUID(record["id"])
            existing[record["cve_id"]] = vid
            new_rows.append(dict(values, id=vid, created_at=now, updated_at=now))
        else:
            updates.append(dict(values, id=vid, updated_at=now))
        for mapping in record.get("packages") or []:
            mappings.append(_fit(models.PackageVulnerability, dict(
                mapping, id=uuid.uuid4(), vulnerability_id=vid, created_at=now, updated_at=now)))  # fmt: skip
    _insert(db, models.Vulnerability, new_rows)
    if updates:
        db.bulk_update_mappings(models.Vulnerability, updates)
    ids = [existing[r["cve_id"]] for r in records]
    if ids:
        db.query(models.PackageVulnerability).filter(
            models.PackageVulnerability.vulnerability_id.in_(ids)
        ).delete(synchronize_session=False)
    _insert(db, models.PackageVulnerability, mappings)
    return len(records)


_SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def _worst(cve_ids, cve_severity: Dict[str, Any]) -> Optional[str]:
    """The most severe of these CVEs' severities, or None."""
    ranked = [str(cve_severity.get(c) or "").upper() for c in cve_ids]
    ranked = [r for r in ranked if r in _SEVERITY_RANK]
    return max(ranked, key=_SEVERITY_RANK.get) if ranked else None


def _load_advisories(
    db: Session,
    records: List[Dict[str, Any]],
    existing: Dict[Any, Any],
    cves_known: Dict[str, Any],
    cve_severity: Dict[str, Any],
) -> int:
    """Upsert advisories by (source, advisory id) (``existing``: that pair ->
    row id, kept current); replace their packages and CVEs, each CVE linked
    to its catalog row.  An advisory with no severity (Ubuntu's, Debian's)
    takes its worst CVE's, as a connected server's engine does."""
    adv_cols = set(_columns(models.SharedAdvisory)) - set(_ADVISORY_SKIP)
    pkg_cols = set(_columns(models.SharedAdvisoryPackage)) - set(_ADV_PACKAGE_SKIP)
    dates = {name for name, col in models.SharedAdvisory.__table__.columns.items()
             if col.type.python_type is datetime}  # fmt: skip
    now = _now()
    new_rows, updates, packages, cves, ids = [], [], [], [], []
    for record in records:
        values = _fit(
            models.SharedAdvisory, {c: record.get(c) for c in adv_cols if c in record}
        )
        for field in dates & set(values):
            values[field] = _when(values[field])
        if not values.get("severity"):
            values["severity"] = _worst(record.get("cves") or [], cve_severity)
        key = (record.get("source"), record.get("advisory_id"))
        row_id = existing.get(key)
        if row_id is None:
            row_id = uuid.UUID(record["id"])
            existing[key] = row_id
            new_rows.append(dict(values, id=row_id, created_at=now, updated_at=now))
        else:
            updates.append(dict(values, id=row_id, updated_at=now))
        ids.append(row_id)
        for pkg in record.get("packages") or []:
            packages.append(_fit(models.SharedAdvisoryPackage, dict(
                {c: pkg.get(c) for c in pkg_cols if c in pkg}, id=uuid.uuid4(), advisory_row_id=row_id)))  # fmt: skip
        for cve in record.get("cves") or []:
            cves.append({"id": uuid.uuid4(), "advisory_row_id": row_id, "cve_id": cve,
                         "vulnerability_id": cves_known.get(cve)})  # fmt: skip
    _insert(db, models.SharedAdvisory, new_rows)
    if updates:
        db.bulk_update_mappings(models.SharedAdvisory, updates)
    for model in (models.SharedAdvisoryPackage, models.SharedAdvisoryCve):
        if ids:
            db.query(model).filter(model.advisory_row_id.in_(ids)).delete(
                synchronize_session=False
            )
    _insert(db, models.SharedAdvisoryPackage, packages)
    _insert(db, models.SharedAdvisoryCve, cves)
    return len(records)


def _log(db: Session, generated_at: str, cves: int, advisories: int) -> None:
    """Ingestion-log rows (what the UI's "last refreshed" reads), noting the
    catalog came from the media and when the collector made it."""
    now = _now()
    details = {"from": "air-gap media", "generated_at": generated_at}
    db.add(models.VulnerabilityIngestionLog(
        source=SOURCE, status="success", started_at=now, completed_at=now,
        vulnerabilities_processed=cves, details=details))  # fmt: skip
    db.add(models.AdvisoryIngestionLog(
        source=SOURCE, status="success", started_at=now, completed_at=now,
        advisories_processed=advisories, details=details))  # fmt: skip
    settings = db.query(models.CveRefreshSettings).first()
    if settings is not None and hasattr(settings, "last_refresh_at"):
        settings.last_refresh_at = now


def find(repo_root: str, manifest: Dict[str, Any]) -> Optional[str]:
    """The catalog file on this ingest's media, if the signed manifest names
    it and the file's SHA-256 is the named one; else None (logged)."""
    entry = manifest.get("security_catalog") if isinstance(manifest, dict) else None
    if not isinstance(entry, dict) or not entry.get("sha256") or not entry.get("name"):
        return None
    name = os.path.basename(str(entry["name"]))
    path = os.path.join(repo_root, CATALOG_DIR, name)
    if not os.path.isfile(path):
        logger.info("air-gap ingest: the security catalog is not on this disc")
        return None
    if _sha256(path) != entry["sha256"]:
        logger.error(
            "air-gap ingest: %s does not match the signed manifest; not loaded", path
        )
        return None
    return path


def _settle(db: Session) -> None:
    """Write a batch and forget its objects: a full catalog is ~650,000 rows
    (production, 2026-11-23), too many to hold in one session."""
    db.flush()
    db.expunge_all()


def ingest(db: Session, path: str) -> Dict[str, Any]:
    """Load a verified catalog file into the shared tables.  The caller
    commits.  ``{cves, advisories, generated_at}``."""
    header: Dict[str, Any] = {}
    known_cves = dict(db.query(models.Vulnerability.cve_id, models.Vulnerability.id))
    known_advs = {(src, aid): rid for src, aid, rid in db.query(
        models.SharedAdvisory.source, models.SharedAdvisory.advisory_id, models.SharedAdvisory.id)}  # fmt: skip
    cves, advisories, batch_cves, batch_advs = 0, 0, [], []
    severities: Optional[Dict[str, Any]] = None
    for record in _read(path):
        kind = record.get("kind")
        if kind == "header":
            header = record
        elif kind == "cve" and record.get("cve_id"):
            batch_cves.append(record)
        elif kind == "advisory" and record.get("advisory_id"):
            if severities is None:  # the CVEs come first: load the last of them
                cves += _load_cves(db, batch_cves, known_cves)
                batch_cves = []
                _settle(db)
                severities = dict(db.query(models.Vulnerability.cve_id,
                                           models.Vulnerability.severity))  # fmt: skip
            batch_advs.append(record)
        if len(batch_cves) >= _BATCH:
            cves += _load_cves(db, batch_cves, known_cves)
            batch_cves = []
            _settle(db)
        if len(batch_advs) >= _BATCH:
            advisories += _load_advisories(
                db, batch_advs, known_advs, known_cves, severities
            )
            batch_advs = []
            _settle(db)
    cves += _load_cves(db, batch_cves, known_cves)
    advisories += _load_advisories(db, batch_advs, known_advs, known_cves, severities)
    generated = str(header.get("generated_at") or "")
    _log(db, generated, cves, advisories)
    return {"cves": cves, "advisories": advisories, "generated_at": generated}
