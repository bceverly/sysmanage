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
