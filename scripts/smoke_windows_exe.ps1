# Smoke-test a frozen ChichaoSteelFront.exe on Windows.
# Starts with --no-browser, waits for /api/health, then stops the process.
# Example:
#   powershell -ExecutionPolicy Bypass -File scripts/smoke_windows_exe.ps1 -Zip release\ChichaoSteelFront-win64.zip

[CmdletBinding()]
param(
    [string]$Zip = '',
    [string]$Exe = '',
    [int]$Port = 18181,
    [int]$TimeoutSeconds = 90
)

$ErrorActionPreference = 'Stop'

function Stop-SmokeProcess {
    param($Process)
    if (-not $Process) {
        return
    }
    try {
        if (-not $Process.HasExited) {
            Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
            $Process.WaitForExit(8000) | Out-Null
        }
    } catch {
    }
}

if (-not $Zip -and -not $Exe) {
    throw 'Pass -Zip release\ChichaoSteelFront-win64.zip or -Exe path\to\ChichaoSteelFront.exe'
}

$scratch = $null
if ($Zip) {
    if (-not (Test-Path -LiteralPath $Zip)) {
        throw "Missing zip: $Zip"
    }
    $zipPath = (Resolve-Path -LiteralPath $Zip).Path
    $scratch = Join-Path ([System.IO.Path]::GetTempPath()) ("chichao-smoke-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $scratch | Out-Null
    try {
        Add-MpPreference -ExclusionPath $scratch -ErrorAction SilentlyContinue
    } catch {
    }
    Write-Host "Extracting $zipPath -> $scratch"
    Expand-Archive -LiteralPath $zipPath -DestinationPath $scratch -Force
    $found = Get-ChildItem -LiteralPath $scratch -Recurse -Filter 'ChichaoSteelFront.exe' | Select-Object -First 1
    if (-not $found) {
        throw "Zip did not contain ChichaoSteelFront.exe: $zipPath"
    }
    $Exe = $found.FullName
}

if (-not (Test-Path -LiteralPath $Exe)) {
    throw "Missing exe: $Exe"
}

$exePath = (Resolve-Path -LiteralPath $Exe).Path
$workDir = Split-Path -Parent $exePath
$stdoutLog = Join-Path $workDir 'smoke-stdout.log'
$stderrLog = Join-Path $workDir 'smoke-stderr.log'
$healthUrl = "http://127.0.0.1:$Port/api/health"
$indexUrl = "http://127.0.0.1:$Port/"

try {
    Add-MpPreference -ExclusionPath $workDir -ErrorAction SilentlyContinue
} catch {
}

$env:HOST = '127.0.0.1'
$env:PORT = [string]$Port
$env:STEEL_FRONT_NO_BROWSER = '1'
$env:STEEL_FRONT_OPEN_BROWSER = '0'
$env:STEEL_FRONT_DATA_DIR = Join-Path $workDir 'smoke-data'

Write-Host "Starting $exePath --no-browser on 127.0.0.1:$Port"
$proc = Start-Process -FilePath $exePath -ArgumentList '--no-browser' `
    -WorkingDirectory $workDir -PassThru `
    -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$health = $null
$lastError = $null
try {
    while ((Get-Date) -lt $deadline) {
        if ($proc.HasExited) {
            $out = ''
            $err = ''
            if (Test-Path -LiteralPath $stdoutLog) { $out = Get-Content -LiteralPath $stdoutLog -Raw -ErrorAction SilentlyContinue }
            if (Test-Path -LiteralPath $stderrLog) { $err = Get-Content -LiteralPath $stderrLog -Raw -ErrorAction SilentlyContinue }
            throw "Frozen exe exited early with code $($proc.ExitCode). stdout:`n$out`nstderr:`n$err"
        }
        try {
            $resp = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 3
            if ($resp.StatusCode -eq 200) {
                $health = $resp.Content | ConvertFrom-Json
                if ($health.ok -eq $true) {
                    break
                }
                $lastError = "health ok flag was $($health.ok)"
            } else {
                $lastError = "HTTP $($resp.StatusCode)"
            }
        } catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Milliseconds 500
    }

    if (-not $health -or $health.ok -ne $true) {
        $out = ''
        $err = ''
        if (Test-Path -LiteralPath $stdoutLog) { $out = Get-Content -LiteralPath $stdoutLog -Raw -ErrorAction SilentlyContinue }
        if (Test-Path -LiteralPath $stderrLog) { $err = Get-Content -LiteralPath $stderrLog -Raw -ErrorAction SilentlyContinue }
        throw "Timed out waiting for $healthUrl ($lastError). stdout:`n$out`nstderr:`n$err"
    }

    $index = Invoke-WebRequest -Uri $indexUrl -UseBasicParsing -TimeoutSec 5
    if ($index.StatusCode -ne 200 -or ($index.Content -notmatch '(?i)html')) {
        throw "GET / did not return HTML (HTTP $($index.StatusCode))"
    }

    Write-Host ("Health OK: version={0} port={1} rooms={2}" -f $health.version, $health.port, $health.rooms)
    if ([int]$health.port -ne $Port) {
        throw "Health port $($health.port) != requested $Port"
    }
    Write-Host "GET / returned HTML ($($index.RawContentLength) bytes)"
} finally {
    Stop-SmokeProcess -Process $proc
    if ($scratch -and (Test-Path -LiteralPath $scratch)) {
        Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "Frozen exe smoke test passed."
