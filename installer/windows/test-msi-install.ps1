# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.
#
# Download, install and verify the SysManage MSI end to end.
#
#     powershell -ExecutionPolicy Bypass -File installer\windows\test-msi-install.ps1
#
# THIS PERFORMS A REAL INSTALL.  It writes to C:\Program Files\SysManage Server,
# creates the SysManageServer and SysManageNginx services, and installs nginx.
# That is the point -- it is the only way to prove the MSI places files where
# the installer expects and that the custom actions run in the right order.
# Use -Uninstall to remove it again.
#
# WHAT IT PROVES THAT NOTHING ELSE DOES
#   The standalone nginx test proved install-nginx.ps1 works.  Extracting the
#   MSI proved the right FILES are in the package.  Neither proves the MSI puts
#   them in the right DIRECTORY, or that install.ps1's custom action actually
#   invokes nginx during a real install.  This does.
#
# The backend service needs PostgreSQL and a configured sysmanage.yaml; without
# them SysManageServer will not start.  That is expected and is NOT counted as a
# failure here -- this script tests the INSTALLER, not a deployment.

[CmdletBinding()]
param(
    [string]$Version = "3.5.1.21",
    [string]$Arch = "arm64",                 # arm64 | x64
    [string]$Msi,                            # skip the download, use this file
    [switch]$Uninstall,                      # remove a previous install and exit
    [switch]$TestServing,                    # generate a cert and prove HTTPS
    [string]$LogFile = "C:\sysmanage-msi-install-test.log"
)

$ErrorActionPreference = "Continue"
$script:Results = @()
$script:Failed = 0
$InstallRoot = "C:\Program Files\SysManage Server"
$DataRoot = "C:\ProgramData\SysManage"

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
function Note { param([string]$m)
    $script:Results += [pscustomobject]@{ Status = "INFO"; Step = "note"; Detail = $m }
    Write-Host "    INFO  $m" -ForegroundColor DarkCyan
}

# Find installed SysManage products.
#
# Deliberately NOT Get-CimInstance Win32_Product: enumerating that class makes
# the Windows Installer RECONFIGURE every installed MSI on the machine as a side
# effect.  It routinely takes minutes and writes a pile of 1035 events.  The
# uninstall registry keys carry the same ProductCode with none of that.
function Get-SysManageProducts {
    $roots = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )
    Get-ItemProperty $roots -EA SilentlyContinue |
        Where-Object { $_.DisplayName -like '*SysManage*' } |
        ForEach-Object {
            [pscustomobject]@{
                Name        = $_.DisplayName
                Version     = $_.DisplayVersion
                ProductCode = $_.PSChildName
            }
        }
}

