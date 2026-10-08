# Build the Windows one-click itch.io zip (PyInstaller onedir).
# Run on Windows 10/11 with Python 3.8+ on PATH. Does not cross-compile from Linux.
# Example:
#   powershell -ExecutionPolicy Bypass -File scripts/build_windows_release.ps1
# GitHub Actions uses the same script on windows-latest (see
# .github/workflows/windows-release.yml). Honor $env:PYTHON when set.

$ErrorActionPreference = 'Stop'

function Resolve-BuildPython {
    if ($env:PYTHON) {
        if (Test-Path -LiteralPath $env:PYTHON) {
            return (Resolve-Path -LiteralPath $env:PYTHON).Path
        }
        $fromEnv = Get-Command $env:PYTHON -ErrorAction SilentlyContinue
        if ($fromEnv) {
            return $fromEnv.Source
        }
    }
    foreach ($candidate in @('python', 'python3', 'py')) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $cmd) {
            continue
        }
        $path = $cmd.Source
        if ($path -match 'WindowsApps') {
            continue
        }
        return $path
    }
    throw 'Python 3.8+ was not found. The build machine needs Python; the player zip will not.'
}

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Fail,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )
    & $Command
    if ($null -eq $LASTEXITCODE) {
        return
    }
    if ($LASTEXITCODE -ne 0) {
        throw "$Fail (exit $LASTEXITCODE)"
    }
}

$scriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptsDir
Set-Location $repoRoot

$python = Resolve-BuildPython
Write-Host "Using $python"
Invoke-Native -Fail 'Python 3.8+ is required to run PyInstaller' -Command {
    & $python -c "import sys; print(sys.version); raise SystemExit(0 if sys.version_info >= (3, 8) else 1)"
}

$venv = Join-Path $repoRoot '.packaging-venv'
$venvPython = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "Creating packaging venv at $venv"
    Invoke-Native -Fail 'Failed to create packaging venv' -Command {
        & $python -m venv $venv
    }
}
Invoke-Native -Fail 'pip upgrade failed' -Command {
    & $venvPython -m pip install --upgrade pip
}
Invoke-Native -Fail 'PyInstaller install failed' -Command {
    & $venvPython -m pip install 'pyinstaller>=5.13,<7'
}

$spec = Join-Path $scriptsDir 'chichao.spec'
Invoke-Native -Fail 'PyInstaller failed' -Command {
    & $venvPython -m PyInstaller --noconfirm --clean $spec
}

$distExe = Join-Path $repoRoot 'dist\ChichaoSteelFront\ChichaoSteelFront.exe'
if (-not (Test-Path -LiteralPath $distExe)) {
    throw "PyInstaller did not produce $distExe"
}

$releaseRoot = Join-Path $repoRoot 'release'
$winDir = Join-Path $releaseRoot 'ChichaoSteelFront-win64'
$winZip = Join-Path $releaseRoot 'ChichaoSteelFront-win64.zip'
$srcDir = Join-Path $releaseRoot 'ChichaoSteelFront-source'
$srcZip = Join-Path $releaseRoot 'ChichaoSteelFront-source.zip'

Invoke-Native -Fail 'windows-layout staging failed' -Command {
    & $venvPython (Join-Path $scriptsDir 'stage_release.py') windows-layout --output $winDir --zip $winZip
}

Invoke-Native -Fail 'source staging failed' -Command {
    & $venvPython (Join-Path $scriptsDir 'stage_release.py') source --output $srcDir --zip $srcZip
}

Write-Host ""
Write-Host "Windows one-click zip: $winZip"
Write-Host "Source / macOS / Linux zip: $srcZip"
Write-Host "Player entry: ChichaoSteelFront.exe (no system Python required)"
Write-Host "Unsigned exe may show SmartScreen: More info -> Run anyway"
