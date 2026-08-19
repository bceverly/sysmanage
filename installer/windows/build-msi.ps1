# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

#
# Build Windows MSI Installer for SysManage Server
# Uses WiX Toolset v4 to create MSI package
#
# Usage:
#   .\build-msi.ps1                      # Builds x64 installer
#   .\build-msi.ps1 -Architecture x64    # Builds x64 installer
#   .\build-msi.ps1 -Architecture arm64  # Builds ARM64 installer
#

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("x64", "arm64")]
    [string]$Architecture = "x64"
)

$ErrorActionPreference = "Stop"

Write-Host "=== Building Windows .msi Package ($Architecture) ===" -ForegroundColor Cyan
Write-Host ""

# Check for WiX Toolset
Write-Host "Checking build dependencies..."
if (-not (Get-Command wix -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: WiX Toolset not found." -ForegroundColor Red
    Write-Host "Download from: https://wixtoolset.org/docs/intro/"
    Write-Host "Install WiX Toolset v4 or later"
    exit 1
}
Write-Host "[OK] Build tools available" -ForegroundColor Green
Write-Host ""

# Determine version
Write-Host "Determining version..."
$VERSION = ""

if ($env:VERSION) {
    $VERSION = $env:VERSION
    $VERSION = $VERSION -replace '^v', ''
    Write-Host "Using version from environment: $VERSION" -ForegroundColor Green
} else {
    try {
        $gitVersion = (git describe --tags --abbrev=0 2>&1 | Out-String).Trim()
        if ($gitVersion -notmatch "^fatal:" -and $gitVersion -match "^v?(\d+\.\d+\.\d+)") {
            $VERSION = $Matches[1]
            Write-Host "Building version: $VERSION (from git tag)" -ForegroundColor Green
        }
    } catch {
    }
}

if ([string]::IsNullOrEmpty($VERSION)) {
    $epoch = Get-Date "2025-01-01"
    $now = Get-Date
    $daysSinceEpoch = [int]($now - $epoch).TotalDays
    $hour = $now.Hour
    $buildNum = $daysSinceEpoch * 100 + $hour
    $VERSION = "0.1.$buildNum"
    Write-Host "No git tags found, auto-generated version: $VERSION" -ForegroundColor Yellow
}
Write-Host ""

# Get paths
$CurrentDir = Get-Location
$OutputDir = Join-Path $CurrentDir "installer\dist"
$WixSource = Join-Path $CurrentDir "installer\windows\sysmanage.wxs"
$OutputMsi = Join-Path $OutputDir "sysmanage-$VERSION-windows-$Architecture.msi"

# Create output directory
Write-Host "Creating output directory..."
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}
Write-Host "[OK] Output directory ready: $OutputDir" -ForegroundColor Green
Write-Host ""

# Check for NSSM (bundled in repo)
Write-Host "Checking for NSSM (Non-Sucking Service Manager)..." -ForegroundColor Cyan
$NssmDir = Join-Path $CurrentDir "installer\windows\nssm"
$NssmExe = Join-Path $NssmDir "nssm.exe"

if (-not (Test-Path $NssmExe)) {
    Write-Host "ERROR: NSSM not found at $NssmExe" -ForegroundColor Red
    Write-Host "NSSM should be bundled in the repository at installer/windows/nssm/nssm.exe" -ForegroundColor Red
    Write-Host "Download from https://nssm.cc/download and extract nssm.exe to that location" -ForegroundColor Yellow
    exit 1
}
Write-Host "[OK] NSSM found" -ForegroundColor Green
Write-Host ""

# Create SBOM files if they don't exist
Write-Host "Checking for SBOM files..." -ForegroundColor Cyan
$SbomDir = Join-Path $CurrentDir "sbom"
$BackendSbom = Join-Path $SbomDir "backend-sbom.json"
$FrontendSbom = Join-Path $SbomDir "frontend-sbom.json"

if (-not (Test-Path $SbomDir)) {
    New-Item -ItemType Directory -Path $SbomDir -Force | Out-Null
}

if (-not (Test-Path $BackendSbom)) {
    Write-Host "  Creating placeholder backend SBOM..." -ForegroundColor Yellow
    $placeholderSbom = @{
        bomFormat = "CycloneDX"
        specVersion = "1.4"
        version = 1
        metadata = @{
            component = @{
                type = "application"
                name = "sysmanage-backend"
                version = $VERSION
            }
        }
        components = @()
    } | ConvertTo-Json -Depth 10
    Set-Content -Path $BackendSbom -Value $placeholderSbom
}