# Remove any prior install so a run always starts from a known state.  Returns a
# description of what it did.
function Remove-PriorInstall {
    $did = @()

    foreach ($prod in @(Get-SysManageProducts)) {
        Write-Host "      removing $($prod.Name) $($prod.Version) ($($prod.ProductCode))"
        $p = Start-Process msiexec.exe -Wait -PassThru -ArgumentList @(
            "/x", $prod.ProductCode, "/qn", "/l*v", "C:\sysmanage-msi-uninstall.log")
        $did += "uninstalled $($prod.Version) (msiexec exit $($p.ExitCode))"
    }

    # A failed install can leave services behind with no MSI record to remove
    # them -- exactly what the 3.5.1.16 attempt did, leaving SysManageServer
    # restart-looping on a venv with no dependencies.  Tear those down directly.
    foreach ($svc in @("SysManageServer", "SysManageNginx", "SysManageOpenBAO")) {
        $s = Get-Service -Name $svc -EA SilentlyContinue
        if (-not $s) { continue }
        Write-Host "      removing orphaned service $svc ($($s.Status))"
        $prev = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        try {
            if ($s.Status -ne 'Stopped') { Stop-Service -Name $svc -Force -EA SilentlyContinue }
            & sc.exe delete $svc 2>&1 | Out-Null
        } finally { $ErrorActionPreference = $prev }
        $did += "deleted orphaned service $svc"
    }

    # The program directory only ever holds installed payload, so clearing a
    # remnant is safe.  ProgramData is NOT touched: it holds the operator's
    # sysmanage.yaml, TLS material and logs.
    if (Test-Path $InstallRoot) {
        Start-Sleep -Seconds 2   # let service handles close after sc delete
        Remove-Item -Recurse -Force $InstallRoot -EA SilentlyContinue
        if (Test-Path $InstallRoot) { $did += "WARNING: $InstallRoot could not be fully removed" }
        else { $did += "removed leftover $InstallRoot" }
    }

    # install.ps1 APPENDS to install.log, and ProgramData is deliberately kept,
    # so a previous run's output would still be sitting there -- and the log
    # assertions below would then be reading the wrong install.  Rotate rather
    # than delete: the old log is the forensic record of why the last attempt
    # failed.
    $logDir = Join-Path $DataRoot "logs"
    if (Test-Path $logDir) {
        $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
        foreach ($name in @("install.log", "install-transcript.log", "create-service-transcript.log")) {
            $f = Join-Path $logDir $name
            if (Test-Path $f) {
                Move-Item $f "$f.$stamp.prev" -Force -EA SilentlyContinue
                $did += "rotated $name"
            }
        }
    }

    if ($did.Count -eq 0) { return "nothing to remove - machine was already clean" }
    return ($did -join "; ")
}

