#!/usr/bin/env bash
# submit-winget.sh — submit sysmanage.sysmanage and
# sysmanage.sysmanage-agent to microsoft/winget-pkgs for a given
# version.
#
# Usage:
#   GITHUB_TOKEN=<pat> VERSION=2.3.0.14 ./scripts/submit-winget.sh
#
# If ``VERSION`` is unset the script reads the latest published
# GitHub release tag from ``bceverly/sysmanage``.  ``GITHUB_TOKEN``
# is always required (forwarded to komac + gh as ``GH_TOKEN`` too).
#
# What it does, in order:
#   1. Pre-flight HEAD-checks the four MSI URLs (server x64/arm64
#      + agent x64/arm64).  Aborts if any aren't reachable yet.
#   2. ``SKIP_STALE_CLOSE=1`` to bypass: searches for any open PRs
#      from this author with the version in the title and closes
#      them with a "superseded by corrected submission" comment.
#      Useful when a prior run submitted a broken manifest (e.g.
#      the CRLF-anchor bug captured below) and you want a clean
#      resubmit.
#   3. For each of the two packages:
#        a. ``komac new --dry-run --output <tmp>`` dumps fresh
#           manifests for ``sysmanage.sysmanage`` /
#           ``sysmanage.sysmanage-agent``.
#        b. Sed-injects ``Dependencies: PackageDependencies:
#           Python.Python.3.12`` into the installer manifest.
#           komac 2.16.0 has no flag for this today.
#        c. POST-INJECTION GREP verifies the marker landed; aborts
#           loud if it didn't.
#        d. ``komac submit --yes <tmp>`` pushes to your fork +
#           opens a PR upstream.
#   4. Posts ``@microsoft-github-policy-service agree`` on each new
#      PR so the CLA bot drops the Needs-CLA label.
#
# CRLF gotcha (the reason the post-injection grep exists):
#   komac writes manifests with CRLF line endings (it's Rust +
#   targets a Windows package manager).  A plain
#   ``^ManifestType: installer$`` regex on Linux silently misses
#   them — sed's ``$`` anchors before the ``\n`` byte but the
#   literal ``\r`` is in the way.  The regex below tolerates the
#   optional CR (``\r\?``), and the inserted lines themselves end
#   in ``\r\`` so the file stays uniformly CRLF after the edit.

set -euo pipefail

# ---------------------------------------------------------------
# Resolve VERSION — env override first, else latest GitHub tag.
# ---------------------------------------------------------------
if [ -z "${VERSION:-}" ]; then
    LATEST_TAG="$(gh release list --repo bceverly/sysmanage --limit 1 \
        --json tagName --jq '.[0].tagName' 2>/dev/null || true)"
    if [ -z "${LATEST_TAG}" ]; then
        echo "ERROR: VERSION not set and 'gh release list' failed." >&2
        echo "       Export VERSION=<x.y.z.w> explicitly and re-run." >&2
        exit 1
    fi
    VERSION="${LATEST_TAG#v}"
    echo "Using latest published tag: v${VERSION}"
fi

PY_DEPENDENCY="Python.Python.3.12"

SERVER_ID="sysmanage.sysmanage"
AGENT_ID="sysmanage.sysmanage-agent"

SERVER_MSI_X64="https://github.com/bceverly/sysmanage/releases/download/v${VERSION}/sysmanage-${VERSION}-windows-x64.msi"
SERVER_MSI_ARM64="https://github.com/bceverly/sysmanage/releases/download/v${VERSION}/sysmanage-${VERSION}-windows-arm64.msi"
AGENT_MSI_X64="https://github.com/bceverly/sysmanage-agent/releases/download/v${VERSION}/sysmanage-agent-${VERSION}-windows-x64.msi"
AGENT_MSI_ARM64="https://github.com/bceverly/sysmanage-agent/releases/download/v${VERSION}/sysmanage-agent-${VERSION}-windows-arm64.msi"

PUBLISHER="SysManage"
PUBLISHER_SUPPORT_URL_SERVER="https://github.com/bceverly/sysmanage/issues"
PUBLISHER_SUPPORT_URL_AGENT="https://github.com/bceverly/sysmanage-agent/issues"
AUTHOR="Bryan Everly"
LICENSE="AGPL-3.0-or-later"
COPYRIGHT="Copyright (c) Bryan Everly"

