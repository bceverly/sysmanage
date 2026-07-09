#Requires -Version 5.1
<#
.SYNOPSIS
  Package the prebuilt ARM64 Windows build dependencies (libpq runtime DLLs +
  the cross-compiled Python wheel set) for upload to the 'windows-arm64-deps'
  GitHub release. The build-windows-msi-arm64 CI job downloads these so it can
  assemble the MSI in a couple of minutes instead of a 30-60 min cross-compile.

.DESCRIPTION
  Run this on your local ARM64 Windows box AFTER a successful:
      .\installer\windows\build-msi.ps1 -Architecture arm64
  which populates:
      installer\windows\libpq-arm64\    (the 6 libpq runtime DLLs)
      installer\windows\wheels-arm64\   (the arm64 wheel set)

  It writes, under installer\windows\arm64-deps-dist\ (git-ignored):
      libpq-arm64.zip                    flat: the 6 libpq runtime DLLs
      wheels-arm64.zip                   flat: *.whl
      wheels-arm64.requirements.sha256   hash of the requirements-prod.txt these
                                         wheels were built against (CI warns on drift)

  Then upload them to the release with the gh commands printed at the end
  (you run gh yourself). RE-RUN + RE-UPLOAD whenever an ARM64-affecting dependency
  in requirements-prod.txt changes, or the MSI will ship stale wheels.

.PARAMETER Tag
  The release tag to target. Default: windows-arm64-deps.
#>
param(
    [string]$Tag = 'windows-arm64-deps',
    [string]$Repo = 'bceverly/sysmanage'
)
$ErrorActionPreference = 'Stop'

$Win    = $PSScriptRoot                                   # installer\windows
$RepoRoot = (Resolve-Path (Join-Path $Win '..\..')).Path
$Libpq  = Join-Path $Win 'libpq-arm64'
$Wheels = Join-Path $Win 'wheels-arm64'
$Out    = Join-Path $Win 'arm64-deps-dist'
$Reqs   = Join-Path $RepoRoot 'requirements-prod.txt'

# Must match the $needed list in build-msi.ps1 (what WiX references at runtime).
$neededDlls = @("libpq.dll","libcrypto-3-arm64.dll","libssl-3-arm64.dll","z.dll","lz4.dll","legacy.dll")

# --- validate inputs -------------------------------------------------------
if (-not (Test-Path $Libpq)) {
    throw "Missing $Libpq - run 'build-msi.ps1 -Architecture arm64' on this box first."
}
$missing = @($neededDlls | Where-Object { -not (Test-Path (Join-Path $Libpq $_)) })
if ($missing.Count -gt 0) { throw "libpq-arm64 is missing DLL(s): $($missing -join ', ')" }

if (-not (Test-Path $Wheels)) {
    throw "Missing $Wheels - run 'build-msi.ps1 -Architecture arm64' on this box first."
}
$whlCount = @(Get-ChildItem "$Wheels\*.whl" -ErrorAction SilentlyContinue).Count
if ($whlCount -lt 1) { throw "No .whl files in $Wheels." }

# --- (re)create output dir -------------------------------------------------
if (Test-Path $Out) { Remove-Item $Out -Recurse -Force }
New-Item -ItemType Directory -Path $Out -Force | Out-Null

$ProgressPreference = 'SilentlyContinue'
# libpq: zip ONLY the 6 needed DLLs, flat.
Compress-Archive -Path ($neededDlls | ForEach-Object { Join-Path $Libpq $_ }) `
    -DestinationPath (Join-Path $Out 'libpq-arm64.zip') -Force
# wheels: zip all wheels, flat.
Compress-Archive -Path "$Wheels\*.whl" -DestinationPath (Join-Path $Out 'wheels-arm64.zip') -Force
$ProgressPreference = 'Continue'

# requirements hash so CI can warn if the wheels are stale vs the current pins.
if (Test-Path $Reqs) {
    (Get-FileHash $Reqs -Algorithm SHA256).Hash.ToLower() |
        Set-Content -NoNewline -Path (Join-Path $Out 'wheels-arm64.requirements.sha256')
}

Write-Host ""
Write-Host "[OK] Packaged ARM64 build deps ($whlCount wheels) into:" -ForegroundColor Green
Write-Host "     $Out"
Get-ChildItem $Out | ForEach-Object { Write-Host ("       " + $_.Name) }
Write-Host ""
Write-Host "Upload to the '$Tag' release (run these yourself - gh):" -ForegroundColor Cyan
Write-Host "  # first time only - create the release (a non-'v' tag, so it won't trigger build-and-release):"
Write-Host "  gh release create $Tag --repo $Repo --title `"Windows ARM64 build deps`" --notes `"Prebuilt libpq DLLs + arm64 wheels for the ARM64 MSI CI job.`""
Write-Host ""
Write-Host "  # every time - upload/replace the assets:"
Write-Host "  gh release upload $Tag --repo $Repo --clobber `"$Out\libpq-arm64.zip`" `"$Out\wheels-arm64.zip`" `"$Out\wheels-arm64.requirements.sha256`""
