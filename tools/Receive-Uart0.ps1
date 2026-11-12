param([string]$Port = 'COM20', [int]$Baud = 115200)
$ErrorActionPreference = 'Stop'
$logDir = Join-Path $PSScriptRoot '..\logs\uart0'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$base = Join-Path $logDir ($Port + '_' + $stamp)
$statusPath = Join-Path $logDir 'receiver_status.json'
$stopPath = Join-Path $logDir 'stop.request'
$serial = [System.IO.Ports.SerialPort]::new($Port, $Baud, [System.IO.Ports.Parity]::None, 8, [System.IO.Ports.StopBits]::One)
$serial.Handshake = [System.IO.Ports.Handshake]::None
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.ReadTimeout = 200
$raw = $null
$total = 0L
function Save-Status([string]$state, [string]$errorText = '') {
    @{ state=$state; port=$Port; baud=$Baud; pid=$PID; bytes=$total; log=($base+'.log'); updated=(Get-Date -Format o); error=$errorText } | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
}
try {
    $serial.Open()
    $raw = [System.IO.File]::Open($base+'.log', [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)
    Save-Status 'receiving'
    $buffer = New-Object byte[] 4096
    while (!(Test-Path -LiteralPath $stopPath)) {
        $commandPath = Join-Path $logDir 'send.request'
        if (Test-Path -LiteralPath $commandPath) {
            $command = [System.IO.File]::ReadAllText($commandPath).TrimEnd("`r", "`n")
            $serial.Write($command + "`r`n")
            Add-Content -LiteralPath ($base+'.commands.txt') -Value ((Get-Date -Format o) + ' TX: ' + $command)
            Remove-Item -LiteralPath $commandPath
        }
        try { $count = $serial.Read($buffer,0,$buffer.Length) } catch [System.TimeoutException] { continue }
        if ($count -gt 0) {
            $raw.Write($buffer,0,$count)
            $raw.Flush()
            $total += $count
            Save-Status 'receiving'
        }
    }
    Save-Status 'stopped'
} catch {
    Save-Status 'error' $_.Exception.Message
} finally {
    if ($raw) { $raw.Dispose() }
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
}