SERVER_PUBLISHER_URL="https://github.com/bceverly/sysmanage"
SERVER_PACKAGE_NAME="SysManage Server"
SERVER_PACKAGE_URL="https://github.com/bceverly/sysmanage"
SERVER_LICENSE_URL="https://github.com/bceverly/sysmanage/blob/main/LICENSE"
SERVER_SHORT_DESCRIPTION="Open-source fleet management server for SysManage."
SERVER_DESCRIPTION="SysManage is the server-side component of an open-source fleet management platform. It accepts inventory from SysManage Agent hosts, dispatches declarative deployment plans (package install, firewall config, antivirus deployment, VM lifecycle), surfaces health and compliance dashboards, and exposes a REST + WebSocket API for orchestration."
SERVER_MONIKER="sysmanage"

AGENT_PUBLISHER_URL="https://github.com/bceverly/sysmanage-agent"
AGENT_PACKAGE_NAME="SysManage Agent"
AGENT_PACKAGE_URL="https://github.com/bceverly/sysmanage-agent"
AGENT_LICENSE_URL="https://github.com/bceverly/sysmanage-agent/blob/main/LICENSE"
AGENT_SHORT_DESCRIPTION="Cross-platform system management agent for SysManage."
AGENT_DESCRIPTION="SysManage Agent is the host-side daemon for the SysManage open-source fleet management platform. It registers the host with a SysManage server, reports inventory, applies declarative deployment plans (package install, firewall config, antivirus deployment, VM lifecycle), and surfaces real-time health metrics."
AGENT_MONIKER="sysmanage-agent"

if [ -z "${GITHUB_TOKEN:-}" ]; then
    echo "ERROR: GITHUB_TOKEN is not set." >&2
    exit 1
fi
export GH_TOKEN="${GITHUB_TOKEN}"

KOMAC="${KOMAC:-/home/bceverly/.cargo/bin/komac}"
if [ ! -x "${KOMAC}" ]; then
    KOMAC="$(command -v komac || true)"
fi
if [ -z "${KOMAC}" ] || [ ! -x "${KOMAC}" ]; then
    echo "ERROR: komac not found on PATH." >&2
    exit 1
fi

WORK_DIR="$(mktemp -d -t winget-${VERSION}.XXXXXX)"
trap 'rm -rf "${WORK_DIR}"' EXIT
echo "Work directory: ${WORK_DIR}"

# ---------------------------------------------------------------
# Pre-flight 1: confirm the v${VERSION} GitHub releases exist with
# downloadable MSIs.  Fail fast with a clear message if the tag
# hasn't been built yet — saves a confusing komac error.
# ---------------------------------------------------------------
preflight() {
    local url="$1"
    local code
    code="$(curl -ksSI -o /dev/null -w '%{http_code}' --max-time 30 "$url" 2>/dev/null || echo 000)"
    # GitHub releases return 302 to a signed S3 URL; treat 2xx and 3xx as OK.
    case "$code" in
        2*|3*) return 0 ;;
        *)
            echo "ERROR: MSI not reachable: $url (HTTP $code)" >&2
            echo "Make sure the v${VERSION} release workflow has finished." >&2
            return 1
            ;;
    esac
}
echo "Pre-flight: checking that v${VERSION} MSIs are published..."
preflight "$SERVER_MSI_X64"
preflight "$SERVER_MSI_ARM64"
preflight "$AGENT_MSI_X64"
preflight "$AGENT_MSI_ARM64"
echo "  All four MSIs reachable."