if (-not (Test-Path $FrontendSbom)) {
    Write-Host "  Creating placeholder frontend SBOM..." -ForegroundColor Yellow
    $placeholderSbom = @{
        bomFormat = "CycloneDX"
        specVersion = "1.4"
        version = 1
        metadata = @{
            component = @{
                type = "application"
                name = "sysmanage-frontend"
                version = $VERSION
            }
        }
        components = @()
    } | ConvertTo-Json -Depth 10
    Set-Content -Path $FrontendSbom -Value $placeholderSbom
}

Write-Host "[OK] SBOM files ready" -ForegroundColor Green
Write-Host ""

# Create ZIP files for packaging
Write-Host "Preparing source files for packaging..." -ForegroundColor Cyan

$BackendDir = Join-Path $CurrentDir "backend"
$FrontendDistDir = Join-Path $CurrentDir "frontend\dist"
$AlembicDir = Join-Path $CurrentDir "alembic"

# Verify frontend build exists
if (-not (Test-Path $FrontendDistDir)) {
    Write-Host "ERROR: Frontend build not found at $FrontendDistDir" -ForegroundColor Red
    Write-Host "Run 'make build' first to build the frontend" -ForegroundColor Yellow
    exit 1
}

$BackendZip = Join-Path $CurrentDir "installer\windows\backend.zip"
$FrontendZip = Join-Path $CurrentDir "installer\windows\frontend.zip"
$AlembicZip = Join-Path $CurrentDir "installer\windows\alembic.zip"

# Remove old ZIPs
if (Test-Path $BackendZip) { Remove-Item -Path $BackendZip -Force }
if (Test-Path $FrontendZip) { Remove-Item -Path $FrontendZip -Force }
if (Test-Path $AlembicZip) { Remove-Item -Path $AlembicZip -Force }

# Create ZIPs (only include what's needed for deployment)
$ProgressPreference = 'SilentlyContinue'
Write-Host "  Compressing backend..." -ForegroundColor Gray
Compress-Archive -Path "$BackendDir\*" -DestinationPath $BackendZip -Force
Write-Host "  Compressing frontend (built dist only)..." -ForegroundColor Gray
Compress-Archive -Path "$FrontendDistDir\*" -DestinationPath $FrontendZip -Force
Write-Host "  Compressing alembic..." -ForegroundColor Gray
Compress-Archive -Path "$AlembicDir\*" -DestinationPath $AlembicZip -Force
$ProgressPreference = 'Continue'

$backendSize = ([System.IO.FileInfo]$BackendZip).Length / 1MB
$frontendSize = ([System.IO.FileInfo]$FrontendZip).Length / 1MB
$alembicSize = ([System.IO.FileInfo]$AlembicZip).Length / 1MB

Write-Host "[OK] Source files packaged:" -ForegroundColor Green
Write-Host "  Backend:  $($backendSize | ForEach-Object { '{0:N2}' -f $_ }) MB" -ForegroundColor Gray
Write-Host "  Frontend: $($frontendSize | ForEach-Object { '{0:N2}' -f $_ }) MB" -ForegroundColor Gray
Write-Host "  Alembic:  $($alembicSize | ForEach-Object { '{0:N2}' -f $_ }) MB" -ForegroundColor Gray
Write-Host ""

