# Offline checks only: does not start a game server or enable a hotspot.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$outputDir = Join-Path $repoRoot 'artifacts\launcher-network'
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$compiler = "$env:SystemRoot\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$output = Join-Path $outputDir 'test.exe'
& $compiler /nologo /target:exe /main:LauncherNetworkTest /codepage:65001 "/out:$output" `
    /reference:System.dll /reference:System.Drawing.dll /reference:System.Windows.Forms.dll /reference:System.Web.Extensions.dll `
    (Join-Path $repoRoot 'launcher\SteelFrontLauncher.cs') `
    (Join-Path $repoRoot 'launcher\NetworkSupport.cs') `
    (Join-Path $repoRoot 'tests\LauncherNetworkTest.cs')
if ($LASTEXITCODE -ne 0) { throw 'Launcher test build failed' }
& $output
if ($LASTEXITCODE -ne 0) { throw 'Launcher tests failed' }
$parseErrors = $null
$tokens = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $repoRoot 'launcher\hotspot.ps1'), [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
# Validation fails before accessing any system hotspot API.
$validation = '{"action":"start","ssid":"Chichao-LAN","password":"123456"}' | `
    & "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $repoRoot 'launcher\hotspot.ps1')
$result = $validation | ConvertFrom-Json
if ($result.ok -ne $false -or $result.error -notmatch '8-63') { throw 'Hotspot must reject a 6-character password before changing system state' }
Write-Host 'Hotspot syntax and safe early validation passed.'
