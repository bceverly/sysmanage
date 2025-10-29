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

# Download NSSM if not already present
Write-Host "Checking for NSSM (Non-Sucking Service Manager)..." -ForegroundColor Cyan
$NssmDir = Join-Path $CurrentDir "installer\windows"
$NssmExe = Join-Path $NssmDir "nssm.exe"

if (-not (Test-Path $NssmExe)) {
    Write-Host "Downloading NSSM for bundling with installer..." -ForegroundColor Yellow

    $nssmArch = if ($Architecture -eq "x64" -or $Architecture -eq "arm64") { "win64" } else { "win32" }
    $nssmVersion = "2.24"
    $nssmUrl = "https://nssm.cc/release/nssm-$nssmVersion.zip"
    $nssmZip = Join-Path $env:TEMP "nssm-download.zip"
    $nssmExtract = Join-Path $env:TEMP "nssm-extract"

    try {
        Invoke-WebRequest -Uri $nssmUrl -OutFile $nssmZip -UseBasicParsing
        Write-Host "  Downloaded NSSM archive" -ForegroundColor Gray

        if (Test-Path $nssmExtract) {
            Remove-Item -Path $nssmExtract -Recurse -Force
        }
        $ProgressPreference = 'SilentlyContinue'
        Expand-Archive -Path $nssmZip -DestinationPath $nssmExtract -Force
        $ProgressPreference = 'Continue'

        $nssmSource = Join-Path $nssmExtract "nssm-$nssmVersion\$nssmArch\nssm.exe"
        if (Test-Path $nssmSource) {
            Copy-Item $nssmSource $NssmExe -Force
            Write-Host "[OK] NSSM downloaded and ready for bundling" -ForegroundColor Green
        } else {
            throw "NSSM executable not found in downloaded archive"
        }

        Remove-Item -Path $nssmZip -Force -ErrorAction SilentlyContinue
        Remove-Item -Path $nssmExtract -Recurse -Force -ErrorAction SilentlyContinue

    } catch {
        Write-Host "ERROR: Failed to download NSSM: $_" -ForegroundColor Red
        Write-Host "Please manually download from https://nssm.cc/download" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[OK] NSSM already present" -ForegroundColor Green
}
Write-Host ""

# Create ZIP files for packaging
Write-Host "Preparing source files for packaging..." -ForegroundColor Cyan

$BackendDir = Join-Path $CurrentDir "backend"
$FrontendDir = Join-Path $CurrentDir "frontend"
$AlembicDir = Join-Path $CurrentDir "alembic"

$BackendZip = Join-Path $CurrentDir "installer\windows\backend.zip"
$FrontendZip = Join-Path $CurrentDir "installer\windows\frontend.zip"
$AlembicZip = Join-Path $CurrentDir "installer\windows\alembic.zip"

# Remove old ZIPs
if (Test-Path $BackendZip) { Remove-Item -Path $BackendZip -Force }
if (Test-Path $FrontendZip) { Remove-Item -Path $FrontendZip -Force }
if (Test-Path $AlembicZip) { Remove-Item -Path $AlembicZip -Force }

# Create ZIPs
$ProgressPreference = 'SilentlyContinue'
Compress-Archive -Path "$BackendDir\*" -DestinationPath $BackendZip -Force
Compress-Archive -Path "$FrontendDir\*" -DestinationPath $FrontendZip -Force
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