# ---------------------------------------------------------------------------
# Bundled Python runtime.
#
# The MSI used to hunt for a system Python ("3.9+, first one found").  That is
# unfixable in general: the bundled offline wheels are compiled against exactly
# ONE Python minor via their cpXY ABI tag, and we do not control what the
# operator has installed.  On 2026-08-19 a box with 3.14 got a wheel set built
# for an older minor, pip resolved nothing ("No matching distribution found for
# aiohttp"), and the install still reported success.  Pinning the interpreter
# selection made that failure legible; bundling the interpreter removes it.
#
# python-build-standalone "install_only" builds are relocatable full CPythons
# that include pip and venv, published for both windows arches.  Downloaded at
# BUILD time and shipped inside the MSI, so the install itself needs no network
# and no system Python at all.
#
# Version + hashes are pinned.  Bump $PythonVersion/$PythonRelease and BOTH
# hashes together, then rebuild the ARM64 wheel set against the new version
# (installer\windows\package-arm64-build-deps.ps1).  The wheels and this
# interpreter must stay in lockstep; the ARM64 branch below fails the build if
# they drift, since that set is cross-built elsewhere and cannot be checked here
# any other way.  x64 sidesteps the problem entirely by fetching its wheels with
# this very interpreter.
#
# 3.13 specifically: the cross-built ARM64 wheel set targets cp313, and that set
# is expensive to rebuild (static OpenSSL for cryptography, a special-cased
# grpcio build).  Matching the interpreter to the existing wheels is the cheap
# direction.
$PythonVersion = "3.13.15"
$PythonRelease = "20260814"
$PythonHashes = @{
    "arm64" = "b75b76d7d5ce6db7af426de8ea09d587fe6ac01d1f4238fb6fccda64bf01aee7"
    "x64"   = "4ca61e4b09c2240cc50cc6910c90664051e93ab7caa2f48b3c6b3c070670c0bd"
}
$PythonTriple = @{ "arm64" = "aarch64-pc-windows-msvc"; "x64" = "x86_64-pc-windows-msvc" }

Write-Host "Staging bundled Python $PythonVersion ($Architecture)..." -ForegroundColor Cyan
$PythonZip = Join-Path $CurrentDir "installer\windows\python.zip"
if (Test-Path $PythonZip) { Remove-Item -Path $PythonZip -Force }

$pyAsset = "cpython-$PythonVersion+$PythonRelease-$($PythonTriple[$Architecture])-install_only.tar.gz"
$pyUrl = "https://github.com/astral-sh/python-build-standalone/releases/download/$PythonRelease/$pyAsset"
$pyCache = Join-Path $CurrentDir "installer\windows\.python-cache"
New-Item -ItemType Directory -Path $pyCache -Force | Out-Null
$pyTarball = Join-Path $pyCache $pyAsset

if (-not (Test-Path $pyTarball)) {
    Write-Host "  Downloading $pyAsset..." -ForegroundColor Gray
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest -Uri $pyUrl -OutFile $pyTarball -UseBasicParsing
    $ProgressPreference = 'Continue'
} else {
    Write-Host "  Using cached $pyAsset" -ForegroundColor Gray
}

$pyActual = (Get-FileHash $pyTarball -Algorithm SHA256).Hash.ToLower()
$pyExpected = $PythonHashes[$Architecture].ToLower()
if ($pyActual -ne $pyExpected) {
    Remove-Item $pyTarball -Force -ErrorAction SilentlyContinue
    Write-Host "ERROR: Python runtime checksum mismatch for $Architecture" -ForegroundColor Red
    Write-Host "  expected $pyExpected" -ForegroundColor Red
    Write-Host "  actual   $pyActual" -ForegroundColor Red
    exit 1
}
Write-Host "  Checksum verified" -ForegroundColor Gray

# Repack tar.gz -> zip.  install.ps1 uses Expand-Archive for every other payload
# and Windows PowerShell 5.1 cannot read tar.gz natively, so normalising here
# keeps the install side uniform.  .pdb symbols are dropped: ~40% of the payload
# for files an operator install never uses.
$pyStage = Join-Path $pyCache "extract-$Architecture"
if (Test-Path $pyStage) { Remove-Item -Recurse -Force $pyStage }
New-Item -ItemType Directory -Path $pyStage -Force | Out-Null
& tar -xzf $pyTarball -C $pyStage
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: failed to extract $pyAsset" -ForegroundColor Red; exit 1 }

$pyRoot = Join-Path $pyStage "python"
if (-not (Test-Path (Join-Path $pyRoot "python.exe"))) {
    Write-Host "ERROR: python.exe not found in the extracted runtime ($pyRoot)" -ForegroundColor Red
    exit 1
}
Get-ChildItem $pyRoot -Recurse -Filter *.pdb -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

$ProgressPreference = 'SilentlyContinue'
Compress-Archive -Path "$pyRoot\*" -DestinationPath $PythonZip -Force
$ProgressPreference = 'Continue'
Write-Host ("[OK] Bundled Python packaged: {0:N2} MB" -f (([System.IO.FileInfo]$PythonZip).Length / 1MB)) -ForegroundColor Green
Write-Host ""