# ---------------------------------------------------------------
# Pre-flight 2: close any prior open v${VERSION} PRs from this
# author so we don't end up with two competing submissions at the
# same version.  Set ``SKIP_STALE_CLOSE=1`` to bypass.
# ---------------------------------------------------------------
if [ "${SKIP_STALE_CLOSE:-0}" != "1" ]; then
    echo
    echo "Pre-flight: scanning for stale v${VERSION} PRs to close..."
    STALE_PRS="$(gh search prs \
        --repo microsoft/winget-pkgs \
        --author bceverly \
        --state open \
        --json number,title \
        --jq '.[] | select(.title | contains("'"${VERSION}"'")) | .number' \
        2>/dev/null || true)"
    if [ -z "${STALE_PRS}" ]; then
        echo "  No prior v${VERSION} PRs found.  Proceeding to submission."
    else
        STALE_COMMENT="Superseded by a corrected submission for v${VERSION}.  Closing in favour of the fresh PR."
        for pr in ${STALE_PRS}; do
            echo "  - PR #${pr}: posting supersede comment + closing"
            gh pr comment "${pr}" --repo microsoft/winget-pkgs --body "${STALE_COMMENT}" \
                || echo "    (gh pr comment failed for #${pr}; continuing)"
            gh pr close   "${pr}" --repo microsoft/winget-pkgs \
                --comment "superseded by fresh v${VERSION} submission" \
                || echo "    (gh pr close failed for #${pr}; close it manually)"
        done
        echo "  Stale PR cleanup complete."
    fi
fi

# ---------------------------------------------------------------
# Inject Dependencies block into an installer manifest.  komac
# 2.16.0 has no flag for PackageDependencies so we do it via sed
# after ``komac new --dry-run`` dumps the YAML.  See the CRLF
# gotcha at the top of this file for why the regex looks like it
# does.
# ---------------------------------------------------------------
inject_python_dependency() {
    local manifest="$1"
    if [ ! -f "$manifest" ]; then
        echo "ERROR: expected installer manifest not found: $manifest" >&2
        return 1
    fi
    # Already-injected? (idempotent in case the script is re-run.)
    if grep -q "PackageIdentifier: ${PY_DEPENDENCY}\b" "$manifest"; then
        echo "  Already has ${PY_DEPENDENCY} dependency; skipping injection."
        return 0
    fi
    # Insert the Dependencies block before ManifestType.  The
    # ``\r\?`` matches komac's CRLF; the trailing ``\r\`` on each
    # inserted line preserves CRLF in the output so the YAML
    # parser doesn't see a line-ending mix.
    sed -i '/^ManifestType: installer\r\?$/i\
Dependencies:\r\
  PackageDependencies:\r\
  - PackageIdentifier: '"${PY_DEPENDENCY}"'\r\
' "$manifest"
    # Verify the injection actually landed — silent no-op is the
    # exact failure mode the CRLF tweaks above are guarding
    # against.  If the post-grep doesn't see our marker, bail so
    # the operator notices instead of submitting a broken
    # manifest.
    if ! grep -q "PackageIdentifier: ${PY_DEPENDENCY}\b" "$manifest"; then
        echo "ERROR: sed-injection silently no-op'd on $(basename "$manifest")" >&2
        echo "       (expected to see 'PackageIdentifier: ${PY_DEPENDENCY}'" >&2
        echo "        in the file after sed — manifest may have an" >&2
        echo "        unexpected line-ending convention).  Aborting submit." >&2
        return 1
    fi
    echo "  Injected Dependencies → ${PY_DEPENDENCY} into $(basename "$manifest")."
}

# ---------------------------------------------------------------
# Dump-edit-submit one package.
# ---------------------------------------------------------------
process_package() {
    local pkg_id="$1"
    local short_path="$2"   # e.g. s/sysmanage/sysmanage or s/sysmanage/sysmanage-agent
    shift 2
    local -a komac_args=("$@")

    local pkg_dir="${WORK_DIR}/${pkg_id}"
    mkdir -p "$pkg_dir"

    echo
    echo "============================================================"
    echo " Dumping manifests for ${pkg_id} v${VERSION}"
    echo "============================================================"

    # Use ``komac new`` rather than ``update`` because the package
    # may not yet exist in microsoft/winget-pkgs (the first
    # submission, or a prior one still pending merge).  ``new``
    # generates the manifest from scratch using the per-package
    # metadata passed via ``komac_args``; ``update`` would 404 if
    # the package isn't in master yet.
    "${KOMAC}" new \
        --version "${VERSION}" \
        --dry-run \
        --output "${pkg_dir}" \
        --token "${GITHUB_TOKEN}" \
        "${komac_args[@]}" \
        "${pkg_id}"

    local manifest_dir="${pkg_dir}/manifests/${short_path}/${VERSION}"
    if [ ! -d "$manifest_dir" ]; then
        # komac may place under a slightly different path; locate it.
        manifest_dir="$(find "$pkg_dir" -type d -name "${VERSION}" | head -1)"
    fi
    if [ -z "$manifest_dir" ] || [ ! -d "$manifest_dir" ]; then
        echo "ERROR: could not locate generated manifest dir under $pkg_dir" >&2
        return 1
    fi
    echo "  Manifest dir: $manifest_dir"

    inject_python_dependency "${manifest_dir}/${pkg_id}.installer.yaml"

    echo
    echo "============================================================"
    echo " Submitting ${pkg_id} v${VERSION}"
    echo "============================================================"
    "${KOMAC}" submit --yes --token "${GITHUB_TOKEN}" "$manifest_dir"
}

