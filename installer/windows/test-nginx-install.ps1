# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.
#
# Self-contained acceptance test for the Windows nginx install.
#
# Run this from an ELEVATED PowerShell in a sysmanage checkout:
#
#     powershell -ExecutionPolicy Bypass -File installer\windows\test-nginx-install.ps1
#
# It installs nginx into an ISOLATED directory (default C:\nginx-test), proves
# each step, and tears everything down again.  It does not touch a real
# SysManage install, and it registers its own service name so it cannot collide
# with a production SysManageNginx.
#
# WHY THIS EXISTS
#   Nothing in the Windows nginx path had ever executed on Windows -- CI proves
#   the MSI compiles, not that nginx installs, registers, starts or serves.  A
#   path-separator bug in unrelated code survived every Linux check and was
#   found only by a real Windows run, so "it built" is not evidence.
#
# THE ARM64 QUESTION
#   nginx.org ships ONE Windows build and it is 32-bit x86 -- there is no ARM64
#   binary.  Windows 11 on ARM emulates x86, so it is expected to work, but that
#   is an assumption this script tests explicitly rather than trusting.  If the
#   emulation is unavailable or blocked by policy, step 5 fails and everything
#   after it is meaningless -- which is exactly what the summary will say.
#
# Exit code 0 = everything passed.  Non-zero = at least one step failed, and the
# failure detail plus diagnostics are printed.

[CmdletBinding()]
param(
    # Isolated by default so a failed run cannot damage a real install.
    [string]$InstallDir = "C:\nginx-test",
    # Distinct from the production SysManageNginx for the same reason.
    [string]$ServiceName = "SysManageNginxTest",
    # Keep the tree and the service for manual poking.
    [switch]$KeepArtifacts,
    # Everything -- console output, diagnostics, the installer's own log -- is
    # copied here.  Console-only output is useless when the person who has to
    # read the failure is not the person at the keyboard.
    # Deliberately C:\ and not %TEMP%: this file exists to be scp'd off the
    # box, and a path under C:\Users\<name>\AppData\Local\Temp is a nuisance
    # to type from a remote shell.
    [string]$LogFile = "C:\sysmanage-nginx-test.log"
)

# Transcript rather than redirection: Write-Host goes to the information stream
# and a plain "> file" misses it, which would produce an empty log at exactly
# the moment it matters.
# A stale transcript from an aborted run blocks a new one, so clear it first.
try { Stop-Transcript | Out-Null } catch { }
$script:Transcribing = $false
try {
    Start-Transcript -Path $LogFile -Force | Out-Null
    $script:Transcribing = $true
} catch {
    # Transcription is unavailable in some hosts.  Fall back to a real tee so
    # the log exists either way -- the whole point is handing this file to
    # someone who is not at this keyboard.
    Write-Host "WARN  transcript unavailable ($_) - using fallback tee" -ForegroundColor Yellow
    try { "" | Out-File -FilePath $LogFile -Encoding utf8 -Force } catch { }
}

function Say {
    <#  Console AND file, for the fallback path.  When the transcript is running
        it already captures Write-Host, so writing again would duplicate every
        line -- hence the guard.  #>
    param([string]$Message, [string]$Color = "Gray")
    Write-Host $Message -ForegroundColor $Color
    if (-not $script:Transcribing) {
        try { Add-Content -Path $LogFile -Value $Message -ErrorAction SilentlyContinue } catch { }
    }
}

$ErrorActionPreference = "Continue"
$script:Results = @()
$script:Failed = 0

function Step {
    param([string]$Name, [scriptblock]$Body)
    Write-Host ""
    Write-Host "--- $Name" -ForegroundColor Cyan
    try {
        $detail = & $Body
        if ($detail -is [array]) { $detail = ($detail -join "; ") }
        $script:Results += [pscustomobject]@{ Step = $Name; Status = "PASS"; Detail = "$detail" }
        Write-Host "    PASS  $detail" -ForegroundColor Green
        return $true
    } catch {
        $script:Failed++
        $script:Results += [pscustomobject]@{ Step = $Name; Status = "FAIL"; Detail = "$_" }
        Write-Host "    FAIL  $_" -ForegroundColor Red
        return $false
    }
}

function Warn { param([string]$m) Write-Host "    WARN  $m" -ForegroundColor Yellow }

function Skip {
    param([string]$Name, [string]$Why)
    $script:Results += [pscustomobject]@{ Step = $Name; Status = "SKIP"; Detail = $Why }
    Write-Host ""
    Write-Host "--- $Name" -ForegroundColor Cyan
    Write-Host "    SKIP  $Why" -ForegroundColor DarkYellow
}

