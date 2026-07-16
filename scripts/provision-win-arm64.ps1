# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

<#
.SYNOPSIS
  Provision the native Windows-ARM64 build toolchain that `make install-dev` needs.

.DESCRIPTION
  On native ARM64 Windows, several of this project's Python dependencies have no
  arm64 wheels and must build from source, and pure-Python psycopg needs a native
  arm64 libpq at runtime. This script provisions, idempotently:

    1. MSVC ARM64 C++ build tools  (compiles the Cython/C extensions + vcpkg;
                                    needs elevation -> triggers a UAC prompt)
    2. Rust                        (cryptography's source build)
    3. vcpkg + native arm64 libpq  (for pure-Python psycopg; on PATH + copied
                                    into .venv\Scripts so it's found at runtime)
    4. OPENSSL_DIR / OPENSSL_NO_VENDOR  (points cryptography's build at the
                                         vcpkg OpenSSL; persisted for future shells)

  Each step no-ops if already satisfied. The whole script no-ops on non-ARM64
  (x64/x64-emulated), where `psycopg[binary]` + prebuilt wheels are used instead.

  NOTE: the pip build in the SAME `make install-dev` run does not inherit env/PATH
  changes made here (a child can't mutate the parent make process), so the Makefile
  also prefixes its pip lines with $(WIN_ARM64_ENV) to bridge the first run.

  NOTE: step 1 (MSVC install) needs admin. If this process is already elevated
  (e.g. an elevated SSH session), it runs the VS installer directly; otherwise it
  falls back to a UAC prompt, which requires an interactive desktop and therefore
  does NOT work over a headless SSH session.
#>
$ErrorActionPreference = "Stop"

# --- Only relevant when building against native ARM64 Python -----------------
$arch = (& python -c "import platform; print(platform.machine())" 2>$null)
if ($arch -ne "ARM64") {
    Write-Host "[provision] Python arch is '$arch' (not ARM64) - nothing to provision." -ForegroundColor Gray
    exit 0
}
Write-Host "=== Provisioning native Windows ARM64 build toolchain ===" -ForegroundColor Cyan

function Test-Elevated {
    # True if this process holds a full admin token (High integrity). An elevated
    # SSH session (password logon, or key logon with LocalAccountTokenFilterPolicy=1)
    # is already elevated and needs no UAC prompt — which SSH couldn't display anyway.
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltinRole]::Administrator)
}

# --- 1. MSVC ARM64 C++ build tools -------------------------------------------
$vsBuildTools = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools"
$vsInstaller  = "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vs_installer.exe"
function Test-Arm64Msvc {
    @(Get-ChildItem "$vsBuildTools\VC\Tools\MSVC\*\lib\arm64\msvcrt.lib" -ErrorAction SilentlyContinue).Count -gt 0
}
if (Test-Arm64Msvc) {
    Write-Host "[provision] MSVC ARM64 build tools: already installed." -ForegroundColor Green
} elseif (Test-Path $vsInstaller) {
    $vsArgs = "modify --installPath `"$vsBuildTools`" --add Microsoft.VisualStudio.Component.VC.Tools.ARM64 --quiet --norestart"
    if (Test-Elevated) {
        # Already elevated (e.g. an elevated SSH session): run the installer directly.
        # A UAC consent prompt (-Verb RunAs) needs an interactive desktop, which a
        # headless SSH session (Session 0) doesn't have, so RunAs would just hang.
        Write-Host "[provision] Installing MSVC ARM64 build tools (session already elevated)..." -ForegroundColor Yellow
        Start-Process -FilePath $vsInstaller -ArgumentList $vsArgs -Wait -NoNewWindow
    } else {
        Write-Host "[provision] Installing MSVC ARM64 build tools (elevating via UAC - accept the prompt)..." -ForegroundColor Yellow
        Start-Process -FilePath $vsInstaller -ArgumentList $vsArgs -Verb RunAs -Wait
    }
    if (-not (Test-Arm64Msvc)) {
        Write-Host "[provision] ERROR: MSVC ARM64 tools still missing after install." -ForegroundColor Red
        Write-Host "  Over SSH without an elevated token: run this once from an elevated session," -ForegroundColor Yellow
        Write-Host "  or set LocalAccountTokenFilterPolicy=1 (then reconnect) for key-based auth;" -ForegroundColor Yellow
        Write-Host "  or add 'MSVC v143 - VS 2022 C++ ARM64 build tools' via the Visual Studio Installer." -ForegroundColor Yellow
        exit 1
    }
    Write-Host "[provision] MSVC ARM64 build tools installed." -ForegroundColor Green
} else {
    Write-Host "[provision] ERROR: Visual Studio Installer not found; cannot add ARM64 tools." -ForegroundColor Red
    exit 1
}

# --- 2. Rust (cryptography's source build) -----------------------------------
$cargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
if ((Get-Command cargo -ErrorAction SilentlyContinue) -or (Test-Path (Join-Path $cargoBin "cargo.exe"))) {
    Write-Host "[provision] Rust: already installed." -ForegroundColor Green
} else {
    Write-Host "[provision] Installing Rust via winget..." -ForegroundColor Yellow
    winget install --id Rustlang.Rustup -e --accept-package-agreements --accept-source-agreements --disable-interactivity
    if (-not (Test-Path (Join-Path $cargoBin "cargo.exe"))) {
        Write-Host "[provision] ERROR: Rust install did not produce cargo." -ForegroundColor Red
        exit 1
    }
    Write-Host "[provision] Rust installed." -ForegroundColor Green
}
$env:PATH = "$cargoBin;$env:PATH"

# --- 3. vcpkg ----------------------------------------------------------------
$vcpkg    = Join-Path $env:USERPROFILE "vcpkg"
$vcpkgExe = Join-Path $vcpkg "vcpkg.exe"
if (-not (Test-Path $vcpkgExe)) {
    Write-Host "[provision] Bootstrapping vcpkg..." -ForegroundColor Yellow
    if (-not (Test-Path $vcpkg)) { git clone --depth 1 https://github.com/microsoft/vcpkg $vcpkg }
    & (Join-Path $vcpkg "bootstrap-vcpkg.bat") -disableMetrics
    if (-not (Test-Path $vcpkgExe)) { Write-Host "[provision] ERROR: vcpkg bootstrap failed." -ForegroundColor Red; exit 1 }
}
Write-Host "[provision] vcpkg: ready." -ForegroundColor Green

# --- 4. Native ARM64 libpq (only if libpq.dll isn't already discoverable) -----
$vcpkgBin = Join-Path $vcpkg "installed\arm64-windows\bin"
function Test-Libpq {
    if (Test-Path (Join-Path $vcpkgBin "libpq.dll")) { return $true }
    foreach ($d in ($env:PATH -split ';')) {
        if ($d -and (Test-Path (Join-Path $d "libpq.dll"))) { return $true }
    }
    return $false
}
if (Test-Libpq) {
    Write-Host "[provision] libpq: already present." -ForegroundColor Green
} else {
    Write-Host "[provision] Building native ARM64 libpq via vcpkg (a few minutes)..." -ForegroundColor Yellow
    & $vcpkgExe install libpq:arm64-windows
    if (-not (Test-Path (Join-Path $vcpkgBin "libpq.dll"))) {
        Write-Host "[provision] ERROR: libpq build failed." -ForegroundColor Red; exit 1
    }
    Write-Host "[provision] Native ARM64 libpq built." -ForegroundColor Green
}
# Persist the vcpkg arm64 bin on the user PATH so libpq is found at runtime.
$userPath = [Environment]::GetEnvironmentVariable('Path','User')
if (($userPath -split ';') -notcontains $vcpkgBin) {
    [Environment]::SetEnvironmentVariable('Path', $userPath.TrimEnd(';') + ';' + $vcpkgBin, 'User')
    Write-Host "[provision] Added libpq dir to user PATH: $vcpkgBin" -ForegroundColor Green
}

# --- 4b. Static ARM64 OpenSSL for cryptography's from-source build ------------
# cryptography has no win_arm64 wheel for the CVE-patched pin, so it builds from
# source. Linked against a STATIC OpenSSL (+ a static CRT via RUSTFLAGS, set by the
# Makefile), its _rust extension carries no external OpenSSL/vcruntime deps — a
# dynamic build loads flakily against this box's multi-Python PATH.
$osslStaticLib = Join-Path $vcpkg "installed\arm64-windows-static\lib\libcrypto.lib"
if (Test-Path $osslStaticLib) {
    Write-Host "[provision] Static OpenSSL: already present." -ForegroundColor Green
} else {
    Write-Host "[provision] Building static ARM64 OpenSSL via vcpkg (a few minutes)..." -ForegroundColor Yellow
    & $vcpkgExe install openssl:arm64-windows-static
    if (-not (Test-Path $osslStaticLib)) {
        Write-Host "[provision] ERROR: static OpenSSL build failed." -ForegroundColor Red; exit 1
    }
    Write-Host "[provision] Static ARM64 OpenSSL built." -ForegroundColor Green
}

# libpq + its runtime deps go next to the venv's python (.venv\Scripts, which is on
# PATH when the venv is active) so pure-Python psycopg — which locates libpq via
# ctypes/PATH — finds it without a fresh shell. (Mirrors the MSI's install.ps1.)
$venvScripts = Join-Path (Get-Location) ".venv\Scripts"
if (Test-Path $venvScripts) {
    foreach ($d in @("libpq.dll", "libcrypto-3-arm64.dll", "libssl-3-arm64.dll",
                     "z.dll", "lz4.dll", "legacy.dll")) {
        $src = Join-Path $vcpkgBin $d
        if (Test-Path $src) { Copy-Item $src $venvScripts -Force }
    }
    Write-Host "[provision] Copied libpq + OpenSSL runtime DLLs into .venv\Scripts (for psycopg)." -ForegroundColor Green
} else {
    Write-Host "[provision] .venv not found; skipping DLL copy (created by 'make install-dev')." -ForegroundColor Yellow
}

# --- 5. OpenSSL env for cryptography's static source build -------------------
# Point cryptography's build at the STATIC OpenSSL. The static-CRT flag
# (RUSTFLAGS=-C target-feature=+crt-static) is applied by the Makefile's
# WIN_ARM64_ENV during `make install-dev`; a manual rebuild should go through make
# (or set RUSTFLAGS too) to get the fully self-contained _rust.
$osslStatic = Join-Path $vcpkg "installed\arm64-windows-static"
[Environment]::SetEnvironmentVariable('OPENSSL_DIR', $osslStatic, 'User')
[Environment]::SetEnvironmentVariable('OPENSSL_STATIC', '1', 'User')
[Environment]::SetEnvironmentVariable('OPENSSL_NO_VENDOR', '1', 'User')
Write-Host "[provision] OPENSSL_DIR/OPENSSL_STATIC set for cryptography's static build." -ForegroundColor Green

Write-Host "=== ARM64 toolchain provisioned. ===" -ForegroundColor Cyan
