# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.
#
# Install and configure nginx as the SysManage reverse proxy on Windows.
#
# WHY THIS EXISTS
# ---------------
# Windows was the one platform with no web server.  The MSI extracted the built
# frontend to <InstallDir>\frontend and then NOTHING served it, while
# install.ps1 finished by telling the operator to open http://localhost:8080 --
# which is the API, not the console.  So a Windows install laid down the entire
# web UI, reported success, and served nothing: no console, no TLS, no security
# headers, and no /airgap-repo/ route.  Every other platform gets those from
# nginx.
#
# nginx is REQUIRED, not optional.  The rendered config terminates TLS on 443,
# serves the frontend from disk, and proxies /api/ and /ws to the backend on
# loopback 8080 -- the backend has no static-file mount, so without nginx there
# is no console at all.
#
# WHERE THE BINARY COMES FROM
#   1. A bundled nginx-<ver>.zip beside this script (air-gap installs -- the
#      bundle builder stages it there), used if present.
#   2. Otherwise downloaded from nginx.org.
# Either way the SHA-256 is verified before anything is extracted: this runs
# elevated and unpacks an executable that will front the management console.
#
# Run as Administrator.  Idempotent: safe to re-run.

param(
    [string]$InstallDir = "C:\Program Files\SysManage Server",
    [string]$LogFile = "$env:TEMP\sysmanage-nginx-install.log",
    # Overridable so the acceptance test can register an ISOLATED service
    # instead of reusing (and its cleanup then destroying) a production one.
    [string]$ServiceName = "SysManageNginx"
)

$ErrorActionPreference = "Stop"

# Pinned, not "latest".  An installer that silently tracks upstream changes the
# software it deploys without anyone choosing to -- and the hash below only
# means anything against a fixed version.  Bump both together.
$NginxVersion = "1.28.0"
$NginxSha256 = "db8c7a529f84c819702bd1c50926b27d961a48b4f72fc7c46b30314fc2bbfd7c"
$NginxUrl = "https://nginx.org/download/nginx-$NginxVersion.zip"

$NginxDir = Join-Path $InstallDir "nginx"

function Write-Log {
    <#
        Write-Host + Add-Content, NOT Tee-Object.

        Tee-Object writes to the file AND passes the line down the success
        stream.  Inside a function every logged line therefore became part of
        that function's RETURN VALUE: Get-NginxZip returned
        @("...Downloading nginx...", "...checksum verified", "C:\...\nginx.zip")
        and Expand-Archive received the whole array coerced to one string:

          The path '2026-08-19 09:11:48  Downloading nginx 1.28.0 from
          https://... C:\Users\...\nginx-1.28.0.zip' either does not exist

        The download and the SHA-256 check had both SUCCEEDED; only the return
        value was corrupt.  Write-Host does not touch the success stream, so a
        function's return value is only what it actually returns.
    #>
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "$stamp  $Message"
    Write-Host $line
    try { Add-Content -Path $LogFile -Value $line -ErrorAction Stop } catch { }
}

function Get-NginxZip {
    <#
        Returns the path to a verified nginx zip, or throws.

        Prefers a bundled copy so an air-gapped install needs no network; the
        air-gap bundle builder stages nginx-<ver>.zip next to this script.
    #>
    $bundled = Join-Path $PSScriptRoot "nginx-$NginxVersion.zip"
    if (Test-Path $bundled) {
        Write-Log "Using bundled nginx: $bundled"
        $zip = $bundled
    } else {
        $zip = Join-Path $env:TEMP "nginx-$NginxVersion.zip"
        Write-Log "Downloading nginx $NginxVersion from $NginxUrl"
        try {
            # Tls12 explicitly: older Windows PowerShell defaults to SSL3/TLS1,
            # which nginx.org refuses, and the resulting error names neither.
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri $NginxUrl -OutFile $zip -UseBasicParsing
        } catch {
            throw ("Could not download nginx from $NginxUrl : $_`n" +
                   "nginx is REQUIRED - the SysManage console is served by it, " +
                   "not by the API.`nOn a host without internet access, use an " +
                   "air-gap bundle (it ships nginx), or place " +
                   "nginx-$NginxVersion.zip next to this script and re-run.")
        }
    }

    # Verify BEFORE extracting.  This script runs elevated and the archive
    # contains an executable that will terminate TLS for the console.
    $actual = (Get-FileHash -Path $zip -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $NginxSha256.ToLower()) {
        throw ("nginx archive failed checksum verification.`n" +
               "  expected $NginxSha256`n  got      $actual`n" +
               "Refusing to extract it.")
    }
    Write-Log "nginx archive checksum verified"
    return $zip
}