try {

Write-Host "=== SysManage MSI install + verify ===" -ForegroundColor White
Write-Host "LOG FILE : $LogFile   <-- scp this back" -ForegroundColor White

# ---------------------------------------------------------------- uninstall --
if ($Uninstall) {
    Write-Host ""
    Write-Host "--- Uninstall mode" -ForegroundColor Cyan
    Write-Host "    $(Remove-PriorInstall)"
    if (Test-Path $DataRoot) {
        Write-Host "    NOTE: $DataRoot kept (config, TLS material, logs)" -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "Uninstall log: C:\sysmanage-msi-uninstall.log"
    exit 0
}

# ------------------------------------------------------------------ preflight --
Step "Elevated (Administrator)" {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $pr = New-Object Security.Principal.WindowsPrincipal($id)
    if (-not $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "not elevated - msiexec cannot install. Re-run as Administrator."
    }
    "running as $($id.Name)"
}

Step "Remove any prior SysManage install" {
    # Always start clean rather than upgrading over whatever is there.  An
    # upgrade-in-place can leave a stale venv, a stale bundled Python or an
    # orphaned service from a previously FAILED install, and then the checks
    # below pass or fail for reasons that have nothing to do with the MSI under
    # test.  This is the whole point of the script, so it is a step, not a note.
    $summary = Remove-PriorInstall
    Write-Host "      $summary"

    $leftover = @(Get-SysManageProducts)
    if ($leftover.Count -gt 0) {
        throw ("a SysManage product is STILL registered after removal: " +
               ($leftover | ForEach-Object { "$($_.Name) $($_.Version)" }) -join ', ')
    }
    foreach ($svc in @("SysManageServer", "SysManageNginx")) {
        if (Get-Service -Name $svc -EA SilentlyContinue) {
            throw "service $svc survived removal - reboot may be required before re-testing"
        }
    }

    # A leftover certificate would mask the 'correctly refuses without a cert'
    # check below, so say so rather than silently producing a misleading pass.
    if (Test-Path "$DataRoot\tls\server.crt") {
        Note "a TLS certificate is already present in $DataRoot - nginx -t will PASS rather than correctly refuse"
    }
    $summary
}

# ------------------------------------------------------------------ download --
Step "Obtain the MSI" {
    if ($Msi) {
        if (-not (Test-Path $Msi)) { throw "not found: $Msi" }
        $script:MsiPath = (Resolve-Path $Msi).Path
    } else {
        $script:MsiPath = "C:\sysmanage-$Version-$Arch.msi"
        if (Test-Path $script:MsiPath) {
            Note "reusing already-downloaded $($script:MsiPath)"
        } else {
            $url = "https://github.com/bceverly/sysmanage/releases/download/v$Version/sysmanage-$Version-windows-$Arch.msi"
            Write-Host "      downloading $url"
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri $url -OutFile $script:MsiPath -UseBasicParsing
        }
    }
    "{0} ({1:N1} MB)" -f $script:MsiPath, ((Get-Item $script:MsiPath).Length / 1MB)
}

# ------------------------------------------------------------------- install --
Step "msiexec /i (this takes several minutes - venv + ~97 wheels)" {
    $msiLog = "C:\sysmanage-msi-install-verbose.log"
    if (Test-Path $msiLog) { Remove-Item $msiLog -Force }
    $p = Start-Process msiexec.exe -Wait -PassThru -ArgumentList @(
        "/i", "`"$($script:MsiPath)`"", "/qn", "/l*v", "`"$msiLog`""
    )
    if ($p.ExitCode -eq 3010) { Note "exit 3010 - install succeeded, reboot requested" }
    elseif ($p.ExitCode -ne 0) {
        $tail = if (Test-Path $msiLog) {
            (Select-String -Path $msiLog -Pattern "Error|error status|returned 3" |
             Select-Object -Last 8 | ForEach-Object { $_.Line.Trim() }) -join "`n        "
        } else { "(no verbose log)" }
        throw "msiexec exited $($p.ExitCode)`n        $tail`n        Full log: $msiLog"
    }
    "exit $($p.ExitCode); verbose log at $msiLog"
}

Step "Bundled Python runtime is installed and usable" {
    # The whole point of bundling: the install must not depend on, or be
    # influenced by, whatever Python the operator happens to have.
    $py = Join-Path $InstallRoot "python\python.exe"
    if (-not (Test-Path $py)) {
        throw "no bundled interpreter at $py - python.zip was not shipped or not extracted"
    }
    $v = (& $py --version 2>&1) -join " "
    if ($v -notmatch "Python 3\.(\d+)") { throw "bundled python did not report a version: $v" }
    "$v"
}

Step "Dependencies actually installed into the venv" {
    # This is the check that would have caught the 3.14-vs-cp312 failure on the
    # spot: the venv existed and the service was registered, but nothing was in
    # it.  Assert on the import that the service actually needs.
    $venvPy = Join-Path $InstallRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPy)) { throw "no venv at $venvPy" }
    $out = (& $venvPy -c "import uvicorn, fastapi, aiohttp; print(uvicorn.__version__)" 2>&1) -join " "
    if ($LASTEXITCODE -ne 0) {
        throw "venv cannot import its own dependencies - the offline wheel install failed`n        $out"
    }
    "uvicorn $out importable in the venv"
}

