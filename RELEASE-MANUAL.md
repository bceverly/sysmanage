# SysManage Server - Manual Release Guide

This document describes how to perform a manual release of the SysManage server when
GitHub Actions CI/CD is unavailable (e.g., during GitHub outages or for air-gapped
environments).

## Overview

The normal release process is fully automated via GitHub Actions: pushing a tag
matching `v*.*.*` or `v*.*.*.*` triggers builds across all platforms, publishes to
package repositories, and stages artifacts in sysmanage-docs. This manual process
replicates that pipeline using local machines.

**Key concept: Multi-machine additive workflow.** Each machine runs `make release-local`,
which builds packages for its native platform and stages them into a shared
sysmanage-docs repository. You run this on as many machines as needed to cover all
target platforms. Each run is additive -- existing packages from other platforms are
preserved.

## Prerequisites

### 1. Verify credentials

| Credential | Purpose | How to verify |
|------------|---------|---------------|
| GPG signing key | Signing DEB source packages | `gpg --list-secret-keys` |
| Launchpad PPA access | Ubuntu PPA uploads | Check `~/.dput.cf` or `~/.dput.d/` |
| OBS account | openSUSE Build Service | Check `~/.config/osc/oscrc` |
| COPR API token | Fedora COPR builds | Check `~/.config/copr` |
| Snap Store login | Snap publishing | `snapcraft whoami` |

### 2. Install deployment tools

```bash
cd ~/dev/sysmanage
make deploy-check-deps
```

This checks for all required tools and prints install instructions for any that are
missing. The full list:

- **Launchpad**: `dch`, `debuild`, `debsign`, `dput`, `gpg`
  ```bash
  sudo apt-get install -y devscripts debhelper dh-python python3-all python3-setuptools dput-ng gnupg
  ```
- **OBS**: `osc`
  ```bash
  sudo apt-get install -y osc
  ```
- **COPR**: `copr-cli`, `rpmbuild`
  ```bash
  pip3 install copr-cli
  sudo apt-get install -y rpm    # or: sudo dnf install -y rpm-build
  ```
- **Snap Store**: `snapcraft`
  ```bash
  sudo snap install snapcraft --classic
  ```
- **Docs repo metadata**: `dpkg-scanpackages`, `createrepo_c`
  ```bash
  sudo apt-get install -y dpkg-dev
  sudo apt-get install -y createrepo-c    # or: sudo dnf install -y createrepo_c
  ```
- **Docker** (for Alpine builds): `docker`
  ```bash
  # See https://docs.docker.com/engine/install/
  ```
- **Release artifacts**: `sha256sum`, `apt-ftparchive`, `cyclonedx-bom`
  ```bash
  pip3 install cyclonedx-bom
  ```

### 3. Clone or update sysmanage-docs

The docs repo is where all built packages are staged before being pushed to GitHub
Pages. By default, it is expected at `~/dev/sysmanage-docs`. Override with the
`DOCS_REPO` environment variable.

```bash
# First time:
cd ~/dev
git clone git@github.com:bceverly/sysmanage-docs.git

# Or if it already exists, pull latest:
cd ~/dev/sysmanage-docs
git pull
```

## Machine Matrix

### Minimum machines for a complete release

| Machine | OS | What gets built |
|---------|----|-----------------|
| Linux (Ubuntu/Debian) | Ubuntu 22.04+ | `.deb`, `.rpm` (CentOS + openSUSE), `.snap`, Alpine `.apk` (via Docker), Launchpad PPA, OBS, COPR |
| macOS | macOS 13+ | `.pkg` (universal) |
| Windows | Windows 10+ with WiX Toolset v4 | `.msi` (x64 + ARM64) |

### Full coverage (optional additional machines)

| Machine | OS | What gets built |
|---------|----|-----------------|
| FreeBSD | FreeBSD 13+ | FreeBSD `.pkg` |
| NetBSD | NetBSD 10+ | NetBSD `.tgz` |
| OpenBSD | OpenBSD 7.x | OpenBSD port tarball |

On Linux, all deploy targets (Launchpad, OBS, COPR, Snap Store) are available. On
other platforms, only the native package build and docs-repo staging run.

## Step-by-Step Workflow

### Step 0: Prepare the release