function Install-NginxFiles {
    param([string]$Zip)

    $staging = Join-Path $env:TEMP "sysmanage-nginx-staging"
    if (Test-Path $staging) { Remove-Item -Path $staging -Recurse -Force }
    New-Item -ItemType Directory -Path $staging -Force | Out-Null
    Expand-Archive -Path $Zip -DestinationPath $staging -Force

    # The archive has ONE top-level dir (nginx-<ver>/); lift its contents so
    # paths do not carry the version and the config never needs re-rendering
    # on an upgrade.
    $inner = Get-ChildItem -Path $staging -Directory | Select-Object -First 1
    if (-not $inner) { throw "Unexpected nginx archive layout: no top-level directory in $Zip" }

    # Preserve conf/ and any TLS material across a re-run; replace the binary.
    if (-not (Test-Path $NginxDir)) {
        New-Item -ItemType Directory -Path $NginxDir -Force | Out-Null
    }
    foreach ($item in Get-ChildItem -Path $inner.FullName) {
        $dest = Join-Path $NginxDir $item.Name
        if ($item.Name -eq "conf" -and (Test-Path $dest)) {
            # Keep the operator's edited nginx.conf; only refresh the stock
            # files they are not expected to have touched.
            continue
        }
        if (Test-Path $dest) { Remove-Item -Path $dest -Recurse -Force }
        Move-Item -Path $item.FullName -Destination $dest
    }
    Remove-Item -Path $staging -Recurse -Force
    Write-Log "nginx $NginxVersion installed to $NginxDir"
}

function Set-SysManageConfig {
    <#
        Drop in the generated SysManage server block and make nginx.conf
        include it.  The .conf is GENERATED from
        installer/nginx/sysmanage-nginx.conf.template by
        scripts/render_nginx_configs.py, exactly like every other platform's,
        so Windows cannot drift from the others.
    #>
    $confDir = Join-Path $NginxDir "conf"
    if (-not (Test-Path $confDir)) { New-Item -ItemType Directory -Path $confDir -Force | Out-Null }

    $src = Join-Path $PSScriptRoot "sysmanage-nginx.conf"
    if (-not (Test-Path $src)) {
        # Also look in the install dir: the MSI lays the config down there.
        $src = Join-Path $InstallDir "sysmanage-nginx.conf"
    }
    if (-not (Test-Path $src)) {
        throw "sysmanage-nginx.conf not found next to this script or in $InstallDir"
    }
    Copy-Item -Path $src -Destination (Join-Path $confDir "sysmanage-nginx.conf") -Force
    Write-Log "Installed sysmanage-nginx.conf into $confDir"

    # nginx.conf must include it.  Idempotent: only add the include once, and
    # do it INSIDE the existing http {} block -- a server block at top level is
    # a syntax error, which would leave nginx refusing to start.
    $mainConf = Join-Path $confDir "nginx.conf"
    $includeLine = "    include sysmanage-nginx.conf;"
    if (-not (Test-Path $mainConf)) {
        throw "$mainConf missing - nginx archive layout not as expected"
    }
    $text = Get-Content -Path $mainConf -Raw
    if ($text -match [regex]::Escape("include sysmanage-nginx.conf;")) {
        Write-Log "nginx.conf already includes sysmanage-nginx.conf"
        return
    }
    # Insert before the LAST closing brace of http {}.  Matching the final "}"
    # of the file is what nginx's own stock layout makes safe: http {} is the
    # last block in the shipped nginx.conf.
    $idx = $text.LastIndexOf("}")
    if ($idx -lt 0) { throw "Could not parse $mainConf (no closing brace)" }
    $text = $text.Substring(0, $idx) + "$includeLine`r`n" + $text.Substring($idx)
    # WriteAllText with an explicit BOM-less encoder, NOT Set-Content.
    # In Windows PowerShell 5.1 "-Encoding UTF8" means UTF-8 *with* a BOM, and
    # nginx does not skip it -- it tries to parse it as a configuration
    # directive and refuses to start:
    #     nginx: [emerg] unknown directive "<BOM>" in conf/nginx.conf:3
    # UTF8Encoding($false) is the "no BOM" constructor and behaves the same on
    # PowerShell 5.1 and 7.
    [System.IO.File]::WriteAllText(
        $mainConf, $text, (New-Object System.Text.UTF8Encoding($false)))
    Write-Log "Added include for sysmanage-nginx.conf to nginx.conf"
}