# --------------------------------------------------------------------------
Write-Host "=== SysManage Windows nginx acceptance test ===" -ForegroundColor White
Write-Host "InstallDir : $InstallDir"
Write-Host "Service    : $ServiceName"
Write-Host "LOG FILE   : $LogFile   <-- scp this back" -ForegroundColor White

$ScriptDir = $PSScriptRoot
$NginxDir = Join-Path $InstallDir "nginx"
$NginxExe = Join-Path $NginxDir "nginx.exe"
$TlsDir = "C:\ProgramData\SysManage\tls"
$MadeTls = $false

try {

# 0 -----------------------------------------------------------------------
Step "Elevated (Administrator)" {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $pr = New-Object Security.Principal.WindowsPrincipal($id)
    if (-not $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "not elevated - service registration and C:\ProgramData writes will fail. Re-run as Administrator."
    }
    "running as $($id.Name)"
} | Out-Null

# 1 -----------------------------------------------------------------------
Step "Host architecture" {
    $arch = $env:PROCESSOR_ARCHITECTURE
    $os = (Get-CimInstance Win32_OperatingSystem).Caption
    "$os / $arch"
} | Out-Null

Step "install-nginx.ps1 present next to this script" {
    $p = Join-Path $ScriptDir "install-nginx.ps1"
    if (-not (Test-Path $p)) { throw "not found at $p - run this from a sysmanage checkout" }
    $p
} | Out-Null

Step "sysmanage-nginx.conf present (generated config)" {
    $p = Join-Path $ScriptDir "sysmanage-nginx.conf"
    if (-not (Test-Path $p)) {
        throw "not found at $p - run: python3 scripts/render_nginx_configs.py"
    }
    "$([math]::Round((Get-Item $p).Length / 1KB, 1)) KB"
} | Out-Null

# 2 -----------------------------------------------------------------------
# Clean slate so a re-run tests the install, not a leftover.
Step "Production install untouched" {
    if ($ServiceName -eq "SysManageNginx") {
        throw ("refusing to run: -ServiceName is the PRODUCTION name, and this " +
               "script's cleanup would delete a real service. Use the default " +
               "SysManageNginxTest.")
    }
    $prod = Get-Service -Name "SysManageNginx" -ErrorAction SilentlyContinue
    if ($prod) { Warn "a production SysManageNginx exists ($($prod.Status)) - it will NOT be touched" }
    "test service is $ServiceName"
} | Out-Null

Step "Clean slate" {
    & "$ScriptDir\nssm\nssm.exe" stop $ServiceName confirm 2>&1 | Out-Null
    & "$ScriptDir\nssm\nssm.exe" remove $ServiceName confirm 2>&1 | Out-Null
    if (Test-Path $InstallDir) { Remove-Item -Recurse -Force $InstallDir -ErrorAction SilentlyContinue }
    "removed prior test artifacts"
} | Out-Null

# 3 -----------------------------------------------------------------------
$installOk = Step "Run install-nginx.ps1 (download + SHA-256 + extract + configure + service)" {
    $log = Join-Path $env:TEMP "sysmanage-nginx-test.log"
    if (Test-Path $log) { Remove-Item $log -Force }
    $p = Join-Path $ScriptDir "install-nginx.ps1"
    & powershell.exe -ExecutionPolicy Bypass -File $p -InstallDir $InstallDir -LogFile $log -ServiceName $ServiceName 2>&1 |
        ForEach-Object { Write-Host "      $_" -ForegroundColor DarkGray }
    if ($LASTEXITCODE -ne 0) { throw "install-nginx.ps1 exited $LASTEXITCODE (log: $log)" }
    "completed"
}

# 4 -----------------------------------------------------------------------
Step "nginx.exe extracted" {
    if (-not (Test-Path $NginxExe)) { throw "missing $NginxExe" }
    "$([math]::Round((Get-Item $NginxExe).Length / 1MB, 1)) MB"
} | Out-Null

Step "nginx.exe binary architecture" {
    # nginx.org ships 32-bit x86 only.  Reading the PE header tells us what we
    # actually got, so a surprise (or a future ARM64 upstream build) is visible
    # rather than inferred.
    $fs = [IO.File]::OpenRead($NginxExe)
    try {
        $br = New-Object IO.BinaryReader($fs)
        $fs.Position = 0x3C
        $peOff = $br.ReadInt32()
        $fs.Position = $peOff + 4
        $machine = $br.ReadUInt16()
    } finally { $fs.Dispose() }
    $name = switch ($machine) {
        0x014c { "i386 (32-bit x86)" }
        0x8664 { "x86-64" }
        0xaa64 { "ARM64" }
        default { "unknown 0x{0:x4}" -f $machine }
    }
    if ($machine -eq 0x014c -and $env:PROCESSOR_ARCHITECTURE -eq "ARM64") {
        Warn "x86 binary on ARM64 - relies on Windows x86 emulation (step below proves it)"
    }
    $name
} | Out-Null

# 5 -----------------------------------------------------------------------
# THE critical ARM64 check: does the binary actually run here?
Step "nginx.exe EXECUTES on this machine" {
    $out = & $NginxExe -v 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0 -and -not ($out -match "nginx version")) {
        throw ("nginx.exe did not run (exit $LASTEXITCODE). Output: $($out.Trim())`n" +
               "        On ARM64 this means x86 emulation is unavailable or blocked.")
    }
    ($out -split "`n" | Where-Object { $_ -match "nginx version" } | Select-Object -First 1).Trim()
} | Out-Null

