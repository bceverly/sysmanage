# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The security catalog across an air gap (2026-11-23): the collector's
CVEs and vendor advisories exported to one file, staged onto the media and
loaded on the repository side only when the signed manifest names its
hash."""

# pylint: disable=redefined-outer-name

import gzip
import json
import os
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence import models
from backend.persistence.db import Base
from backend.services import advisory_tick, airgap_catalog

TABLES = [
    models.Vulnerability.__table__,
    models.PackageVulnerability.__table__,
    models.SharedAdvisory.__table__,
    models.SharedAdvisoryPackage.__table__,
    models.SharedAdvisoryCve.__table__,
    models.VulnerabilityIngestionLog.__table__,
    models.AdvisoryIngestionLog.__table__,
    models.CveRefreshSettings.__table__,
]
NOW = datetime(2026, 11, 23, 12, 0, 0)


def _db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=TABLES)
    return engine, sessionmaker(bind=engine)()


@pytest.fixture
def collector():
    engine, session = _db()
    vid = uuid.uuid4()
    session.add(models.Vulnerability(
        id=vid, cve_id="CVE-2026-0001", description="openssl", severity="HIGH",
        cvss_score="7.5", published_date=NOW, created_at=NOW, updated_at=NOW))  # fmt: skip
    session.add(models.PackageVulnerability(
        id=uuid.uuid4(), vulnerability_id=vid, package_name="openssl", package_manager="apt",
        fixed_version="3.0.15-1", source="debian", release="debian:12",
        created_at=NOW, updated_at=NOW))  # fmt: skip
    adv = models.SharedAdvisory(
        id=uuid.uuid4(), advisory_id="DSA-6000-1", source="debian", advisory_type="security",
        severity="HIGH", title="openssl", created_at=NOW, updated_at=NOW)  # fmt: skip
    session.add(adv)
    session.flush()
    session.add(models.SharedAdvisoryPackage(
        id=uuid.uuid4(), advisory_row_id=adv.id, package_name="openssl",
        package_manager="apt", release="debian:12", fixed_version="3.0.15-1"))  # fmt: skip
    session.add(models.SharedAdvisoryCve(id=uuid.uuid4(), advisory_row_id=adv.id,
                                         cve_id="CVE-2026-0001"))  # fmt: skip
    session.commit()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def repository():
    engine, session = _db()
    yield session
    session.close()
    engine.dispose()


def test_the_export_carries_every_cve_mapping_and_advisory(collector, tmp_path):
    entry = airgap_catalog.export(collector, str(tmp_path))
    assert (entry["cves"], entry["mappings"], entry["advisories"]) == (1, 1, 1)
    lines = [json.loads(l) for l in gzip.open(tmp_path / entry["name"], "rt")]
    assert [l["kind"] for l in lines] == ["header", "cve", "advisory"]
    assert lines[1]["packages"][0]["release"] == "debian:12"
    assert lines[2]["cves"] == ["CVE-2026-0001"]
    with patch.object(airgap_catalog, "EXPORT_ROOT", str(tmp_path.parent)):
        assert airgap_catalog.manifest_entry(tmp_path.name)["sha256"] == entry["sha256"]


def test_staging_copies_and_checks_the_file(tmp_path):
    entry = {"name": airgap_catalog.CATALOG_FILE, "sha256": "ab" * 32}
    plan = airgap_catalog.stage_plan("run-1", "/stage/run-1", entry)
    argvs = [c["argv"] for c in plan["commands"]]
    assert argvs[1][:2] == ["sudo", "cp"] and argvs[2][:2] == ["sudo", "sha256sum"]
    assert all(c["ignore_errors"] for c in plan["commands"])
    assert (
        plan["files"][0]["content"] == f"{'ab' * 32}  {airgap_catalog.CATALOG_FILE}\n"
    )


def _on_media(collector, tmp_path):
    out = tmp_path / "export"
    entry = airgap_catalog.export(collector, str(out))
    media = tmp_path / "repo" / airgap_catalog.CATALOG_DIR
    media.mkdir(parents=True)
    os.replace(out / entry["name"], media / entry["name"])
    return str(tmp_path / "repo"), {"security_catalog": entry}


def test_the_repository_loads_only_what_the_signed_manifest_names(collector, tmp_path):
    root, manifest = _on_media(collector, tmp_path)
    assert airgap_catalog.find(root, manifest)
    assert airgap_catalog.find(root, {}) is None
    bad = {"security_catalog": dict(manifest["security_catalog"], sha256="0" * 64)}
    assert airgap_catalog.find(root, bad) is None


def test_ingest_loads_and_a_second_ingest_updates_in_place(
    collector, repository, tmp_path
):
    root, manifest = _on_media(collector, tmp_path)
    path = airgap_catalog.find(root, manifest)
    assert airgap_catalog.ingest(repository, path)["cves"] == 1
    repository.commit()
    vid = repository.query(models.Vulnerability).one().id
    # A host finding points at that id: a newer catalog must keep it.
    collector.query(models.Vulnerability).update({"severity": "CRITICAL"})
    collector.commit()
    root2, manifest2 = _on_media(collector, tmp_path / "second")
    airgap_catalog.ingest(repository, airgap_catalog.find(root2, manifest2))
    repository.commit()
    row = repository.query(models.Vulnerability).one()
    assert row.id == vid and row.severity == "CRITICAL"
    assert repository.query(models.PackageVulnerability).count() == 1
    assert repository.query(models.SharedAdvisory).one().advisory_id == "DSA-6000-1"
    assert repository.query(models.SharedAdvisoryPackage).count() == 1
    assert repository.query(models.SharedAdvisoryCve).count() == 1
    logs = repository.query(models.AdvisoryIngestionLog).all()
    assert len(logs) == 2 and logs[0].source == "airgap" and logs[0].status == "success"


def test_a_repository_server_never_refreshes_online():
    engine = MagicMock()
    with patch.object(advisory_tick, "_engine", return_value=engine), \
            patch.object(advisory_tick.config_module, "is_repository", return_value=True):  # fmt: skip
        assert advisory_tick.run_one_tick() is None
    assert (
        not engine._advisory_service.refresh_advisories.called
    )  # pylint: disable=protected-access


@pytest.mark.real_catalog_export
def test_a_cve_run_stages_the_catalog_and_names_it_in_the_manifest(collector, tmp_path):
    from backend.services import (
        airgap_run_tick,
    )  # pylint: disable=import-outside-toplevel

    run = MagicMock(include_cve=True, id="run-7")
    with patch.object(airgap_catalog, "EXPORT_ROOT", str(tmp_path)), \
            patch("backend.persistence.partitions.shared_sessionmaker",
                  return_value=lambda: collector):  # fmt: skip
        staged = airgap_run_tick._resolve_catalog(
            run, "/stage/run-7"
        )  # pylint: disable=protected-access
        entry = airgap_run_tick._catalog_manifest(
            run
        )  # pylint: disable=protected-access
    assert entry["cves"] == 1 and entry["advisories"] == 1
    assert any(c["argv"][:2] == ["sudo", "cp"] for c in staged["commands"])
    run.include_cve = False
    assert (
        airgap_run_tick._catalog_manifest(run) is None
    )  # pylint: disable=protected-access


def test_strings_longer_than_their_column_are_cut_to_fit():
    """PostgreSQL refused SUSE-SU-2024:1639-2's 600-character title in the
    lab (2026-11-23); SQLite on the collector never minds."""
    long_title = "Security update for " + ", ".join(f"python-pkg{n}" for n in range(60))
    fitted = airgap_catalog._fit(
        models.SharedAdvisory, {"title": long_title, "source": "suse"}
    )  # pylint: disable=protected-access
    assert len(fitted["title"]) == 500 and fitted["title"].endswith("...")
    assert fitted["source"] == "suse"


def test_an_advisory_without_a_severity_takes_its_worst_cves_and_links_them(
    collector, repository, tmp_path
):
    """Ubuntu and Debian advisories carry no severity: every lab host showed
    84 UNKNOWN (2026-11-23).  A catalog from an older collector gets the
    same rule a connected engine applies, and each CVE link its row."""
    collector.query(models.SharedAdvisory).update({"severity": None})
    collector.commit()
    root, manifest = _on_media(collector, tmp_path)
    airgap_catalog.ingest(repository, airgap_catalog.find(root, manifest))
    repository.commit()
    assert repository.query(models.SharedAdvisory).one().severity == "HIGH"
    link = repository.query(models.SharedAdvisoryCve).one()
    assert link.vulnerability_id == repository.query(models.Vulnerability).one().id
