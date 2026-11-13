# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The SysManage tools repository of an air-gapped site (ROADMAP 25.9): the
agent, restate and restate-proxy named with their SHA-256 on the internet
side, checked against the signed manifest and served as a repository signed
with the site's own key on the other."""

# pylint: disable=protected-access,redefined-outer-name

import gzip
import hashlib
import json
import os
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from backend.services import airgap_repoint_service as repoint
from backend.services import airgap_tools as tools

SHA = "c" * 64


@pytest.fixture(autouse=True)
def no_cache():
    tools._cache.clear()
    yield
    tools._cache.clear()


def _ppa_index(*packages):
    text = "\n\n".join(
        f"Package: {name}\nVersion: 1.0\nFilename: pool/main/r/{name}/{name}_1.0_amd64.deb\nSHA256: {SHA}"
        for name in packages
    )
    return gzip.compress(text.encode())


def test_ubuntu_takes_the_packages_from_the_ppas_with_their_sha256(monkeypatch):
    fetched = []

    def get(url, limit=tools.INDEX_LIMIT):
        fetched.append(url)
        if "/restate/" in url:
            return _ppa_index("restate", "restate-proxy", "restate-doc")
        return _ppa_index("sysmanage-agent")

    monkeypatch.setattr(tools, "_get", get)
    items = tools.resolve("ubuntu", "24.04")
    assert all("/dists/noble/" in url for url in fetched)  # 24.04 is noble
    names = sorted({i["name"] for i in items})
    assert names == [
        "restate-proxy_1.0_amd64.deb",
        "restate_1.0_amd64.deb",
        "sysmanage-agent_1.0_amd64.deb",
    ]
    assert all(
        i["sha256"] == SHA and i["url"].startswith("https://ppa.launchpadcontent.net/")
        for i in items
    )


def test_el_takes_github_release_assets_by_their_digests(monkeypatch):
    def get(url, limit=tools.INDEX_LIMIT):
        repo = "restate" if "/restate/" in url else "agent"
        names = {
            "restate": ["restate-3.2-1.el9.x86_64.rpm", "restate-proxy-3.2-1.el9.x86_64.rpm",
                        "restate-3.2-1.el10.x86_64.rpm", "restate-3.2-1.opensuseleap16.0.x86_64.rpm"],
            "agent": ["sysmanage-agent-3.13-1.x86_64.rpm", "sysmanage-agent-3.13-0.sles.x86_64.rpm"],
        }[repo]  # fmt: skip
        return json.dumps({"assets": [
            {"name": n, "browser_download_url": f"https://github.com/x/{n}", "digest": f"sha256:{SHA}"}
            for n in names]}).encode()  # fmt: skip

    monkeypatch.setattr(tools, "_get", get)
    names = {i["name"] for i in tools.resolve("rocky", "9.5")}
    assert names == {"restate-3.2-1.el9.x86_64.rpm", "restate-proxy-3.2-1.el9.x86_64.rpm",
                     "sysmanage-agent-3.13-1.x86_64.rpm"}  # fmt: skip


def test_an_unreachable_source_or_an_unserved_distro_gives_nothing(monkeypatch):
    def broken(url, limit=tools.INDEX_LIMIT):
        raise OSError("no route")

    monkeypatch.setattr(tools, "_get", broken)
    assert tools.resolve("ubuntu", "24.04") == []
    assert tools.resolve("alpine", "3.22") == [] and tools.family("freebsd") is None


def test_the_fetch_never_fails_the_mirror_run_and_is_checked():
    target = {"distro": "ubuntu", "version": "noble",
              "items": [{"name": "restate_1.0_amd64.deb", "url": "https://x/r.deb", "sha256": SHA}]}  # fmt: skip
    plan = tools.fetch_plan("/var/lib/sysmanage/airgap-staging/r1", [target])
    folder = "/var/lib/sysmanage/airgap-staging/r1/sysmanage-tools/ubuntu/noble"
    assert all(c["ignore_errors"] for c in plan["commands"])
    argvs = [c["argv"] for c in plan["commands"]]
    assert ["sudo", "curl", "-fsSL", "--max-time", "1800", "-o", f"{folder}/restate_1.0_amd64.deb",
            "https://x/r.deb"] in argvs  # fmt: skip
    assert argvs[-1] == ["sudo", "sha256sum", "-c", "--quiet", f"{folder}/SHA256SUMS"]
    assert plan["files"][0]["content"] == f"{SHA}  restate_1.0_amd64.deb\n"
    # The signed manifest carries names and hashes, never a URL.
    entry = tools.manifest_entries([target])[0]
    assert entry["files"] == [{"name": "restate_1.0_amd64.deb", "sha256": SHA}]


