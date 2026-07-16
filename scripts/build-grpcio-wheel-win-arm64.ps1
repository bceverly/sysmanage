# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

<#
.SYNOPSIS
  Build a grpcio win_arm64 wheel from source via a SHORT build directory.

.DESCRIPTION
  grpcio ships no win_arm64 wheel, so on native ARM64 it must be compiled from its
  vendored gRPC-core. Its upb-gen source tree is extremely deep (~187-char relative
  object paths). pip's own build layout unpacks the sdist to
  <TMP>\pip-wheel-<8>\grpcio_<32-hex>\ (~64 chars) or <TMP>\pip-install-<8>\grpcio_<32-hex>\,
  and 64 + 187 exceeds the Windows MAX_PATH (260) limit at LINK time, so link.exe fails
  with "LNK1181: cannot open input file ...upb_minitable.obj". Neither
  `pip install --no-binary grpcio` nor `pip wheel grpcio` avoids this — both use that deep
  temp layout.

  The fix is to build in a MANUALLY extracted, short source dir (C:\g\grpcio-<ver>, ~21
  chars): 21 + 187 stays well under 260. This downloads the sdist, extracts it there, and
  builds the wheel IN PLACE with `python -m build --wheel` (which, unlike `pip wheel`, does
  not relocate the source into a deep temp dir), then copies the wheel to -OutputDir.

.PARAMETER Python     Interpreter to build with (the target venv's python.exe).
.PARAMETER OutputDir  Directory to copy the finished wheel into.
.PARAMETER Version    grpcio version to build.
#>
param(
    [Parameter(Mandatory = $true)][string]$Python,
    [Parameter(Mandatory = $true)][string]$OutputDir,
    [string]$Version = "1.81.1"
)
$ErrorActionPreference = "Stop"

# --- grpcio-from-source build knobs (long paths + short temp + parallel jobs) ---
# grpcio's deep upb-gen tree needs long paths (machine setting; needs elevation).
try {
    Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -Value 1 -Type DWord -Force
} catch {
    Write-Host "[grpcio] WARN: could not set LongPathsEnabled (run elevated)." -ForegroundColor Yellow
}
# Short temp so link.exe's response file and intermediate paths stay under MAX_PATH.
$bt = Join-Path $env:SystemDrive "bt"
if (-not (Test-Path $bt)) { New-Item -ItemType Directory -Path $bt -Force | Out-Null }
$env:TMP = $bt
$env:TEMP = $bt
$env:GRPC_PYTHON_BUILD_EXT_COMPILER_JOBS = "8"

# Ultra-short build root so the deep upb-gen object paths stay under MAX_PATH.
$short = Join-Path $env:SystemDrive "g"
if (Test-Path $short) { Remove-Item $short -Recurse -Force -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Path $short -Force | Out-Null

Write-Host "[grpcio] downloading sdist $Version..." -ForegroundColor Cyan
& $Python -m pip download "grpcio==$Version" --no-binary grpcio --no-deps -d $short
if ($LASTEXITCODE -ne 0) { throw "[grpcio] sdist download failed" }

$tar = Get-ChildItem "$short\grpcio-*.tar.gz" | Select-Object -First 1
if (-not $tar) { throw "[grpcio] sdist not found in $short" }
& tar -xzf $tar.FullName -C $short
if ($LASTEXITCODE -ne 0) { throw "[grpcio] sdist extraction failed" }
$src = Join-Path $short "grpcio-$Version"
if (-not (Test-Path $src)) { throw "[grpcio] extracted source not found at $src" }

# `python -m build --wheel` builds the wheel IN PLACE (creates .\dist) using an isolated
# env for grpcio's PEP 517 build deps; the source stays in the short dir (no deep temp).
& $Python -m pip install --quiet --upgrade build
if ($LASTEXITCODE -ne 0) { throw "[grpcio] could not install the 'build' frontend" }
Push-Location $src
try {
    Write-Host "[grpcio] building wheel from source (~20-30 min for gRPC core)..." -ForegroundColor Yellow
    & $Python -m build --wheel
    if ($LASTEXITCODE -ne 0) { throw "[grpcio] wheel build failed" }
} finally {
    Pop-Location
}

$whl = Get-ChildItem "$src\dist\grpcio-*.whl" | Select-Object -First 1
if (-not $whl) { throw "[grpcio] no wheel produced in $src\dist" }
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
Copy-Item $whl.FullName -Destination $OutputDir -Force
Write-Host "[grpcio] built $($whl.Name) -> $OutputDir" -ForegroundColor Green
