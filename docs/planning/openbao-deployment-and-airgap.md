# OpenBAO Deployment & the Air-Gap Appliance Model

**Status:** Design / decided (June 2026)
**Scope:** Making OpenBAO a first-class, installed-and-running dependency on **every**
supported OS/version, and the architectural invariants that keep air-gapped
deployments simple. Companion to
[`phase13-multi-tenancy-design.md`](phase13-multi-tenancy-design.md) — OpenBAO is
the credential broker that multi-tenancy (Phase 13.1.C) depends on, so it must be
present everywhere the server runs.

---

## 1. Why this exists

Phase 13.1 makes OpenBAO central: it brokers dynamic per-tenant DB credentials, and
it already backs the Pro+ secrets-management / dynamic-lease features (Phase 8.7 /
12.5). Two requirements follow:

- **(a) Server support on every supported OS/version.** Already essentially done —
  `backend/api/openbao.py` (`find_bao_binary()`) and `VaultService` are
  binary-name based and OS-agnostic; they only need a `bao` binary on `PATH` /
  `/usr/local/bin` / `~/.local/bin`.
- **(b) A clean install of OpenBAO built into the installer for each OS/version.**
  This is the gap: as of June 2026 **none of the 11 production installers** install
  or start OpenBAO. It was a dev-only concern (`make install-dev` →
  `scripts/install-openbao.py`).

## 2. OpenBAO platform reality (the key finding)

As of **OpenBAO v2.5.4** the official GitHub release ships **prebuilt binaries for
every OS in our support matrix**, including the BSDs:

| OS | Prebuilt binaries | Native package |
|---|---|---|
| Linux | x86_64, arm64, armv6, riscv64, ppc64le, s390x (+ HSM) | **`.deb` + `.rpm`**; official apt repo `pkg.openbao.org/deb` |
| macOS | x86_64, arm64 | tarball only |
| FreeBSD | x86_64, armv6, arm64 | `pkg install openbao` |
| **OpenBSD** | **x86_64, armv6, arm64** | tarball only |
| **NetBSD** | **x86_64, armv6, arm64** | tarball only |
| Windows | x86_64, armv6, arm64 | zip only |

Consequences:

- **The "build OpenBAO from source on OpenBSD/NetBSD" path is OBSOLETE.**
  `scripts/build-openbao.sh` + the OpenBSD/NetBSD source-build branches in
  `scripts/install-openbao.py` predate the prebuilt BSD tarballs. They become a
  *fallback only* (kept for the case where a prebuilt binary won't run — see the
  OpenBSD caveat below).
- **`bao` is a single static Go binary (CGO disabled) with no runtime dependency
  tree.** It runs on glibc *and* musl (Alpine). "OpenBAO and all its dependencies"
  is, in practice, one file. This is what makes air-gap bundling trivial (§4).

### OpenBSD caveat (the one real risk)
OpenBSD enforces syscall-origin pinning + `W^X`; cross-compiled Go binaries usually
run on `openbsd/amd64` but are OpenBSD-version-sensitive. **The prebuilt tarball
must be smoke-tested on real OpenBSD 7.7/7.8.** If it fails, OpenBSD falls back to
the existing source-build path.

## 3. Install strategy (decided)

**Native package where it exists, official tarball elsewhere** (the chosen option):

- **Linux** (Ubuntu/Debian/RHEL family/openSUSE): the `.deb`/`.rpm` (or the official
  apt/dnf repo). Declared deps are trivial (a service user + the unit file).
- **FreeBSD**: `pkg install openbao` (ports).
- **OpenBSD / NetBSD / macOS / Windows / Alpine**: extract the pinned official
  release tarball/zip and drop `bao` in a fixed path (Alpine is musl — the static
  Linux binary runs there; there is no `.apk`).

Pin a specific OpenBAO version with **checksum + signature (GPG / sigstore)
verification** at install time. Each platform installer also writes the service
definition (systemd / OpenRC / rc.d / launchd / Windows service / snap).

## 4. Air-gap bundling — assurance