def _deb(folder, name="restate"):
    root = os.path.join(folder, "pkg")
    os.makedirs(os.path.join(root, "DEBIAN"))
    with open(os.path.join(root, "DEBIAN", "control"), "w", encoding="ascii") as out:
        out.write(f"Package: {name}\nVersion: 1.0\nArchitecture: all\nMaintainer: t <t@t>\n"
                  "Description: test\n")  # fmt: skip
    path = os.path.join(folder, f"{name}_1.0_all.deb")
    subprocess.run(
        ["dpkg-deb", "--build", "-Zgzip", root, path], check=True, capture_output=True
    )
    shutil.rmtree(root)
    with open(path, "rb") as handle:
        return path, hashlib.sha256(handle.read()).hexdigest()


@pytest.mark.skipif(not (shutil.which("gpg") and shutil.which("apt-ftparchive") and shutil.which("dpkg-deb")),
                    reason="needs gpg, apt-ftparchive and dpkg-deb")  # fmt: skip
def test_an_ingest_builds_a_signed_apt_repository_of_what_matches(tmp_path):
    repo_root = tmp_path / "airgap-repo"
    media = repo_root / "sysmanage-tools" / "ubuntu" / "noble"
    media.mkdir(parents=True)
    good, good_sha = _deb(str(media), "restate")
    bad, _bad_sha = _deb(str(media), "restate-proxy")
    manifest = {"tools": [{"distro": "ubuntu", "version": "noble", "files": [
        {"name": os.path.basename(good), "sha256": good_sha},
        {"name": os.path.basename(bad), "sha256": "0" * 64},  # swapped on the way
    ]}]}  # fmt: skip
    [result] = tools.build(str(repo_root), manifest)
    assert result["error"] is None and result["kept"] == [os.path.basename(good)]
    served = tmp_path / "airgap-tools" / "ubuntu" / "noble"
    assert (served / "Packages").read_text().count("Package: ") == 1
    assert tools.served(str(repo_root), "ubuntu", "noble")
    # The index verifies against the published key, and only against it.
    key = tools.public_key(str(repo_root))
    assert key.startswith("-----BEGIN PGP PUBLIC KEY BLOCK-----")
    check = tmp_path / "check"
    check.mkdir(mode=0o700)
    env = {**os.environ, "GNUPGHOME": str(check)}
    subprocess.run(["gpg", "--batch", "--import", str(tmp_path / "airgap-tools" / tools.KEY_FILE)],
                   env=env, check=True, capture_output=True)  # fmt: skip
    verify = subprocess.run(["gpg", "--batch", "--verify", str(served / "InRelease")],
                            env=env, capture_output=True)  # fmt: skip
    assert verify.returncode == 0
    # The private key stays on the server, never beside what is served.
    assert not any("PRIVATE" in p.read_text(errors="ignore")
                   for p in (tmp_path / "airgap-tools").rglob("*") if p.is_file())  # fmt: skip


def test_an_rpm_repository_without_createrepo_says_so_and_serves_nothing(
    tmp_path, monkeypatch
):
    repo_root = tmp_path / "airgap-repo"
    media = repo_root / "sysmanage-tools" / "fedora" / "44"
    media.mkdir(parents=True)
    (media / "restate-1.rpm").write_bytes(b"rpm")
    sha = hashlib.sha256(b"rpm").hexdigest()
    monkeypatch.setattr(tools, "ensure_key", lambda root: str(tmp_path / "k.asc"))
    real_which = shutil.which
    monkeypatch.setattr(
        tools.shutil,
        "which",
        lambda name: None if name == "createrepo_c" else real_which(name),
    )
    [result] = tools.build(str(repo_root), {"tools": [{"distro": "fedora", "version": "44",
                                                       "files": [{"name": "restate-1.rpm", "sha256": sha}]}]})  # fmt: skip
    assert "createrepo_c" in result["error"]
    assert not tools.served(str(repo_root), "fedora", "44")


def test_a_path_in_the_manifest_never_leaves_the_tools_tree(tmp_path):
    assert tools.build(str(tmp_path / "airgap-repo"), {"tools": [
        {"distro": "../../etc", "version": "x", "files": []},
        {"distro": "ubuntu", "version": "../noble", "files": []}]}) == []  # fmt: skip


# --- the hosts ---------------------------------------------------------------


KEY = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nx\n-----END PGP PUBLIC KEY BLOCK-----\n"
MIRROR = "http://repo.site.lan/airgap-repo/ubuntu/noble/mirror"