Ensure all changes are merged to `main` and tests pass.

```bash
cd ~/dev/sysmanage

# Verify you are on main and up to date
git checkout main
git pull origin main

# Run tests to confirm everything passes
make test
make lint
```

### Step 1: Tag the release

Tags must match the pattern `v*.*.*` (e.g., `v1.2.3`) or `v*.*.*.*` (e.g., `v0.9.0.3`).
This is the same tag format that triggers the CI/CD pipeline.

```bash
# Create an annotated tag (recommended)
git tag -a v1.2.3 -m "Release v1.2.3"

# Or a lightweight tag
git tag v1.2.3

# Push the tag (if GitHub is reachable; otherwise push later)
git push origin v1.2.3
```

If you need to override the version detected from the tag, set the `VERSION`
environment variable for any command:

```bash
VERSION=1.2.3 make release-local
```

### Step 2: Run on Linux (primary build machine)

This is the main build machine. It handles the most targets.

```bash
cd ~/dev/sysmanage
make release-local
```

The command is interactive -- it detects your OS and prompts before each step. Answer
`y` to execute a step or `n` to skip it. Here is what each step does:

**Step 1 -- Build packages for current platform:**
```bash
# On Ubuntu/Debian, this runs:
make installer-deb
# On CentOS/RHEL/Fedora:
make installer-rpm-centos
# On openSUSE/SLES:
make installer-rpm-opensuse
```
Produces packages in `installer/dist/`.

**Step 2 -- Generate SBOM:**
```bash
make sbom
```
Creates `sbom/backend-sbom.json` and `sbom/frontend-sbom.json` in CycloneDX format.

**Step 3 -- Generate checksums:**
```bash
make checksums
```
Creates `.sha256` files for every package in `installer/dist/`.

**Step 4 -- Generate release notes:**
```bash
make release-notes
```
Creates `installer/dist/release-notes-VERSION.md` with installation instructions
for every platform.

**Step 5 -- Stage to docs repo:**
```bash
make deploy-docs-repo
```
Copies packages from `installer/dist/` into `~/dev/sysmanage-docs/repo/server/`
organized by platform (deb, rpm, macos, windows, freebsd, alpine, snap, sbom).
Regenerates DEB and RPM repository metadata if the tools are available.

**Step 6 -- Deploy to Launchpad PPA (Ubuntu):**
```bash
make deploy-launchpad
```
Builds signed source packages for each Ubuntu release (questing, noble,
jammy) and uploads them via `dput` to `ppa:bceverly/sysmanage`.
Override target releases: `LAUNCHPAD_RELEASES="noble jammy" make deploy-launchpad`
Override GPG key: `LAUNCHPAD_GPG_KEY=ABCDEF12 make deploy-launchpad`
If your GPG key has a passphrase, set `LAUNCHPAD_GPG_PASSPHRASE`.

**Step 7 -- Deploy to OBS (openSUSE):**
```bash
make deploy-obs
```
Checks out `home:USERNAME/sysmanage` from OBS, creates source + vendor tarballs,
updates the spec file version, and commits. OBS then builds RPMs automatically.
Override credentials: `OBS_USERNAME=user OBS_PASSWORD=pass make deploy-obs`

**Step 8 -- Deploy to COPR (Fedora):**
```bash
make deploy-copr
```
Creates an SRPM with vendored Python wheels (3.12 + 3.13) and uploads it to
`USERNAME/sysmanage` on Fedora COPR. COPR builds RPMs for enabled chroots.
Override credentials: `COPR_LOGIN=x COPR_API_TOKEN=y COPR_USERNAME=z make deploy-copr`

**Step 9 -- Deploy to Snap Store:**
```bash
make deploy-snap
```
Builds a snap with `snapcraft pack` and uploads to the Snap Store stable channel.
Requires prior `snapcraft login`.

**Step 10 -- Build Alpine packages (Docker required):**
```bash
make installer-alpine
```
Pulls Alpine Docker images (3.19, 3.20, 3.21 by default) and runs `abuild` inside
each container. Produces `installer/dist/sysmanage-VERSION-alpineXYZ.apk`.
Override versions: `ALPINE_VERSIONS="3.20 3.21" make installer-alpine`