# ARM64: stage the libpq runtime DLLs the WiX references (installer\windows\libpq-arm64\).
# Native ARM64 uses pure-Python psycopg, which needs an ARM64 libpq at runtime; x64
# uses psycopg[binary] (libpq bundled in the wheel), so this is arm64-only.
if ($Architecture -eq "arm64") {
    Write-Host "Staging ARM64 libpq runtime DLLs..." -ForegroundColor Cyan
    $LibpqStage = Join-Path $CurrentDir "installer\windows\libpq-arm64"
    $needed = @("libpq.dll","libcrypto-3-arm64.dll","libssl-3-arm64.dll","z.dll","lz4.dll","legacy.dll")
    $missing = @($needed | Where-Object { -not (Test-Path (Join-Path $LibpqStage $_)) })
    if ($missing.Count -gt 0) {
        $vcpkgBin = Join-Path $env:USERPROFILE "vcpkg\installed\arm64-windows\bin"
        if (Test-Path (Join-Path $vcpkgBin "libpq.dll")) {
            New-Item -ItemType Directory -Path $LibpqStage -Force | Out-Null
            foreach ($d in $needed) {
                $src = Join-Path $vcpkgBin $d
                if (Test-Path $src) { Copy-Item $src -Destination $LibpqStage -Force }
            }
            Write-Host "[OK] libpq staged from vcpkg: $vcpkgBin" -ForegroundColor Green
        } else {
            Write-Host "ERROR: ARM64 libpq DLLs not found for the MSI." -ForegroundColor Red
            Write-Host "  Provide them at $LibpqStage, or build with: vcpkg install libpq:arm64-windows" -ForegroundColor Yellow
            exit 1
        }
    } else {
        Write-Host "[OK] libpq DLLs already staged at $LibpqStage" -ForegroundColor Green
    }
    Write-Host ""
}

