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
    [string]$Version = "3.5.1.16",
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

try {

Write-Host "=== SysManage MSI install + verify ===" -ForegroundColor White
Write-Host "LOG FILE : $LogFile   <-- scp this back" -ForegroundColor White

# ---------------------------------------------------------------- uninstall --
if ($Uninstall) {
    Write-Host ""
    Write-Host "--- Uninstall mode" -ForegroundColor Cyan
    $p = Get-CimInstance Win32_Product -Filter "Name LIKE '%SysManage%'" -EA SilentlyContinue
    if ($p) {
        foreach ($prod in $p) {
            Write-Host "    removing $($prod.Name) $($prod.Version)"
            Start-Process msiexec.exe -Wait -ArgumentList @("/x", $prod.IdentifyingNumber, "/qn",
                "/l*v", "C:\sysmanage-msi-uninstall.log")
        }
    } else {
        Write-Host "    no SysManage product registered"
    }
    foreach ($svc in @("SysManageServer", "SysManageNginx", "SysManageOpenBAO")) {
        $s = Get-Service -Name $svc -EA SilentlyContinue
        if ($s) { Write-Host "    LEFTOVER SERVICE: $svc ($($s.Status))" -ForegroundColor Yellow }
    }
    if (Test-Path $InstallRoot) { Write-Host "    LEFTOVER DIR: $InstallRoot" -ForegroundColor Yellow }
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

Step "No conflicting install already present" {
    $existing = Get-Service -Name "SysManageNginx" -EA SilentlyContinue
    if ($existing) {
        Note "SysManageNginx already exists ($($existing.Status)) - this run will upgrade over it"
    }
    # A leftover certificate would mask the 'correctly refuses without a cert'
    # check below, so say so rather than silently producing a misleading pass.
    if (Test-Path "$DataRoot\tls\server.crt") {
        Note "a TLS certificate is already present - nginx -t will PASS rather than correctly refuse"
    }
    "checked"
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

Step "Installer log shows the nginx step ran" {
    $logs = Get-ChildItem "$DataRoot\logs" -Filter "*install*.log" -EA SilentlyContinue |
            Sort-Object LastWriteTime -Descending
    if (-not $logs) { throw "no installer log under $DataRoot\logs" }
    $text = Get-Content $logs[0].FullName -Raw
    if ($text -notmatch "Setting up nginx") {
        throw "installer log has no 'Setting up nginx' line - the nginx custom action did not run"
    }
    if ($text -match "ERROR: nginx setup failed") {
        throw "installer log reports 'nginx setup failed' - see $($logs[0].FullName)"
    }
    if ($text -notmatch "nginx configured") {
        throw "nginx step started but never reported 'nginx configured' - see $($logs[0].FullName)"
    }
    "nginx configured (per $($logs[0].Name))"
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
    $script:Results | Format-Table -AutoSize Status, Step, Detail | Out-String | Write-Host
    if ($script:Failed -eq 0) {
        Write-Host "MSI INSTALL VERIFIED." -ForegroundColor Green
        Write-Host ""
        Write-Host "The install is LIVE on this machine.  To remove it:" -ForegroundColor White
        Write-Host "  powershell -ExecutionPolicy Bypass -File installer\windows\test-msi-install.ps1 -Uninstall"
    } else {
        Write-Host "$($script:Failed) CHECK(S) FAILED." -ForegroundColor Red
        Write-Host "  MSI verbose log : C:\sysmanage-msi-install-verbose.log"
        Write-Host "  installer log   : $DataRoot\logs\"
    }
    Write-Host ""
    Write-Host "Full log: $LogFile"
    if ($script:Transcribing) { try { Stop-Transcript | Out-Null } catch { } }
}

if ($script:Failed -eq 0) { exit 0 } else { exit 1 }
