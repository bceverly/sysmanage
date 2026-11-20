# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

# The ARM64 libpq runtime DLLs the MSIs bundle, in one place (dot-source it).
#
# zlib's DLL is named by the vcpkg zlib port that built libpq: z.dll from the
# older port, zlib1.dll (or zlib.dll) from zlib 1.4 -- CI, 2026-11-20: "vcpkg
# did not produce z.dll".  libpq.dll loads the name it was linked against, so
# the DLL is staged under its own name (never renamed) and WiX is told which
# (-d LIBPQ_ZLIB=...).

$LibpqZlibNames = @('z.dll', 'zlib1.dll', 'zlib.dll')
$LibpqFixedDlls = @('libpq.dll', 'libcrypto-3-arm64.dll', 'libssl-3-arm64.dll', 'lz4.dll', 'legacy.dll')

function Get-LibpqZlibName([string]$Dir) {
    foreach ($name in $LibpqZlibNames) {
        if (Test-Path (Join-Path $Dir $name)) { return $name }
    }
    return $null
}

# Every DLL that must be in $Dir; a missing zlib shows as its first name.
function Get-LibpqArm64Dlls([string]$Dir) {
    $zlib = Get-LibpqZlibName $Dir
    if (-not $zlib) { $zlib = $LibpqZlibNames[0] }
    return @($LibpqFixedDlls + $zlib)
}

function Get-LibpqArm64Missing([string]$Dir) {
    if (-not (Test-Path $Dir)) { return @(Get-LibpqArm64Dlls $Dir) }
    return @(Get-LibpqArm64Dlls $Dir | Where-Object { -not (Test-Path (Join-Path $Dir $_)) })
}

# Copy the runtime set from a vcpkg arm64-windows install into $Stage.
# legacy.dll (OpenSSL's legacy provider) is looked for under the whole
# release tree, not only bin\, since OpenSSL ports have moved it.
function Copy-LibpqArm64Dlls([string]$Installed, [string]$Stage) {
    $bin = Join-Path $Installed 'bin'
    if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $Stage | Out-Null
    $zlib = Get-LibpqZlibName $bin
    if (-not $zlib) {
        Get-ChildItem $bin -Filter *.dll | ForEach-Object { Write-Host "  in bin: $($_.Name)" }
        throw "vcpkg produced no zlib DLL ($($LibpqZlibNames -join ', ')) in $bin"
    }
    foreach ($dll in @($LibpqFixedDlls + $zlib)) {
        $src = Join-Path $bin $dll
        if (-not (Test-Path $src)) {
            $found = Get-ChildItem $Installed -Recurse -Filter $dll -File -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -notmatch '[\\/]debug[\\/]' } | Select-Object -First 1
            if (-not $found) {
                Get-ChildItem $bin -Filter *.dll | ForEach-Object { Write-Host "  in bin: $($_.Name)" }
                throw "vcpkg did not produce $dll under $Installed"
            }
            $src = $found.FullName
        }
        Copy-Item $src (Join-Path $Stage $dll) -Force
    }
    return $zlib
}
