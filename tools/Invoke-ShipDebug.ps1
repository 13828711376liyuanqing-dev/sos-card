# SAM | 2026-10-13 14:26 +08:00 | Capture bounded COM26 ship diagnostics;
# Enter is an explicit power-cut operation; default Preflight never confirms.
param([ValidateSet('Preflight','Enter')][string]$Mode='Preflight',[string]$Port='COM26')
$ErrorActionPreference='Stop'
$shipLog=''
$shipSerial=[System.IO.Ports.SerialPort]::new($Port,115200,[System.IO.Ports.Parity]::None,8,[System.IO.Ports.StopBits]::One)
$shipSerial.DtrEnable=$false
$shipSerial.RtsEnable=$false
$shipLogPath=Join-Path $PSScriptRoot ('..\logs\shipping_20261013\'+$Mode+'_'+(Get-Date -Format 'yyyyMMdd_HHmmss')+'.log')
function Send-ShipCommand([string]$Command,[int]$Seconds=2) {
    $script:shipLog += "`r`n"+[DateTimeOffset]::Now.ToString('o')+" TX: $Command`r`n"
    $shipSerial.Write($Command+"`r`n")
    $shipText=''; $shipUntil=[DateTime]::UtcNow.AddSeconds($Seconds)
    while([DateTime]::UtcNow -lt $shipUntil) {
        $shipText += $shipSerial.ReadExisting()
        Start-Sleep -Milliseconds 100
    }
    $script:shipLog += $shipText
    [System.IO.File]::WriteAllText($shipLogPath,$script:shipLog)
    return $shipText
}
try {
    $shipSerial.Open()
    $shipStatus=Send-ShipCommand 'charger ship status'
    if ($shipStatus -notmatch '\[SHIP\] state=IDLE') { throw 'Expected IDLE; use ship status/cancel before another test' }
    if ($Mode -eq 'Preflight') {
        # Before explicit rail OFF, boot rail should make preparation fail.
        $shipRejected=Send-ShipCommand 'charger ship prepare'
        Write-Output $shipRejected
        if ($shipRejected -notmatch 'prepare refused') { throw 'CAT1 ON interlock did not reject; do not confirm' }
    }
    Write-Output (Send-ShipCommand 'cat1_power off')
    $shipReady=Send-ShipCommand 'charger ship prepare' 4
    Write-Output $shipReady
    $shipMatch=[regex]::Match($shipReady,'\[SHIP\] state=READY token=(\d+)')
    if (!$shipMatch.Success) { throw 'No READY token; do not confirm' }
    $shipToken=$shipMatch.Groups[1].Value
    if ($Mode -eq 'Preflight') {
        $shipWrong=if($shipToken -eq '1'){'2'}else{'1'}
        $shipRefused=Send-ShipCommand ('charger ship confirm '+$shipWrong)
        Write-Output $shipRefused
        if ($shipRefused -notmatch 'confirm refused') { throw 'Wrong-token rejection failed' }
        $shipBlocked=Send-ShipCommand 'charger start'
        Write-Output $shipBlocked
        if ($shipBlocked -notmatch 'command blocked') { throw 'Ordinary command interlock failed' }
        Write-Output (Send-ShipCommand 'charger ship cancel')
        Write-Output (Send-ShipCommand 'charger ship status')
    } else {
        $shipCut=Send-ShipCommand ('charger ship confirm '+$shipToken) 17
        Write-Output $shipCut
        if ($shipCut -notmatch 'BATFET_DIS readback=1') { throw 'Cutoff write unconfirmed; inspect log and restore with 5V' }
        Write-Output 'Command accepted. SYS and battery current must be measured; serial silence is not cutoff proof.'
    }
} finally {
    [System.IO.File]::WriteAllText($shipLogPath,$shipLog)
    if($shipSerial.IsOpen){$shipSerial.Close()}
    $shipSerial.Dispose()
    Write-Output ('Log: '+$shipLogPath)
}