If you prefer to run individual targets instead of the interactive pipeline:

```bash
cd ~/dev/sysmanage
VERSION=1.2.3 make installer-deb
VERSION=1.2.3 make installer-alpine
VERSION=1.2.3 make sbom
VERSION=1.2.3 make checksums
VERSION=1.2.3 make release-notes
VERSION=1.2.3 make deploy-docs-repo
VERSION=1.2.3 make deploy-launchpad
VERSION=1.2.3 make deploy-obs
VERSION=1.2.3 make deploy-copr
VERSION=1.2.3 make deploy-snap
```

### Step 3: Run on macOS

```bash
cd ~/dev/sysmanage
make release-local
```

This detects macOS and runs:

```bash
make installer-macos    # builds .pkg with pkgbuild + productbuild
make sbom
make checksums
make release-notes
make deploy-docs-repo   # stages .pkg to sysmanage-docs/repo/server/macos/VERSION/
```

Prerequisites: Xcode command-line tools (`xcode-select --install` for `pkgbuild`
and `productbuild`).

### Step 4: Run on Windows

From Git Bash or MSYS2 (requires WiX Toolset v4):

```bash
cd ~/dev/sysmanage
make release-local
```

This detects MINGW/MSYS and runs:

```bash
make installer-msi-all  # builds .msi for x64 and ARM64 via PowerShell + WiX
make sbom
make checksums
make release-notes
make deploy-docs-repo   # stages .msi files to sysmanage-docs/repo/server/windows/VERSION/
```

### Step 5: Run on BSD machines (optional)

On each BSD machine:

```bash
cd ~/dev/sysmanage
make release-local
```

The OS is auto-detected:

| OS | Build target | Output |
|----|-------------|--------|
| FreeBSD | `make installer-freebsd` | `installer/dist/*freebsd*.pkg` |
| NetBSD | `make installer-netbsd` | `installer/dist/*.tgz` |
| OpenBSD | `make installer-openbsd` | `installer/dist/*.tar.gz` |

Each then runs checksums, release-notes, and deploy-docs-repo to stage the
platform-specific packages.

### Step 6: Verify the docs repo

After running on all machines, verify that all platforms are represented:

```bash
cd ~/dev/sysmanage-docs

# Check each platform directory
ls -la repo/server/deb/pool/main/
ls -la repo/server/rpm/centos/
ls -la repo/server/rpm/opensuse/
ls -la repo/server/macos/
ls -la repo/server/windows/
ls -la repo/server/freebsd/
ls -la repo/server/alpine/
ls -la repo/server/snap/
ls -la repo/server/sbom/
```

### Step 7: Commit and push sysmanage-docs

When GitHub access is restored:

```bash
cd ~/dev/sysmanage-docs
git add repo/
git status              # review what will be committed
git commit -m "Release sysmanage v1.2.3"
git push
```

## Running Individual Targets Without the Pipeline

You do not have to use `make release-local`. Every target can be run individually.

### Build a single package type

```bash
VERSION=1.2.3 make installer-deb
VERSION=1.2.3 make installer-alpine
VERSION=1.2.3 make installer-rpm-centos
VERSION=1.2.3 make installer-rpm-opensuse
VERSION=1.2.3 make installer-macos
VERSION=1.2.3 make installer-msi-all
VERSION=1.2.3 make installer-freebsd
VERSION=1.2.3 make installer-netbsd
VERSION=1.2.3 make installer-openbsd
VERSION=1.2.3 make snap
```

### Publish to a single repository

```bash
VERSION=1.2.3 make deploy-launchpad
VERSION=1.2.3 make deploy-obs
VERSION=1.2.3 make deploy-copr
VERSION=1.2.3 make deploy-snap
VERSION=1.2.3 make deploy-docs-repo
```

### Generate artifacts only

```bash
make sbom                       # CycloneDX SBOM in sbom/
make checksums                  # SHA256 files in installer/dist/
VERSION=1.2.3 make release-notes  # Release notes in installer/dist/
```

## Target Reference

### Package Build Targets