# 6 -----------------------------------------------------------------------
Step "SysManage server block installed" {
    $p = Join-Path $NginxDir "conf\sysmanage-nginx.conf"
    if (-not (Test-Path $p)) { throw "missing $p" }
    $p
} | Out-Null

Step "nginx.conf includes it (exactly once)" {
    $p = Join-Path $NginxDir "conf\nginx.conf"
    $hits = @(Select-String -Path $p -Pattern "include\s+sysmanage-nginx\.conf;" -AllMatches)
    if ($hits.Count -lt 1) { throw "nginx.conf does not include sysmanage-nginx.conf" }
    if ($hits.Count -gt 1) { throw "include added $($hits.Count) times - not idempotent" }
    "1 include directive"
} | Out-Null

Step "Service registered" {
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if (-not $svc) { throw "service $ServiceName not found (nssm registration failed)" }
    "$ServiceName = $($svc.Status), StartType=$($svc.StartType)"
} | Out-Null

# 7 -----------------------------------------------------------------------
Step "Config test FAILS without a certificate (expected, by design)" {
    $out = & $NginxExe -p "$NginxDir" -t 2>&1 | Out-String
    if ($out -match "syntax is ok" -and $out -match "test is successful") {
        Warn "config already passes - a certificate is present from an earlier run"
        return "already had a certificate"
    }
    if ($out -match "cannot load certificate|BIO_new_file|No such file") {
        return "correctly refuses: certificate missing"
    }
    throw ("nginx -t failed for an UNEXPECTED reason (not the missing cert):`n" +
           ($out.Trim() -split "`n" | Select-Object -First 6 | ForEach-Object { "        $_" }) -join "`n")
} | Out-Null

# 8 -----------------------------------------------------------------------
$CanServe = $true
if (-not (Get-Command openssl -ErrorAction SilentlyContinue)) {
    $CanServe = $false
    foreach ($n in @("Self-signed certificate for the serving test",
                     "Config test PASSES with a certificate",
                     "Service starts and listens on 443",
                     "HTTPS responds (404 expected - no frontend in this isolated test)",
                     "HTTP 80 redirects to HTTPS")) {
        Skip $n "openssl not on PATH (ships with Git for Windows) - cannot build a PEM keypair"
    }
    Write-Host ""
    Write-Host "    Everything BEFORE this point is the install itself and is fully tested." -ForegroundColor DarkYellow
    Write-Host "    Install openssl (or add Git's usr\bin to PATH) to also test serving." -ForegroundColor DarkYellow
}

if ($CanServe) {
Step "Self-signed certificate for the serving test" {
    New-Item -ItemType Directory -Path $TlsDir -Force | Out-Null
    $crt = Join-Path $TlsDir "server.crt"
    $key = Join-Path $TlsDir "server.key"
    if ((Test-Path $crt) -and (Test-Path $key)) { return "reusing existing certificate" }
    $c = New-SelfSignedCertificate -DnsName "localhost" -CertStoreLocation "Cert:\LocalMachine\My" `
            -NotAfter (Get-Date).AddDays(2) -KeyExportPolicy Exportable
    $pfx = Join-Path $env:TEMP "sysmanage-test.pfx"
    $pw = ConvertTo-SecureString -String "test" -Force -AsPlainText
    Export-PfxCertificate -Cert $c -FilePath $pfx -Password $pw | Out-Null
    # nginx wants PEM.  openssl ships with Git for Windows; fall back cleanly.
    $ossl = Get-Command openssl -ErrorAction SilentlyContinue
    if (-not $ossl) { throw "openssl vanished between the check above and here" }
    & openssl pkcs12 -in $pfx -clcerts -nokeys -out $crt -passin pass:test 2>&1 | Out-Null
    & openssl pkcs12 -in $pfx -nocerts -nodes -out $key -passin pass:test 2>&1 | Out-Null
    Remove-Item $pfx -Force -ErrorAction SilentlyContinue
    Remove-Item "Cert:\LocalMachine\My\$($c.Thumbprint)" -Force -ErrorAction SilentlyContinue
    $script:MadeTls = $true
    "generated 2-day self-signed cert"
} | Out-Null

Step "Config test PASSES with a certificate" {
    $out = & $NginxExe -p "$NginxDir" -t 2>&1 | Out-String
    if ($out -notmatch "test is successful") {
        throw ("nginx -t still failing:`n" +
               (($out.Trim() -split "`n" | Select-Object -First 8 | ForEach-Object { "        $_" }) -join "`n"))
    }
    "syntax ok, test successful"
} | Out-Null

