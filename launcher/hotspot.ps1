# Windows 10/11 Mobile Hotspot. Invoked only by explicit launcher actions.
# Credentials arrive over stdin, never arguments or a saved configuration file.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

function Wait-WinRt($operation, [Type]$resultType) {
    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetGenericArguments().Count -eq 1 -and $_.GetParameters().Count -eq 1
    } | Select-Object -First 1
    $task = $method.MakeGenericMethod($resultType).Invoke($null, @($operation))
    $task.GetAwaiter().GetResult()
}
function Get-ActiveIpv4 {
    foreach ($adapter in [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces()) {
        if ($adapter.OperationalStatus -ne 'Up') { continue }
        foreach ($ip in $adapter.GetIPProperties().UnicastAddresses) {
            if ($ip.Address.AddressFamily -eq 'InterNetwork') { $ip.Address.ToString() }
        }
    }
}
try {
    $request = [Console]::In.ReadToEnd() | ConvertFrom-Json
    if ($request.action -notin @('start', 'stop', 'status')) { throw 'Unknown hotspot action.' }
    if ($request.action -eq 'start') {
        if ([string]::IsNullOrWhiteSpace($request.ssid) -or [Text.Encoding]::UTF8.GetByteCount($request.ssid) -gt 32 -or $request.ssid.Contains([string][char]0)) { throw 'SSID must contain 1-32 UTF-8 bytes.' }
        if ($request.password -notmatch '^[!-~][ -~]{6,61}[!-~]$') { throw 'Password must contain 8-63 printable ASCII characters, without leading/trailing spaces.' }
    }
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime]
    $null = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime]
    $null = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringAccessPointConfiguration,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime]
    $null = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime]
    if ($request.adapterId) {
        $profile = [Windows.Networking.Connectivity.NetworkInformation]::GetConnectionProfiles() | Where-Object {
            $_.NetworkAdapter -and $_.NetworkAdapter.NetworkAdapterId.ToString() -eq $request.adapterId.Trim('{}')
        } | Select-Object -First 1
    } else {
        $profile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
    }
    if (-not $profile) { throw 'No usable source connection profile. Select a connected Ethernet/Wi-Fi adapter, or use Windows Mobile hotspot settings.' }
    $manager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)
    $sourceId = $profile.NetworkAdapter.NetworkAdapterId.ToString()
    if ($request.action -eq 'status') {
        @{ok=$true; state=$manager.TetheringOperationalState.ToString(); adapterId=$sourceId} | ConvertTo-Json -Compress
        exit 0
    }
    if ($request.action -eq 'start') {
        if ($manager.TetheringOperationalState -ne 'Off') { throw 'A hotspot is already on or transitioning. It was not changed. Use the existing hotspot or Windows settings.' }
        $before = @(Get-ActiveIpv4)
        $config = New-Object Windows.Networking.NetworkOperators.NetworkOperatorTetheringAccessPointConfiguration
        $config.Ssid = $request.ssid
        $config.Passphrase = $request.password
        $configure = [System.WindowsRuntimeSystemExtensions]::AsTask($manager.ConfigureAccessPointAsync($config))
        $configure.GetAwaiter().GetResult()
        $result = Wait-WinRt ($manager.StartTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
        if ($result.Status.ToString() -ne 'Success') { throw ('Hotspot start failed: ' + $result.Status + '. Check Wi-Fi hardware, source connection and Windows hotspot settings.') }
        if ($manager.TetheringOperationalState -ne 'On') { throw 'Windows did not confirm that the hotspot is on. Check system settings.' }
        $newAddresses = @()
        for ($i=0; $i -lt 12; $i++) {
            $newAddresses = @(Get-ActiveIpv4 | Where-Object { $_ -notin $before -and $_ -ne '127.0.0.1' -and $_ -notlike '169.254.*' })
            if ($newAddresses.Count -gt 0) { break }
            Start-Sleep -Milliseconds 250
        }
        # Never assume 192.168.137.1. If ambiguous, ask user to choose after refresh.
        $address = if ($newAddresses.Count -eq 1) { $newAddresses[0] } else { '' }
        @{ok=$true; state='On'; adapterId=$sourceId; address=$address} | ConvertTo-Json -Compress
    } else {
        if ($manager.TetheringOperationalState -eq 'Off') {
            @{ok=$true; state='Off'} | ConvertTo-Json -Compress
            exit 0
        }
        $config = $manager.GetCurrentAccessPointConfiguration()
        if ($config.Ssid -cne $request.ssid -or $config.Passphrase -cne $request.password) {
            throw 'Hotspot configuration changed outside the launcher. It was not stopped. Check Windows settings.'
        }
        $result = Wait-WinRt ($manager.StopTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
        if ($result.Status.ToString() -ne 'Success' -or $manager.TetheringOperationalState -ne 'Off') { throw ('Hotspot stop failed: ' + $result.Status + '. Close it in Windows settings.') }
        @{ok=$true; state='Off'} | ConvertTo-Json -Compress
    }
} catch {
    @{ok=$false; error=$_.Exception.Message} | ConvertTo-Json -Compress
    exit 1
}
