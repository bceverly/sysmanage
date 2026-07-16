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
    $WheelsZip = Join-Path $CurrentDir "installer\windows\wheels.zip"
    if (Test-Path $WheelsZip) { Remove-Item $WheelsZip -Force }
    $ProgressPreference = 'SilentlyContinue'
    Compress-Archive -Path "$WheelsDir\*" -DestinationPath $WheelsZip -Force
    $ProgressPreference = 'Continue'
    Write-Host "[OK] Bundled $(@(Get-ChildItem "$WheelsDir\*.whl").Count) ARM64 wheels into wheels.zip" -ForegroundColor Green
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