Step "Installer log shows the nginx step ran" {
    # install.ps1 writes TWO files here: install.log (its own Write-Log output) and
    # install-transcript.log (a Start-Transcript capture).  Both match "*install*.log",
    # and the transcript is normally the newer of the two because Stop-Transcript
    # writes its footer last -- so a newest-wins wildcard reads the wrong file.
    # Assert against install.log by name, and fall back to the transcript only if
    # install.ps1 died before creating it.
    $dir = "$DataRoot\logs"
    $primary = Join-Path $dir "install.log"
    $log = if (Test-Path $primary) { Get-Item $primary }
           else {
               Get-ChildItem $dir -Filter "*install*.log" -EA SilentlyContinue |
                   Sort-Object LastWriteTime -Descending | Select-Object -First 1
           }
    if (-not $log) {
        $seen = @(Get-ChildItem $dir -EA SilentlyContinue | ForEach-Object Name)
        throw ("no installer log under $dir" +
               "`n        directory contains: " + $(if ($seen) { $seen -join ", " } else { "(nothing)" }) +
               "`n        install.ps1 never got far enough to write one.")
    }

    $text = Get-Content $log.FullName -Raw
    # One shared failure reporter: whichever assertion trips, show the tail of the
    # log so the cause travels back in the SAME round trip instead of the next one.
    $bail = {
        param($why)
        $tail = (Get-Content $log.FullName -Tail 30) -join "`n        "
        throw ("$why`n        log: $($log.FullName) (last written $($log.LastWriteTime))" +
               "`n        --- last 30 lines ---`n        $tail")
    }

    if ($text -notmatch "Setting up nginx") {
        & $bail "installer log has no 'Setting up nginx' line - install.ps1 did not reach the nginx step"
    }
    if ($text -match "ERROR: nginx setup failed") {
        & $bail "installer log reports 'nginx setup failed'"
    }
    if ($text -notmatch "nginx configured") {
        & $bail "nginx step started but never reported 'nginx configured'"
    }
    "nginx configured (per $($log.Name))"
}

# ------------------------------------------------- files in the RIGHT PLACE --
# This is the gap nothing else covers: extracting the MSI proves the files are
# in the package, not that they are installed where install-nginx.ps1 and nginx
# look for them.
foreach ($rel in @("install-nginx.ps1",
                   "sysmanage-nginx.conf",
                   "nginx\nginx.exe",
                   "nginx\conf\sysmanage-nginx.conf",
                   "nssm.exe",
                   "frontend\index.html")) {
    Step "Installed: $rel" {
        $p = Join-Path $InstallRoot $rel
        if (-not (Test-Path $p)) { throw "missing $p" }
        "{0:N1} KB" -f ((Get-Item $p).Length / 1KB)
    }
}

Step "nginx.conf includes the SysManage server block (exactly once)" {
    $p = Join-Path $InstallRoot "nginx\conf\nginx.conf"
    $hits = @(Select-String -Path $p -Pattern "include\s+sysmanage-nginx\.conf;" -AllMatches)
    if ($hits.Count -lt 1) { throw "include missing from $p" }
    if ($hits.Count -gt 1) { throw "include present $($hits.Count) times - not idempotent" }
    "1 include directive"
}

Step "nginx.conf has no UTF-8 BOM" {
    # The BOM bug: nginx parses it as a directive and refuses to start.
    $p = Join-Path $InstallRoot "nginx\conf\nginx.conf"
    $b = [IO.File]::ReadAllBytes($p)
    if ($b.Length -ge 3 -and $b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF) {
        throw "nginx.conf starts with a UTF-8 BOM - nginx will fail with 'unknown directive'"
    }
    "clean (first bytes: {0:X2} {1:X2} {2:X2})" -f $b[0], $b[1], $b[2]
}

# ------------------------------------------------------------------ services --
Step "SysManageNginx service registered" {
    $s = Get-Service -Name "SysManageNginx" -EA SilentlyContinue
    if (-not $s) { throw "service not registered - nginx will not survive a reboot" }
    "$($s.Status), StartType=$($s.StartType)"
}

Step "SysManageServer service registered" {
    $s = Get-Service -Name "SysManageServer" -EA SilentlyContinue
    if (-not $s) { throw "backend service not registered" }
    if ($s.Status -ne "Running") {
        Note "not Running - expected without PostgreSQL and a configured sysmanage.yaml"
    }
    "$($s.Status), StartType=$($s.StartType)"
}

# --------------------------------------------------------------- nginx config --
$NginxExe = Join-Path $InstallRoot "nginx\nginx.exe"
$NginxDir = Join-Path $InstallRoot "nginx"