def test_apt_hosts_get_the_tools_repository_signed_by_the_site_key():
    _kind, plan = repoint.repoint_plan("ubuntu", MIRROR, "noble")
    url = repoint.tools_url(MIRROR, "ubuntu", "noble")
    assert url == "http://repo.site.lan/airgap-tools/ubuntu/noble"
    plan = repoint._with_tools("apt", plan, url, KEY)
    files = {f["path"]: f["content"] for f in plan["files"]}
    assert files[repoint.TOOLS_APT_KEY] == KEY
    assert files["/etc/apt/sources.list.d/sysmanage-tools.list"] == (
        f"deb [signed-by={repoint.TOOLS_APT_KEY}] {url} ./\n")  # fmt: skip
    assert plan["commands"][-1]["argv"] == ["sudo", "apt-get", "update"]


def test_dnf_hosts_enable_it_after_switching_the_rest_off():
    _kind, plan = repoint.repoint_plan("fedora", MIRROR, "")
    plan = repoint._with_tools("dnf", plan, "http://repo/airgap-tools/fedora/44", KEY)
    files = {f["path"]: f["content"] for f in plan["files"]}
    repo = files["/etc/yum.repos.d/sysmanage-tools.repo"]
    assert (
        "repo_gpgcheck=1" in repo and f"gpgkey=file://{repoint.TOOLS_RPM_KEY}" in repo
    )
    argvs = [c["argv"] for c in plan["commands"]]
    off = argvs.index(["sudo", "dnf", "config-manager", "--set-disabled", "*"])
    on = argvs.index(
        ["sudo", "dnf", "config-manager", "--set-enabled", "sysmanage-tools"]
    )
    assert off < on and argvs[-1] == ["sudo", "dnf", "makecache"]


def test_zypper_imports_only_through_the_repository_key():
    _kind, plan = repoint.repoint_plan("opensuse-leap", MIRROR, "")
    plan = repoint._with_tools(
        "zypper", plan, "http://repo/airgap-tools/opensuse-leap/16.0", KEY
    )
    argvs = [c["argv"] for c in plan["commands"]]
    assert argvs[-1] == [
        "sudo",
        "zypper",
        "--non-interactive",
        "--gpg-auto-import-keys",
        "refresh",
    ]
    assert not any(
        a[:2] == ["sudo", "rpm"] for a in argvs
    )  # sudoers grants no rpm --import


def test_no_tools_repository_until_an_ingest_built_one(tmp_path, monkeypatch):
    from backend.services import (
        airgap_ingest_tick,
    )  # noqa: PLC0415  pylint: disable=import-outside-toplevel

    monkeypatch.setattr(airgap_ingest_tick, "REPO_ROOT", str(tmp_path / "airgap-repo"))
    repo = SimpleNamespace(distro="ubuntu", version="noble", repo_url=MIRROR)
    assert repoint._tools_for(repo) is None


# --- the collector run and the ingest ------------------------------------------


def test_the_collection_run_fetches_the_tools_and_signs_their_list(monkeypatch):
    from backend.services import (
        airgap_run_tick,
    )  # noqa: PLC0415  pylint: disable=import-outside-toplevel

    item = {"name": "restate_1.0_amd64.deb", "url": "https://x/r.deb", "sha256": SHA}
    monkeypatch.setattr(tools, "resolve", lambda distro, version: [item])
    run = SimpleNamespace(id="r1", targets=[SimpleNamespace(distro="ubuntu", version="noble")],
                          tools_manifest=None)  # fmt: skip
    plan = {"commands": [{"argv": ["sudo", "rsync"]}], "files": []}
    airgap_run_tick._add_tools(run, plan)
    assert plan["commands"][0]["argv"] == ["sudo", "rsync"]  # the mirror first
    assert any(c["argv"][:2] == ["sudo", "curl"] for c in plan["commands"])
    assert airgap_run_tick._tools_manifest(run) == [
        {"distro": "ubuntu", "version": "noble", "files": [{"name": item["name"], "sha256": SHA}]}]  # fmt: skip


def test_the_tools_column_comes_and_goes_idempotently():
    import tempfile  # noqa: PLC0415  pylint: disable=import-outside-toplevel

    from tests.test_backup_proxy_migration import (
        _columns,
    )  # noqa: PLC0415  pylint: disable=import-outside-toplevel
    from tests.test_backup_rules_migration import (
        _alembic,
    )  # noqa: PLC0415  pylint: disable=import-outside-toplevel

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        assert "tools_manifest" in _columns(db_path, "airgap_collection_run")
        _alembic(["stamp", "q88pmrepair"], db_path)
        _alembic(["upgrade", "head"], db_path)
        _alembic(["downgrade", "q88pmrepair"], db_path)
        assert "tools_manifest" not in _columns(db_path, "airgap_collection_run")
        _alembic(["upgrade", "head"], db_path)
    finally:
        os.unlink(db_path)