# ARM64: bundle prebuilt wheels so the target installs offline (no build toolchain).
if ($Architecture -eq "arm64") {
    Write-Host "Preparing ARM64 wheel set for offline install..." -ForegroundColor Cyan
    $WheelsDir = Join-Path $CurrentDir "installer\windows\wheels-arm64"
    if (-not (Test-Path $WheelsDir) -or @(Get-ChildItem "$WheelsDir\*.whl" -ErrorAction SilentlyContinue).Count -eq 0) {
        Write-Host "  No prebuilt wheels found - building from requirements-prod.txt (arm64 toolchain)..." -ForegroundColor Yellow
        $venvPy = Join-Path $CurrentDir ".venv\Scripts\python.exe"
        if (-not (Test-Path $venvPy)) {
            Write-Host "ERROR: arm64 .venv not found; run 'make install-dev' first." -ForegroundColor Red
            exit 1
        }
        New-Item -ItemType Directory -Path $WheelsDir -Force | Out-Null
        $vcpkgRoot = Join-Path $env:USERPROFILE "vcpkg"
        # cryptography has no win_arm64 wheel for the CVE-patched pin, so it is built
        # from source. Link it against a STATIC OpenSSL + static CRT so its _rust
        # extension carries no external OpenSSL/vcruntime deps — a dynamically-linked
        # build resolves those flakily at runtime on end-user machines ("procedure
        # could not be found"). Mirrors the Makefile's WIN_ARM64_ENV.
        if (-not (Test-Path "$vcpkgRoot\installed\arm64-windows-static\lib\libcrypto.lib")) {
            Write-Host "  Building static OpenSSL for the cryptography wheel (a few minutes)..." -ForegroundColor Yellow
            & "$vcpkgRoot\vcpkg.exe" install openssl:arm64-windows-static
            if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: static OpenSSL build failed." -ForegroundColor Red; exit 1 }
        }
        $env:PATH = "$env:USERPROFILE\.cargo\bin;$vcpkgRoot\installed\arm64-windows\bin;$env:PATH"
        $env:OPENSSL_DIR = "$vcpkgRoot\installed\arm64-windows-static"
        $env:OPENSSL_STATIC = "1"; $env:OPENSSL_NO_VENDOR = "1"
        $env:RUSTFLAGS = "-C target-feature=+crt-static"
        # Drop any cached dynamic cryptography wheel so the static one is (re)built.
        # (SilentlyContinue + no 2> redirect: under -ErrorActionPreference Stop, PS 5.1
        #  would otherwise wrap pip's "no matching packages" stderr into a fatal error.)
        $ErrorActionPreference = 'SilentlyContinue'
        & $venvPy -m pip cache remove cryptography | Out-Null
        $ErrorActionPreference = 'Stop'
        # grpcio (opentelemetry-exporter-otlp dep) has no win_arm64 wheel either, and its
        # deep upb-gen tree overflows MAX_PATH at link time under pip's own deep temp
        # layout (LNK1181) -- so `pip wheel grpcio` / `pip wheel -r ...` both fail. Build it
        # FIRST via the short-dir builder, then let the -r step reuse that wheel through
        # --find-links instead of rebuilding it from the deep tree.
        & (Join-Path $PSScriptRoot "..\..\scripts\build-grpcio-wheel-win-arm64.ps1") -Python $venvPy -OutputDir $WheelsDir
        if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: grpcio wheel build failed." -ForegroundColor Red; exit 1 }
        & $venvPy -m pip wheel -r (Join-Path $CurrentDir "requirements-prod.txt") --find-links $WheelsDir -w $WheelsDir
        if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: ARM64 wheel build failed." -ForegroundColor Red; exit 1 }
    }
    # The ARM64 wheel set is cross-built on separate hardware and cannot be
    # rebuilt here, so it is the one place the interpreter and the wheels can
    # drift apart.  Fail the BUILD rather than shipping an MSI whose offline
    # install cannot resolve a single compiled package.
    # Two kinds of compiled wheel, and conflating them is wrong:
    #   -cp313-cp313-   version LOCKED: usable only on 3.13
    #   -cp39-abi3-     stable ABI: a MINIMUM ("3.9 or newer"), e.g. cryptography
    # Reading every "-cp3NN-" as a lock reports a healthy set as targeting
    # "3.9, 3.13" and fails a build that should pass.
    $pyMinor = ([version]$PythonVersion).Minor
    $wheelNames = @(Get-ChildItem "$WheelsDir\*.whl" -ErrorAction SilentlyContinue | ForEach-Object { $_.Name })
    $locked = @($wheelNames | ForEach-Object { if ($_ -match '-cp3(\d+)-cp3\d+[a-z]*-') { [int]$Matches[1] } } | Sort-Object -Unique)
    $abi3Min = @($wheelNames | ForEach-Object { if ($_ -match '-cp3(\d+)-abi3-') { [int]$Matches[1] } } | Sort-Object -Unique)

    if ($locked.Count -eq 0) {
        Write-Host "ERROR: no version-locked (cpXY-cpXY) wheels in $WheelsDir - that is not the compiled ARM64 set." -ForegroundColor Red
        exit 1
    }
    if ($locked.Count -gt 1) {
        Write-Host "ERROR: ARM64 wheels are locked to MULTIPLE Python versions (3.$($locked -join ', 3.')) - the set is not internally consistent." -ForegroundColor Red
        exit 1
    }
    if ($locked[0] -ne $pyMinor) {
        Write-Host "ERROR: ARM64 wheels target Python 3.$($locked[0]) but the bundled runtime is $PythonVersion." -ForegroundColor Red
        Write-Host "  The offline install would resolve nothing.  Either set `$PythonVersion to a 3.$($locked[0]).x" -ForegroundColor Red
        Write-Host "  release, or rebuild the wheel set against $PythonVersion and re-run" -ForegroundColor Red
        Write-Host "  installer\windows\package-arm64-build-deps.ps1." -ForegroundColor Red
        exit 1
    }
    $floor = if ($abi3Min.Count) { ($abi3Min | Measure-Object -Maximum).Maximum } else { 0 }
    if ($pyMinor -lt $floor) {
        Write-Host "ERROR: stable-ABI wheels require Python 3.$floor or newer, but the bundled runtime is $PythonVersion." -ForegroundColor Red
        exit 1
    }
    Write-Host "  ARM64 wheels match the bundled runtime (locked cp3$pyMinor, abi3 floor 3.$floor)" -ForegroundColor Gray

    $WheelsZip = Join-Path $CurrentDir "installer\windows\wheels.zip"
    if (Test-Path $WheelsZip) { Remove-Item $WheelsZip -Force }
    $ProgressPreference = 'SilentlyContinue'
    Compress-Archive -Path "$WheelsDir\*" -DestinationPath $WheelsZip -Force
    $ProgressPreference = 'Continue'
    Write-Host "[OK] Bundled $(@(Get-ChildItem "$WheelsDir\*.whl").Count) ARM64 wheels into wheels.zip" -ForegroundColor Green
    Write-Host ""
}

