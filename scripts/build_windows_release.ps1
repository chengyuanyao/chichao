# Build the Windows one-click itch.io zip (PyInstaller onedir).
# Run on Windows 10/11 with Python 3.8+ on PATH. Does not cross-compile from Linux.
# Example:
#   powershell -ExecutionPolicy Bypass -File scripts/build_windows_release.ps1

$ErrorActionPreference = 'Stop'

$scriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptsDir
Set-Location $repoRoot

$python = $null
foreach ($candidate in @('py', 'python', 'python3')) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd) {
        $python = $cmd.Source
        break
    }
}
if (-not $python) {
    throw 'Python 3.8+ was not found. The build machine needs Python; the player zip will not.'
}

Write-Host "Using $python"
& $python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw 'Python 3.8+ is required to run PyInstaller.'
}

$venv = Join-Path $repoRoot '.packaging-venv'
if (-not (Test-Path (Join-Path $venv 'Scripts\python.exe'))) {
    Write-Host "Creating packaging venv at $venv"
    & $python -m venv $venv
}
$venvPython = Join-Path $venv 'Scripts\python.exe'
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install 'pyinstaller>=5.13,<7'

$spec = Join-Path $scriptsDir 'chichao.spec'
& $venvPython -m PyInstaller --noconfirm --clean $spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$distExe = Join-Path $repoRoot 'dist\ChichaoSteelFront\ChichaoSteelFront.exe'
if (-not (Test-Path $distExe)) {
    throw "PyInstaller did not produce $distExe"
}

$releaseRoot = Join-Path $repoRoot 'release'
$winDir = Join-Path $releaseRoot 'ChichaoSteelFront-win64'
$winZip = Join-Path $releaseRoot 'ChichaoSteelFront-win64.zip'
$srcDir = Join-Path $releaseRoot 'ChichaoSteelFront-source'
$srcZip = Join-Path $releaseRoot 'ChichaoSteelFront-source.zip'

& $venvPython (Join-Path $scriptsDir 'stage_release.py') windows-layout --output $winDir --zip $winZip
if ($LASTEXITCODE -ne 0) { throw 'windows-layout staging failed' }

& $venvPython (Join-Path $scriptsDir 'stage_release.py') source --output $srcDir --zip $srcZip
if ($LASTEXITCODE -ne 0) { throw 'source staging failed' }

Write-Host ""
Write-Host "Windows one-click zip: $winZip"
Write-Host "Source / macOS / Linux zip: $srcZip"
Write-Host "Player entry: ChichaoSteelFront.exe (no system Python required)"
Write-Host "Unsigned exe may show SmartScreen: More info -> Run anyway"