The air-gap **server** bundle (`scripts/buildAirGapBundle.sh` → mega-ISO; dispatched
by `installer/airgap-bundle/install.sh`) already builds a per-platform subdir
containing the package, **its native-package dependency closure** (`apt-deps/` /
`deps/`), and Python wheels. OpenBAO slots into that existing mechanism:

- **Linux**: add `openbao` to the package set whose closure is downloaded
  (`apt-get download` / `dnf download --resolve`) into the per-platform deps dir.
- **BSD / macOS / Windows**: stage the pinned release tarball/zip as a release asset
  in the platform subdir (these are already "release-asset platforms" in the
  builder).

Because `bao` is a single dependency-free static binary, **there is no transitive
dependency closure to chase** — bundling it is adding one file (plus, on Linux, a
trivial `.deb`/`.rpm` wrapper). A user deploying an air-gapped server gets a fully
self-contained OpenBAO.

## 5. Architectural invariants for air-gapped deployments (decided)

An air-gapped server runs the **repository** role. Two invariants make it a simple,
certifiable **appliance**:

### 5.1 Air-gapped = single-tenant, single local database
Multi-tenancy is **not supported** on air-gapped deployments. The whole point of
multi-tenancy is internet-facing, multi-DB SaaS with **customer-owned SSO**
(Entra/Okta/OIDC/SAML) — and reaching an external IdP is **definitionally
impossible** offline, so multi-tenant air-gap is self-contradictory at the identity
layer. Air-gapped deployments run the **collapsed single-DB mode**
(`multitenancy.enabled=false`, the default) with everything in one local database.

This also simplifies OpenBAO's air-gap role: a **local single node doing KV/secrets**
for the one local database — *not* the dynamic per-tenant cred broker across N DBs.

### 5.2 The repository role does not participate in federation
A **repository**-role (air-gapped) server can be neither federation **coordinator**
nor **site**. Federation across the gap is physically impossible; federation *within*
an enclave is technically possible but generally fights the network segmentation that
justifies the air gap (cross-segment sync is a new lateral path / auditor red flag).
**If you need scale inside an enclave, deploy independent repository servers per
segment.** Federation remains **fully available** for `standard` and `collector`
deployments — a **collector** (internet-connected bridge) may still be a federation
site; it is not itself air-gapped.

### 5.3 Enforcement (belt-and-suspenders)
- A **startup guard** errors if `multitenancy.enabled` is true on an air-gapped
  (repository) deployment, and if the role is `repository` while federation role is
  `coordinator`/`site`.
- The **config builder** (`scripts/_sysmanage_secure_installation.py`) does not offer
  multi-tenancy or federation when the role is `repository`.

Net: **air-gapped repository = single-tenant + single local DB + local OpenBAO + no
federation.** One sentence to test and certify.

## 6. Seal / unseal lifecycle (decided)

OpenBAO boots **sealed** and must be initialized + unsealed to be usable. Baseline
for all deployments:

- **File storage backend + auto-initialize-and-unseal on first boot.** The installer
  configures file storage, initializes on first start, and writes the unseal / root
  material to a **root-owned, `0600`, locked-down** location so the service comes up
  unsealed automatically (hands-off "clean start").
- **Air-gap uses this exclusively** — cloud-KMS auto-unseal is unreachable offline,
  and an air-gapped network is hardened by design, so locally-protected unseal
  material is an acceptable trade (Bryan, June 2026).
- **KMS / transit auto-unseal** for internet-connected hardened deployments is a
  **documented future enhancement**, not GA — the file-storage baseline is the
  shipping mechanism.

## 7. Work to do (installer integration)

For each of the 11 installers + the air-gap bundle builder:
1. Obtain `bao` per §3 (native package or pinned tarball, verified).
2. Create the OpenBAO service unit for that OS's init system.
3. Configure file storage + data dir + auto-init/unseal per §6.
4. Add OpenBAO to the air-gap bundle per §4.
5. Add the §5.3 startup guards + config-builder gating.
6. Retire the source-build path to OpenBSD-only fallback; smoke-test the OpenBSD
   prebuilt binary (§2 caveat).

Sequencing TBD with Bryan (likely: one Linux family first to prove the pattern, then
fan out; OpenBSD verified early because it carries the only real binary risk).