| Target | Description | Platform | Output |
|--------|-------------|----------|--------|
| `installer` | Auto-detect platform and build | Any | Varies |
| `installer-deb` | Ubuntu/Debian `.deb` package | Linux | `installer/dist/*.deb` |
| `installer-alpine` | Alpine `.apk` packages via Docker | Linux (Docker) | `installer/dist/*alpine*.apk` |
| `installer-rpm-centos` | CentOS/RHEL `.rpm` package | Linux | `installer/dist/*.rpm` |
| `installer-rpm-opensuse` | openSUSE `.rpm` with vendor deps | Linux | `installer/dist/*.rpm` |
| `installer-macos` | macOS `.pkg` installer | macOS | `installer/dist/*.pkg` |
| `installer-msi-all` | Windows `.msi` for x64 and ARM64 | Windows | `installer/dist/*.msi` |
| `installer-freebsd` | FreeBSD `.pkg` package | FreeBSD | `installer/dist/*.pkg` |
| `installer-netbsd` | NetBSD `.tgz` package | NetBSD | `installer/dist/*.tgz` |
| `installer-openbsd` | OpenBSD port tarball | OpenBSD | `installer/dist/*.tar.gz` |
| `snap` | Snap package (strict confinement) | Linux | `*.snap` |

### Deploy Targets

| Target | Description | Credentials needed |
|--------|-------------|--------------------|
| `deploy-check-deps` | Verify all deployment tools installed | None |
| `checksums` | Generate SHA256 checksums for `installer/dist/` | None |
| `release-notes` | Generate release notes markdown | None |
| `deploy-launchpad` | Upload source packages to Launchpad PPA | GPG key, `~/.dput.cf` |
| `deploy-obs` | Upload to openSUSE Build Service | `~/.config/osc/oscrc` |
| `deploy-copr` | Build SRPM and upload to Fedora COPR | `~/.config/copr` |
| `deploy-snap` | Build and publish snap to Snap Store | `snapcraft login` |
| `deploy-docs-repo` | Stage all packages into sysmanage-docs | None (local) |
| `release-local` | Full interactive pipeline (combines above) | All of the above |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VERSION` | Auto-detected from git tag | Override the release version (e.g., `VERSION=1.2.3`) |
| `DOCS_REPO` | `~/dev/sysmanage-docs` | Path to the sysmanage-docs repository |
| `ALPINE_VERSIONS` | `3.19 3.20 3.21` | Space-separated Alpine versions to build |
| `LAUNCHPAD_RELEASES` | `questing noble jammy` | Space-separated Ubuntu releases for PPA |
| `LAUNCHPAD_GPG_KEY` | Auto-detected from keyring | GPG key ID for signing source packages |
| `LAUNCHPAD_GPG_PASSPHRASE` | (none) | GPG passphrase for non-interactive signing |
| `OBS_USERNAME` | Read from `~/.config/osc/oscrc` | OBS username |
| `OBS_PASSWORD` | Read from `~/.config/osc/oscrc` | OBS password |
| `COPR_LOGIN` | Read from `~/.config/copr` | COPR login |
| `COPR_API_TOKEN` | Read from `~/.config/copr` | COPR API token |
| `COPR_USERNAME` | Read from `~/.config/copr` | COPR username |
| `GPG_KEY_ID` | Auto-detected from keyring | GPG key for signing packages |

### Alpine Package Build Details

The `installer-alpine` target uses Docker to replicate the CI/CD Alpine build:

1. Pulls `alpine:X.Y` Docker images for each configured version
2. Mounts the workspace and runs `installer/alpine/docker-build.sh` inside each container
3. The script installs `alpine-sdk`, `python3`, `py3-pip`, `nodejs`, `npm`
4. Copies `APKBUILD` and supporting files from `installer/alpine/`
5. Updates `pkgver`, generates a signing key, runs `abuild -r`
6. Extracts the `.apk` to the workspace root
7. The Makefile renames it to `sysmanage-VERSION-alpineXYZ.apk` and moves it to `installer/dist/`

Requirements: Docker must be installed and the current user must have Docker
access (typically via the `docker` group).

```bash
# Build for all default Alpine versions:
make installer-alpine

# Build for specific versions:
ALPINE_VERSIONS="3.21" make installer-alpine

# With explicit version:
VERSION=1.2.3 ALPINE_VERSIONS="3.20 3.21" make installer-alpine
```