# x64: bundle wheels too, so BOTH arches install fully offline.  x64 previously
# pip-installed from PyPI at install time, which needed network on the target and
# silently resolved against whatever system Python was found.  Every dependency
# has a win_amd64 wheel on PyPI, so unlike ARM64 there is no cross-build problem:
# fetch them with the BUNDLED interpreter, which makes the ABI match structural
# rather than something to verify after the fact.
if ($Architecture -eq "x64") {
    Write-Host "Bundling x64 wheels (offline install)..." -ForegroundColor Cyan
    $WheelsDir = Join-Path $CurrentDir "installer\windows\wheels-x64"
    if (Test-Path $WheelsDir) { Remove-Item -Recurse -Force $WheelsDir }
    New-Item -ItemType Directory -Path $WheelsDir -Force | Out-Null

    $bundledPy = Join-Path $pyRoot "python.exe"
    & $bundledPy -m pip download -r (Join-Path $CurrentDir "requirements-prod.txt") `
        --only-binary=:all: -d $WheelsDir --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: x64 wheel download failed." -ForegroundColor Red
        Write-Host "  Every dependency must publish a win_amd64 wheel for Python $PythonVersion." -ForegroundColor Red
        exit 1
    }

    $WheelsZip = Join-Path $CurrentDir "installer\windows\wheels.zip"
    if (Test-Path $WheelsZip) { Remove-Item $WheelsZip -Force }
    $ProgressPreference = 'SilentlyContinue'
    Compress-Archive -Path "$WheelsDir\*" -DestinationPath $WheelsZip -Force
    $ProgressPreference = 'Continue'
    Write-Host "[OK] Bundled $(@(Get-ChildItem "$WheelsDir\*.whl").Count) x64 wheels into wheels.zip" -ForegroundColor Green
    Write-Host ""
}

# Build MSI package
Write-Host "Building MSI package..." -ForegroundColor Cyan
Push-Location (Join-Path $CurrentDir "installer\windows")
try {
    $wixArgs = @(
        "build"
        "-o"
        $OutputMsi
        "sysmanage.wxs"
        "-arch"
        $Architecture
        "-d"
        "VERSION=$VERSION"
    )

    & wix @wixArgs

    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "ERROR: Build failed" -ForegroundColor Red
        exit 1
    }

    Write-Host ""
    Write-Host "[OK] Package built successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Package: $OutputMsi" -ForegroundColor Cyan
    Write-Host ""
    Get-Item $OutputMsi | Format-Table Name, Length, LastWriteTime -AutoSize
    Write-Host ""

    # Generate SHA256 checksum
    Write-Host "Generating SHA256 checksum..." -ForegroundColor Cyan
    $checksumFile = "$OutputMsi.sha256"
    $hash = (Get-FileHash -Path $OutputMsi -Algorithm SHA256).Hash.ToLower()
    $msiFileName = Split-Path -Leaf $OutputMsi
    "$hash  $msiFileName" | Out-File -FilePath $checksumFile -Encoding ASCII -NoNewline
    Write-Host "[OK] Checksum saved to: $checksumFile" -ForegroundColor Green
    Write-Host "  SHA256: $hash" -ForegroundColor Gray
    Write-Host ""

    # Check if package is signed
    $signature = Get-AuthenticodeSignature $OutputMsi
    if ($signature.Status -eq "NotSigned") {
        Write-Host "[WARNING] MSI package is NOT SIGNED" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "To sign the MSI (removes 'Unknown Publisher' warning):" -ForegroundColor Cyan
        Write-Host "  1. Obtain a code signing certificate" -ForegroundColor Gray
        Write-Host "  2. Install it in your certificate store" -ForegroundColor Gray
        Write-Host "  3. Run: signtool sign /a /t http://timestamp.digicert.com `"$OutputMsi`"" -ForegroundColor Gray
        Write-Host ""
    } else {
        Write-Host "[OK] Package is signed by: $($signature.SignerCertificate.Subject)" -ForegroundColor Green
        Write-Host ""
    }

    Write-Host "Install with:" -ForegroundColor Yellow
    Write-Host "  msiexec /i `"$OutputMsi`""
    Write-Host ""
} finally {
    Pop-Location
}
