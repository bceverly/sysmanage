# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.
#
# Verify what an MSI actually CONTAINS, without installing it.
#
#     powershell -ExecutionPolicy Bypass -File installer\windows\test-msi-contents.ps1 `
#         -Msi C:\path\to\sysmanage-3.5.1.16-x64.msi
#
# WHY THIS EXISTS
#   "CI built the MSI with no errors" proves it COMPILED.  It does not prove the
#   new components are in it, that their payload is the current generated file,
#   or that the packaged install.ps1 is the version that invokes nginx at all.
#   A component can compile perfectly and be absent from the installed tree --
#   e.g. if it is not referenced by any Feature.
#
#   This uses an ADMINISTRATIVE install (msiexec /a), which unpacks the file
#   tree WITHOUT running custom actions, creating services, or writing to
#   Program Files.  It is safe to run on a working machine and needs no
#   cleanup beyond deleting a temp directory.
#
# Exit 0 = the MSI contains what it should.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Msi,
    [string]$ExtractDir = "$env:TEMP\sysmanage-msi-extract",
    [string]$LogFile = "C:\sysmanage-msi-test.log"
)

$ErrorActionPreference = "Continue"
$script:Results = @()
$script:Failed = 0

try { Stop-Transcript | Out-Null } catch { }
try { Start-Transcript -Path $LogFile -Force | Out-Null; $script:Transcribing = $true }
catch { $script:Transcribing = $false }

function Step {
    param([string]$Name, [scriptblock]$Body)
    Write-Host ""
    Write-Host "--- $Name" -ForegroundColor Cyan
    try {
        $d = & $Body
        if ($d -is [array]) { $d = ($d -join "; ") }
        $script:Results += [pscustomobject]@{ Status = "PASS"; Step = $Name; Detail = "$d" }
        Write-Host "    PASS  $d" -ForegroundColor Green
    } catch {
        $script:Failed++
        $script:Results += [pscustomobject]@{ Status = "FAIL"; Step = $Name; Detail = "$_" }
        Write-Host "    FAIL  $_" -ForegroundColor Red
    }
}