# ---------------------------------------------------------------
# Server submission
# ---------------------------------------------------------------
process_package \
    "${SERVER_ID}" \
    "s/sysmanage/sysmanage" \
    --urls "${SERVER_MSI_X64}" "${SERVER_MSI_ARM64}" \
    --publisher "${PUBLISHER}" \
    --publisher-url "${SERVER_PUBLISHER_URL}" \
    --publisher-support-url "${PUBLISHER_SUPPORT_URL_SERVER}" \
    --author "${AUTHOR}" \
    --package-name "${SERVER_PACKAGE_NAME}" \
    --package-url "${SERVER_PACKAGE_URL}" \
    --license "${LICENSE}" \
    --license-url "${SERVER_LICENSE_URL}" \
    --copyright "${COPYRIGHT}" \
    --short-description "${SERVER_SHORT_DESCRIPTION}" \
    --description "${SERVER_DESCRIPTION}" \
    --moniker "${SERVER_MONIKER}" \
    --release-notes-url "https://github.com/bceverly/sysmanage/releases/tag/v${VERSION}"

# ---------------------------------------------------------------
# Agent submission
# ---------------------------------------------------------------
process_package \
    "${AGENT_ID}" \
    "s/sysmanage/sysmanage-agent" \
    --urls "${AGENT_MSI_X64}" "${AGENT_MSI_ARM64}" \
    --publisher "${PUBLISHER}" \
    --publisher-url "${AGENT_PUBLISHER_URL}" \
    --publisher-support-url "${PUBLISHER_SUPPORT_URL_AGENT}" \
    --author "${AUTHOR}" \
    --package-name "${AGENT_PACKAGE_NAME}" \
    --package-url "${AGENT_PACKAGE_URL}" \
    --license "${LICENSE}" \
    --license-url "${AGENT_LICENSE_URL}" \
    --copyright "${COPYRIGHT}" \
    --short-description "${AGENT_SHORT_DESCRIPTION}" \
    --description "${AGENT_DESCRIPTION}" \
    --moniker "${AGENT_MONIKER}" \
    --release-notes-url "https://github.com/bceverly/sysmanage-agent/releases/tag/v${VERSION}"

# ---------------------------------------------------------------
# Post-submit: list the new PRs and post the CLA-agree comment
# on each one.  microsoft-github-policy-service[bot] will add the
# Needs-CLA label automatically and the comment removes it.
# ---------------------------------------------------------------
echo
echo "============================================================"
echo " Open PRs after submission:"
echo "============================================================"
NEW_PRS="$(gh search prs \
    --repo microsoft/winget-pkgs \
    --author bceverly \
    --state open \
    --json number,title \
    --jq '.[] | select(.title | contains("'"${VERSION}"'")) | .number')"

if [ -z "${NEW_PRS}" ]; then
    echo "  No PRs found containing version ${VERSION}."
    echo "  Check 'gh search prs --repo microsoft/winget-pkgs --author bceverly' manually."
else
    for pr in ${NEW_PRS}; do
        echo "  - PR #${pr}: posting CLA agree comment"
        gh pr comment "${pr}" --repo microsoft/winget-pkgs \
            --body '@microsoft-github-policy-service agree' || \
            echo "    (gh pr comment failed for #${pr}; post the agree comment manually)"
    done
fi

echo
echo "Done.  Watch the new PRs for validation results."