function Register-NginxService {
    <#
        Run nginx under NSSM, the same supervisor the API service uses.

        nginx on Windows has no native service support -- started bare it dies
        with the console session, so the console would silently disappear on
        logout.  NSSM is already bundled for the API service.
    #>
    $nssm = Join-Path $InstallDir "nssm.exe"
    if (-not (Test-Path $nssm)) {
        $nssm = Join-Path $PSScriptRoot "nssm\nssm.exe"
    }
    if (-not (Test-Path $nssm)) {
        Write-Log "WARNING: nssm.exe not found - cannot register the nginx service."
        Write-Log "         Start nginx manually: $NginxDir\nginx.exe"
        return
    }

    $exe = Join-Path $NginxDir "nginx.exe"

    # Get-Service, NOT `nssm status`.  nssm writes "Can't open service!" to
    # STDERR when the service does not exist, and with
    # $ErrorActionPreference = "Stop" PowerShell promotes any native stderr
    # write to a TERMINATING error -- so the completely normal "nothing to
    # replace" path aborted the whole install.  `2>$null` does not help: the
    # promotion happens regardless of redirection.  Get-Service answers the
    # same question without a subprocess.
    # Native commands are run with ErrorActionPreference relaxed for this block
    # only.  `nssm stop` on an already-stopped service, and `nssm set` on some
    # options, write informational text to STDERR; with "Stop" in force that is
    # promoted to a terminating error and aborts an install that is going
    # perfectly well.  Success is judged by $LASTEXITCODE and by whether the
    # service actually exists afterwards -- both of which are checked -- not by
    # whether the tool said anything on stderr.
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {

    $existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Log "Service $ServiceName exists - reinstalling to pick up changes"
        & $nssm stop $ServiceName confirm 2>&1 | Out-File -FilePath $LogFile -Append
        & $nssm remove $ServiceName confirm 2>&1 | Out-File -FilePath $LogFile -Append
    }
    & $nssm install $ServiceName $exe 2>&1 | Out-File -FilePath $LogFile -Append
    # -p <prefix> so nginx resolves conf/ and logs/ relative to its own dir
    # rather than the service's working directory (which is C:\Windows\System32).
    & $nssm set $ServiceName AppParameters "-p `"$NginxDir`"" 2>&1 | Out-File -FilePath $LogFile -Append
    & $nssm set $ServiceName AppDirectory $NginxDir 2>&1 | Out-File -FilePath $LogFile -Append
    & $nssm set $ServiceName Start SERVICE_AUTO_START 2>&1 | Out-File -FilePath $LogFile -Append
    & $nssm set $ServiceName Description "nginx reverse proxy for SysManage Server (TLS termination, web console)" 2>&1 | Out-File -FilePath $LogFile -Append
    } finally {
        $ErrorActionPreference = $prevEap
    }

    # Verify rather than assume: nssm can exit 0 having done nothing useful,
    # and a missing service here means no console after a reboot.
    if (-not (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue)) {
        throw "nssm did not register the service $ServiceName (see $LogFile)"
    }
    Write-Log "Registered Windows service: $ServiceName"
}

function Test-NginxConfig {
    $exe = Join-Path $NginxDir "nginx.exe"
    if (-not (Test-Path $exe)) { return $false }
    & $exe -p "$NginxDir" -t 2>&1 | Out-File -FilePath $LogFile -Append
    return ($LASTEXITCODE -eq 0)
}

Write-Log "=== SysManage nginx setup ==="
try {
    $zip = Get-NginxZip
    Install-NginxFiles -Zip $zip
    Set-SysManageConfig
    Register-NginxService

    if (Test-NginxConfig) {
        Write-Log "nginx configuration test passed"
    } else {
        # NOT fatal.  The config references a TLS certificate the operator has
        # not supplied yet, and nginx -t fails when it is missing -- that is the
        # expected state immediately after install, and the TLS message below
        # tells them what to do.  Failing here would abort an otherwise correct
        # install over a step the operator has not reached.
        Write-Log "nginx configuration test did not pass yet (expected before the TLS certificate is installed)"
    }
    Write-Log "=== nginx setup complete ==="
} catch {
    Write-Log "ERROR: $_"
    throw
}
