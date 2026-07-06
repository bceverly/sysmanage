<#
.SYNOPSIS
  Build grpcio from source on native Windows ARM64 (no win_arm64 wheel exists).

.DESCRIPTION
  opentelemetry-exporter-otlp depends on grpcio, which ships no win_arm64 wheel
  for any version, so on native ARM64 it must be built from source -- exactly like
  the OpenBSD/NetBSD branches build it. grpcio's vendored gRPC-core compiles fine
  with the MSVC ARM64 toolchain; the only obstacle is its extremely deep upb-gen
  source tree, whose ~187-char relative object paths, on top of pip's own deep build
  layout (<TMP>\pip-*-<8>\grpcio_<32-hex>\, ~64 chars), exceed the Windows MAX_PATH
  (260) limit so link.exe fails with "LNK1181: cannot open input file
  ...upb_minitable.obj". (Neither `pip install --no-binary` nor `pip wheel` avoids
  this -- both use that deep temp layout.)

  Fix: build the wheel in a SHORT, manually extracted source dir (via
  build-grpcio-wheel-win-arm64.ps1) so the object paths stay under MAX_PATH, then
  install it. That helper also enables long paths and parallelizes the compile.

  Runs BEFORE the main "pip install -r requirements*.txt" so grpcio is already
  satisfied when opentelemetry-exporter-otlp is resolved. Arm64-only and
  idempotent: it no-ops on x64 (which uses the prebuilt win_amd64 wheel) and when
  grpcio already imports. The ~20-30 min compile is expected for the gRPC core.
#>
$ErrorActionPreference = "Stop"

$arch = (& python -c "import platform; print(platform.machine())" 2>$null)
if ($arch -ne "ARM64") {
    Write-Host "[grpcio] arch is '$arch' (not ARM64) - using the prebuilt wheel." -ForegroundColor Gray
    exit 0
}

$py = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "[grpcio] .venv not found; skipping (created by 'make install-dev')." -ForegroundColor Yellow
    exit 0
}

# Already built for this interpreter?
& $py -c "import grpc" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "[grpcio] already installed." -ForegroundColor Green
    exit 0
}

# Build a grpcio wheel via the short-dir builder (pip's own deep temp layout would
# overflow MAX_PATH at link time), then install it into this interpreter.
Write-Host "[grpcio] no win_arm64 wheel - building from source (~20-30 min)..." -ForegroundColor Yellow
$wheelOut = Join-Path $env:SystemDrive "g-out"
try {
    & (Join-Path $PSScriptRoot "build-grpcio-wheel-win-arm64.ps1") -Python $py -OutputDir $wheelOut
} catch {
    Write-Host "[grpcio] ERROR: source build failed: $_" -ForegroundColor Red
    exit 1
}
$whl = Get-ChildItem "$wheelOut\grpcio-*.whl" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $whl) { Write-Host "[grpcio] ERROR: no wheel produced." -ForegroundColor Red; exit 1 }
& $py -m pip install $whl.FullName
if ($LASTEXITCODE -ne 0) {
    Write-Host "[grpcio] ERROR: installing the built wheel failed." -ForegroundColor Red
    exit 1
}
Write-Host "[grpcio] built and installed from source." -ForegroundColor Green