Step "nginx config test" {
    $prev = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { $out = & $NginxExe -p "$NginxDir" -t 2>&1 | Out-String }
    finally { $ErrorActionPreference = $prev }

    if ($out -match "test is successful") {
        return "passes (a certificate is present)"
    }
    if ($out -match "cannot load certificate|BIO_new_file|No such file") {
        return "correctly refuses: TLS certificate not installed yet (by design)"
    }
    throw ("nginx -t failed for an unexpected reason:`n        " +
           (($out.Trim() -split "`n" | Select-Object -First 5) -join "`n        "))
}

# ------------------------------------------------------------------- serving --
if ($TestServing) {
    Step "Generate a throwaway certificate and serve" {
        $ossl = (Get-Command openssl -EA SilentlyContinue).Source
        if (-not $ossl) {
            foreach ($c in @("$env:ProgramFiles\Git\usr\bin\openssl.exe",
                             "${env:ProgramFiles(x86)}\Git\usr\bin\openssl.exe")) {
                if (Test-Path $c) { $ossl = $c; break }
            }
        }
        if (-not $ossl) { throw "openssl not found (Git for Windows ships it) - cannot make a PEM cert" }

        New-Item -ItemType Directory -Path "$DataRoot\tls" -Force | Out-Null
        $crt = "$DataRoot\tls\server.crt"; $key = "$DataRoot\tls\server.key"
        $prev = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        try {
            & $ossl req -x509 -newkey rsa:2048 -nodes -days 2 `
                -subj "/CN=localhost" -keyout $key -out $crt 2>&1 | Out-Null
        } finally { $ErrorActionPreference = $prev }
        if (-not (Test-Path $crt)) { throw "openssl produced no certificate" }

        Restart-Service -Name "SysManageNginx" -Force -EA Stop
        Start-Sleep -Seconds 3
        $code = (& curl.exe -k -s -o NUL -w "%{http_code}" https://localhost/ 2>&1)
        switch ($code) {
            "200" { return "HTTPS 200 - the console is being served" }
            "500" { throw "HTTPS 500 - nginx up but the frontend is missing from the document root" }
            "000" { throw "could not connect - nginx may not have restarted" }
            default { return "HTTPS $code" }
        }
    }
}

} finally {
    Write-Host ""
    Write-Host "=== SUMMARY ===" -ForegroundColor White
    # Status/Step only.  Detail is printed unwrapped below: Format-Table -AutoSize
    # truncates long values with "...", which would swallow the diagnostic tail that
    # is the entire reason a failure is worth reporting.
    $script:Results | Format-Table -AutoSize Status, Step | Out-String | Write-Host

    if ($script:Failed -eq 0) {
        Write-Host "MSI INSTALL VERIFIED." -ForegroundColor Green
        Write-Host ""
        Write-Host "The install is LIVE on this machine.  To remove it:" -ForegroundColor White
        Write-Host "  powershell -ExecutionPolicy Bypass -File installer\windows\test-msi-install.ps1 -Uninstall"
    } else {
        Write-Host "--- FAILURE DETAIL (untruncated) ---" -ForegroundColor Red
        foreach ($r in $script:Results | Where-Object Status -eq "FAIL") {
            Write-Host ""
            Write-Host "FAIL: $($r.Step)" -ForegroundColor Red
            Write-Host "      $($r.Detail)"
        }
        Write-Host ""
        Write-Host "$($script:Failed) CHECK(S) FAILED." -ForegroundColor Red
    }
    Write-Host ""
    Write-Host "=== SEND THIS FILE BACK: $LogFile ===" -ForegroundColor White
    Write-Host "It contains the summary, the untruncated failure detail, and everything above."
    if ($script:Failed -ne 0) {
        Write-Host "Only if asked for more: C:\sysmanage-msi-install-verbose.log (raw msiexec), $DataRoot\logs\"
    }
    if ($script:Transcribing) { try { Stop-Transcript | Out-Null } catch { } }
}

if ($script:Failed -eq 0) { exit 0 } else { exit 1 }