try {

Write-Host "=== SysManage MSI content verification ===" -ForegroundColor White
Write-Host "MSI      : $Msi"
Write-Host "LOG FILE : $LogFile   <-- scp this back" -ForegroundColor White

$ScriptDir = $PSScriptRoot

Step "MSI exists" {
    if (-not (Test-Path $Msi)) { throw "not found: $Msi" }
    "{0} MB" -f [math]::Round((Get-Item $Msi).Length / 1MB, 1)
}

Step "Administrative extract (no install, no services, no custom actions)" {
    if (Test-Path $ExtractDir) { Remove-Item -Recurse -Force $ExtractDir }
    New-Item -ItemType Directory -Path $ExtractDir -Force | Out-Null
    $log = "$env:TEMP\msi-admin-extract.log"
    # /a = administrative install: unpack only.  /qn = no UI.
    $p = Start-Process msiexec.exe -Wait -PassThru -ArgumentList @(
        "/a", "`"$Msi`"", "/qn", "TARGETDIR=`"$ExtractDir`"", "/l*v", "`"$log`""
    )
    if ($p.ExitCode -ne 0) {
        $tail = if (Test-Path $log) { (Get-Content $log -Tail 15) -join "`n        " } else { "(no log)" }
        throw "msiexec /a exited $($p.ExitCode)`n        $tail"
    }
    $n = @(Get-ChildItem $ExtractDir -Recurse -File).Count
    "$n file(s) extracted"
}

# The whole point: are the NEW components actually in the package?
$InstallRoot = $null
Step "Locate the installed program directory inside the extract" {
    $cand = Get-ChildItem $ExtractDir -Recurse -Directory -Filter "SysManage Server" -EA SilentlyContinue |
            Select-Object -First 1
    if (-not $cand) {
        # Fall back to wherever install.ps1 landed.
        $f = Get-ChildItem $ExtractDir -Recurse -Filter "install.ps1" -EA SilentlyContinue | Select-Object -First 1
        if (-not $f) { throw "cannot find the program directory (no 'SysManage Server' dir, no install.ps1)" }
        $cand = $f.Directory
    }
    $script:InstallRoot = $cand.FullName
    $script:InstallRoot
}

Step "install-nginx.ps1 is IN the MSI" {
    $p = Join-Path $script:InstallRoot "install-nginx.ps1"
    if (-not (Test-Path $p)) {
        throw ("missing from the installed tree. The component compiled but is " +
               "not reaching the install - check it is inside a ComponentGroup " +
               "that the Feature references.")
    }
    "{0:N1} KB" -f ((Get-Item $p).Length / 1KB)
}

Step "sysmanage-nginx.conf is IN the MSI" {
    $p = Join-Path $script:InstallRoot "sysmanage-nginx.conf"
    if (-not (Test-Path $p)) { throw "missing from the installed tree" }
    "{0:N1} KB" -f ((Get-Item $p).Length / 1KB)
}

Step "Packaged config is byte-identical to the generated one" {
    # Guards against a stale copy being baked in: the config is GENERATED from
    # a shared template, and a packaged copy that has drifted would serve the
    # wrong document root without any gate noticing.
    $packaged = Join-Path $script:InstallRoot "sysmanage-nginx.conf"
    $source = Join-Path $ScriptDir "sysmanage-nginx.conf"
    if (-not (Test-Path $source)) { throw "no reference copy at $source (run this from a checkout)" }
    # Compare CONTENT, not line endings.  git checks the repo out with CRLF on
    # the Windows build agent, so a byte hash differs on every release for a
    # reason that does not matter to nginx -- a gate that cries wolf every time
    # gets ignored, which is worse than not having it.
    $norm = { param($f) ((Get-Content $f -Raw) -replace "`r`n", "`n") }
    $a = [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash(
            [Text.Encoding]::UTF8.GetBytes((& $norm $packaged)))).Replace("-","")
    $b = [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash(
            [Text.Encoding]::UTF8.GetBytes((& $norm $source)))).Replace("-","")
    if ($a -ne $b) {
        throw ("packaged config DIFFERS from installer\windows\sysmanage-nginx.conf`n" +
               "        packaged $($a.Substring(0,16))...`n" +
               "        source   $($b.Substring(0,16))...`n" +
               "        The MSI was built from a different revision, or the config " +
               "was regenerated after the build.")
    }
    "sha256 matches ($($a.Substring(0,16))...)"
}

Step "Packaged install.ps1 actually invokes the nginx setup" {
    # A file being present is not the same as it being wired in.  If the MSI
    # carries an older install.ps1, nginx never runs and the console is unserved
    # exactly as before -- with every file sitting there looking correct.
    $p = Join-Path $script:InstallRoot "install.ps1"
    if (-not (Test-Path $p)) { throw "install.ps1 missing from the installed tree" }
    $text = Get-Content $p -Raw
    if ($text -notmatch "install-nginx\.ps1") {
        throw "packaged install.ps1 does NOT reference install-nginx.ps1 - the MSI predates the nginx work"
    }
    if ($text -notmatch "https://localhost/") {
        throw "packaged install.ps1 still points users at the old URL - it predates the message fix"
    }
    "references install-nginx.ps1 and the corrected https://localhost/ message"
}

Step "nssm.exe is packaged (nginx runs under it)" {
    $p = Get-ChildItem $script:InstallRoot -Recurse -Filter "nssm.exe" -EA SilentlyContinue | Select-Object -First 1
    if (-not $p) { throw "nssm.exe not found - the nginx service cannot be registered" }
    "{0:N1} KB at {1}" -f ($p.Length / 1KB), $p.FullName.Replace($ExtractDir, "")
}

Step "Bundled Python runtime is packaged" {
    # Without this the install falls back to hunting for a system Python, which
    # is what shipped an install whose offline wheels no interpreter could satisfy.
    $z = Get-ChildItem $script:InstallRoot -Recurse -Filter "python.zip" -EA SilentlyContinue | Select-Object -First 1
    if (-not $z) { throw "python.zip missing - the MSI still depends on a system Python" }
    "{0:N1} MB" -f ($z.Length / 1MB)
}

Step "Offline wheel set is packaged" {
    $z = Get-ChildItem $script:InstallRoot -Recurse -Filter "wheels.zip" -EA SilentlyContinue | Select-Object -First 1
    if (-not $z) { throw "wheels.zip missing - the install would need network to fetch dependencies" }
    "{0:N1} MB" -f ($z.Length / 1MB)
}

Step "Frontend payload present (nginx has something to serve)" {
    $z = Get-ChildItem $script:InstallRoot -Recurse -Filter "frontend.zip" -EA SilentlyContinue | Select-Object -First 1
    if (-not $z) { throw "frontend.zip missing - nginx would serve an empty document root" }
    "{0:N1} MB" -f ($z.Length / 1MB)
}

} finally {
    if (Test-Path $ExtractDir) {
        Remove-Item -Recurse -Force $ExtractDir -EA SilentlyContinue
        Write-Host ""
        Write-Host "--- Cleanup: removed $ExtractDir" -ForegroundColor Cyan
    }
    Write-Host ""
    Write-Host "=== SUMMARY ===" -ForegroundColor White
    $script:Results | Format-Table -AutoSize Status, Step, Detail | Out-String | Write-Host
    if ($script:Failed -eq 0) {
        Write-Host "MSI CONTENTS VERIFIED - the nginx components are packaged and wired in." -ForegroundColor Green
    } else {
        Write-Host "$($script:Failed) CHECK(S) FAILED." -ForegroundColor Red
    }
    Write-Host "Full log: $LogFile"
    if ($script:Transcribing) { try { Stop-Transcript | Out-Null } catch { } }
}

if ($script:Failed -eq 0) { exit 0 } else { exit 1 }
