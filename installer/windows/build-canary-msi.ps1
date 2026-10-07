# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.
#
# Build the sysmanage-canary MSI (Phase 22.9) with WiX:
#
#   .\installer\windows\build-canary-msi.ps1 -Architecture x64
#   .\installer\windows\build-canary-msi.ps1 -Architecture arm64
#
# Run from the repository root on a machine of the TARGET architecture: the
# bundled Python fetches the wheels for itself, so the ABI always matches.
# ARM64 also needs the libpq DLLs build-msi.ps1 stages in
# installer\windows\libpq-arm64 (run it first, as CI does).
#
# The Python pin is READ from build-msi.ps1 rather than repeated here, so the
# server and canary MSIs cannot drift onto different interpreters.

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("x64", "arm64")]
    [string]$Architecture = "x64"
)

$ErrorActionPreference = "Stop"

function Fail([string]$Message) {
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

Write-Host "=== Building sysmanage-canary .msi ($Architecture) ===" -ForegroundColor Cyan
if (-not (Get-Command wix -ErrorAction SilentlyContinue)) {
    Fail "WiX Toolset not found (dotnet tool install --global wix --version 6.0.1)"
}

$VERSION = ($env:VERSION -replace '^v', '')
if (-not $VERSION) {
    $tag = (git describe --tags --abbrev=0 2>$null | Out-String).Trim()
    if ($tag -match '^v?(\d+\.\d+\.\d+(\.\d+)?)') { $VERSION = $Matches[1] } else { $VERSION = "0.9.0" }
}
Write-Host "Version: $VERSION"

$Root = Get-Location
$WinDir = Join-Path $Root "installer\windows"
$OutputDir = Join-Path $Root "installer\dist"
$OutputMsi = Join-Path $OutputDir "sysmanage-canary-$VERSION-windows-$Architecture.msi"
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

if (-not (Test-Path (Join-Path $WinDir "nssm\nssm.exe"))) { Fail "installer\windows\nssm\nssm.exe is missing" }

# --- the bundled Python, pinned in build-msi.ps1 ---------------------------
$serverBuild = Get-Content (Join-Path $WinDir "build-msi.ps1") -Raw
if ($serverBuild -notmatch '\$PythonVersion\s*=\s*"([^"]+)"') { Fail "no `$PythonVersion in build-msi.ps1" }
$PythonVersion = $Matches[1]
if ($serverBuild -notmatch '\$PythonRelease\s*=\s*"([^"]+)"') { Fail "no `$PythonRelease in build-msi.ps1" }
$PythonRelease = $Matches[1]
if ($serverBuild -notmatch ('"' + $Architecture + '"\s*=\s*"([0-9a-fA-F]{64})"')) { Fail "no $Architecture hash in build-msi.ps1" }
$PythonHash = $Matches[1].ToLower()
$Triple = @{ "arm64" = "aarch64-pc-windows-msvc"; "x64" = "x86_64-pc-windows-msvc" }[$Architecture]

$asset = "cpython-$PythonVersion+$PythonRelease-$Triple-install_only.tar.gz"
$cache = Join-Path $WinDir ".python-cache"
New-Item -ItemType Directory -Path $cache -Force | Out-Null
$tarball = Join-Path $cache $asset
if (-not (Test-Path $tarball)) {
    Write-Host "Downloading $asset..."
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest -Uri "https://github.com/astral-sh/python-build-standalone/releases/download/$PythonRelease/$asset" `
        -OutFile $tarball -UseBasicParsing
    $ProgressPreference = 'Continue'
}
if ((Get-FileHash $tarball -Algorithm SHA256).Hash.ToLower() -ne $PythonHash) {
    Remove-Item $tarball -Force
    Fail "checksum mismatch for $asset"
}

$stage = Join-Path $cache "canary-extract-$Architecture"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Path $stage -Force | Out-Null
& tar -xzf $tarball -C $stage
if ($LASTEXITCODE -ne 0) { Fail "could not extract $asset" }
$pyRoot = Join-Path $stage "python"
$py = Join-Path $pyRoot "python.exe"
if (-not (Test-Path $py)) { Fail "python.exe not found in $pyRoot" }
Get-ChildItem $pyRoot -Recurse -Filter *.pdb | Remove-Item -Force

# --- the two wheels, fetched by that interpreter ---------------------------
# psycopg-binary carries libpq on x64; there is no win_arm64 build of it, so
# ARM64 takes pure-Python psycopg and the libpq DLLs.
$wheelDir = Join-Path $stage "wheels"
New-Item -ItemType Directory -Path $wheelDir -Force | Out-Null
$requirements = if ($Architecture -eq "x64") { @("pyyaml", "psycopg[binary]") } else { @("pyyaml", "psycopg") }
$ErrorActionPreference = "Continue"
& $py -m pip download --only-binary=:all: --disable-pip-version-check -d $wheelDir @requirements
$pipStatus = $LASTEXITCODE
$ErrorActionPreference = "Stop"
if ($pipStatus -ne 0) { Fail "pip could not fetch $($requirements -join ', ') for $Architecture" }

if ($Architecture -eq "arm64") {
    foreach ($dll in @("libpq.dll", "libcrypto-3-arm64.dll", "libssl-3-arm64.dll", "z.dll", "lz4.dll", "legacy.dll")) {
        if (-not (Test-Path (Join-Path $WinDir "libpq-arm64\$dll"))) {
            Fail "installer\windows\libpq-arm64\$dll is missing; run build-msi.ps1 -Architecture arm64 first"
        }
    }
}

# --- zip the payloads -------------------------------------------------------
$ProgressPreference = 'SilentlyContinue'
$zips = @{
    "canary-python.zip" = "$pyRoot\*"
    "canary-wheels.zip" = "$wheelDir\*.whl"
}
foreach ($name in $zips.Keys) {
    $zip = Join-Path $WinDir $name
    if (Test-Path $zip) { Remove-Item $zip -Force }
}
# The wheels first: they live inside the python stage, which is zipped next.
Compress-Archive -Path $zips["canary-wheels.zip"] -DestinationPath (Join-Path $WinDir "canary-wheels.zip")
Remove-Item -Recurse -Force $wheelDir
Compress-Archive -Path $zips["canary-python.zip"] -DestinationPath (Join-Path $WinDir "canary-python.zip")

$libStage = Join-Path $stage "lib"
New-Item -ItemType Directory -Path $libStage -Force | Out-Null
Copy-Item -Recurse (Join-Path $Root "canary\sysmanage_canary") $libStage
Get-ChildItem $libStage -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
$canaryZip = Join-Path $WinDir "canary.zip"
if (Test-Path $canaryZip) { Remove-Item $canaryZip -Force }
Compress-Archive -Path "$libStage\*" -DestinationPath $canaryZip
$ProgressPreference = 'Continue'

# --- build ------------------------------------------------------------------
# The installer UI (sysmanage-ui.wxs) needs two WiX extensions, pinned to the
# same 6.0.1 as the wix tool CI installs: WixToolset.UI.wixext (the dialogs)
# and WixToolset.Util.wixext (WixShellExec, which opens GETTING-STARTED.txt).
function Install-WixExtensions {
    # No 2> redirect: under "Stop", Windows PowerShell 5.1 turns redirected
    # native stderr into a terminating error.
    $have = (& wix extension list -g | Out-String)
    foreach ($ext in @("WixToolset.UI.wixext", "WixToolset.Util.wixext")) {
        if ($have -notmatch [regex]::Escape($ext)) {
            & wix extension add -g "$ext/6.0.1"
            if ($LASTEXITCODE -ne 0) { throw "could not add the WiX extension $ext" }
        }
    }
}
Install-WixExtensions
Push-Location $WinDir
try {
    & wix build -o $OutputMsi sysmanage-canary.wxs sysmanage-ui.wxs -arch $Architecture `
        -d "VERSION=$VERSION" -ext WixToolset.UI.wixext -ext WixToolset.Util.wixext
    if ($LASTEXITCODE -ne 0) { Fail "wix build failed" }
} finally {
    Pop-Location
}
$hash = (Get-FileHash -Path $OutputMsi -Algorithm SHA256).Hash.ToLower()
"$hash  $(Split-Path -Leaf $OutputMsi)" | Out-File -FilePath "$OutputMsi.sha256" -Encoding ASCII -NoNewline
Write-Host "[OK] $OutputMsi" -ForegroundColor Green
Write-Host "Install with: msiexec /i `"$OutputMsi`""