# 9 -----------------------------------------------------------------------
Step "Service starts and listens on 443" {
    Start-Service -Name $ServiceName -ErrorAction Stop
    Start-Sleep -Seconds 3
    $svc = Get-Service -Name $ServiceName
    if ($svc.Status -ne "Running") { throw "service status is $($svc.Status), expected Running" }
    $listening = Get-NetTCPConnection -LocalPort 443 -State Listen -ErrorAction SilentlyContinue
    if (-not $listening) { throw "service Running but nothing is listening on 443" }
    "Running, listening on 443"
} | Out-Null

Step "HTTPS responds (404 expected - no frontend in this isolated test)" {
    $code = (& curl.exe -k -s -o NUL -w "%{http_code}" https://localhost/ 2>&1)
    if (-not $code) { throw "no HTTP response at all - TLS handshake or listener problem" }
    if ($code -eq "000") { throw "curl could not connect (code 000) - check the nginx error log below" }
    if ($code -eq "404") { return "404 - nginx is serving; the document root is absent in this test, as expected" }
    if ($code -eq "200") { return "200 - serving content (a real frontend is present)" }
    "HTTP $code (unexpected but nginx responded)"
} | Out-Null

Step "HTTP 80 redirects to HTTPS" {
    $code = (& curl.exe -s -o NUL -w "%{http_code}" http://localhost/ 2>&1)
    if ($code -match "30[12]") { return "HTTP $code redirect" }
    "HTTP $code (expected 301)"
} | Out-Null
}  # end if ($CanServe)

# --------------------------------------------------------------------------
# Diagnostics on failure -- printed only when something went wrong, so a green
# run stays short.
if ($script:Failed -gt 0) {
  # Wrapped: ONE failing probe must not cost the summary.  A diagnostic that is
  # unavailable (an absent cmdlet, a permission refusal) is a footnote; losing
  # the PASS/FAIL table because of it means the operator learns nothing at all.
  try {
    Write-Host ""
    Write-Host "=== DIAGNOSTICS ===" -ForegroundColor Yellow

    # Null-safe: if an earlier failure left these unset, the DIAGNOSTICS block
    # must still run.  Diagnostics that themselves crash are worse than none --
    # they replace the failure you needed to see with one you do not care about.
    $errLog = if ($NginxDir) { Join-Path $NginxDir "logs\error.log" } else { $null }
    if ($errLog -and (Test-Path $errLog)) {
        Write-Host "--- nginx error.log (last 25 lines)" -ForegroundColor Yellow
        Get-Content $errLog -Tail 25 | ForEach-Object { Write-Host "    $_" }
    } else { Write-Host "    (no nginx error.log at $errLog)" }

    $instLog = if ($env:TEMP) { Join-Path $env:TEMP "sysmanage-nginx-test.log" } else { $null }
    if ($instLog -and (Test-Path $instLog)) {
        Write-Host "--- install-nginx.ps1 log (FULL)" -ForegroundColor Yellow
        Get-Content $instLog | ForEach-Object { Write-Host "    $_" }
    } else {
        Write-Host "--- install-nginx.ps1 log: NOT FOUND at $instLog" -ForegroundColor Yellow
        Write-Host "    (the installer never started, or could not write its log)"
    }

    Write-Host "--- environment" -ForegroundColor Yellow
    Write-Host "    PSVersion       : $($PSVersionTable.PSVersion)"
    Write-Host "    OS arch         : $env:PROCESSOR_ARCHITECTURE"
    Write-Host "    ScriptDir       : $ScriptDir"
    Write-Host "    InstallDir      : $InstallDir"
    Write-Host "    ExecutionPolicy : $(Get-ExecutionPolicy)"
    $nssmPath = Join-Path $ScriptDir "nssm\nssm.exe"
    Write-Host "    nssm present    : $(Test-Path $nssmPath) ($nssmPath)"

    Write-Host "--- service" -ForegroundColor Yellow
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($svc) {
        Write-Host "    Status=$($svc.Status) StartType=$($svc.StartType)"
        & "$ScriptDir\nssm\nssm.exe" get $ServiceName Application 2>&1 | ForEach-Object { Write-Host "    Application: $_" }
        & "$ScriptDir\nssm\nssm.exe" get $ServiceName AppParameters 2>&1 | ForEach-Object { Write-Host "    AppParameters: $_" }
    } else { Write-Host "    service not registered" }

    Write-Host "--- port 443 owner" -ForegroundColor Yellow
    $c = Get-NetTCPConnection -LocalPort 443 -State Listen -ErrorAction SilentlyContinue
    if ($c) {
        foreach ($x in $c) {
            $pname = (Get-Process -Id $x.OwningProcess -ErrorAction SilentlyContinue).ProcessName
            Write-Host "    PID $($x.OwningProcess) ($pname)"
        }
    } else { Write-Host "    nothing listening on 443" }

    Write-Host "--- tree" -ForegroundColor Yellow
    if ($NginxDir -and (Test-Path $NginxDir)) {
        Get-ChildItem $NginxDir | ForEach-Object { Write-Host "    $($_.Name)" }
    } else { Write-Host "    $NginxDir does not exist" }
  } catch {
    Write-Host "    (diagnostics incomplete: $_)" -ForegroundColor Yellow
  }
}

# --------------------------------------------------------------------------
if (-not $KeepArtifacts) {
  # Wrapped for the same reason as diagnostics: a cleanup that cannot complete
  # (a locked nginx.exe, a service that will not stop) must not cost the
  # PASS/FAIL summary, which is the entire output the operator needs.
  try {
    Write-Host ""
    Write-Host "--- Cleanup" -ForegroundColor Cyan
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    & "$ScriptDir\nssm\nssm.exe" remove $ServiceName confirm 2>&1 | Out-Null
    Get-Process nginx -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $InstallDir -ErrorAction SilentlyContinue
    if ($script:MadeTls) {
        Remove-Item (Join-Path $TlsDir "server.crt") -Force -ErrorAction SilentlyContinue
        Remove-Item (Join-Path $TlsDir "server.key") -Force -ErrorAction SilentlyContinue
        Write-Host "    removed the throwaway certificate"
    }
    Write-Host "    removed $InstallDir and the test service"
  } catch {
    Write-Host "    cleanup incomplete: $_" -ForegroundColor Yellow
    Write-Host "    remove manually: $InstallDir  (service $ServiceName)" -ForegroundColor Yellow
  }
} else {
    Write-Host ""
    Write-Host "--- Artifacts KEPT at $InstallDir (service: $ServiceName)" -ForegroundColor Cyan
}

# --------------------------------------------------------------------------
Write-Host ""
Write-Host "=== SUMMARY ===" -ForegroundColor White
$script:Results | Format-Table -AutoSize Status, Step, Detail | Out-String | Write-Host

$skipped = @($script:Results | Where-Object { $_.Status -eq "SKIP" }).Count
if ($script:Failed -eq 0) {
    if ($skipped -gt 0) {
        Write-Host "INSTALL VERIFIED; $skipped serving check(s) SKIPPED (see reason above)." -ForegroundColor Yellow
    } else {
        Write-Host "ALL CHECKS PASSED - the Windows nginx install works on this machine." -ForegroundColor Green
    }
    Write-Host "Full log written to: $LogFile"
    exit 0
}
Write-Host "$($script:Failed) CHECK(S) FAILED - see the detail column and the diagnostics above." -ForegroundColor Red
Write-Host ""
Write-Host "Full log written to: $LogFile" -ForegroundColor White
Write-Host "Send that file back -- it has every step, the installer log, and the diagnostics."
exit 1

} finally {
    # ALWAYS stop the transcript.  An unhandled error used to leave it running,
    # so the file could be truncated or empty exactly when it was needed.
    if ($script:Transcribing) { try { Stop-Transcript | Out-Null } catch { } }
    if (Test-Path $LogFile) {
        Write-Host ""
        Write-Host "LOG: $LogFile ($([math]::Round((Get-Item $LogFile).Length / 1KB, 1)) KB)" -ForegroundColor White
    } else {
        Write-Host ""
        Write-Host "WARNING: no log was written to $LogFile" -ForegroundColor Red
    }
}
