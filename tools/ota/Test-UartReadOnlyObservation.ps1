# SAM | 2026-10-26 +08:00 | Exercise real host parsing without serial hardware or OTA commands.
$ErrorActionPreference='Stop'
$module=Join-Path $PSScriptRoot 'UartReadOnlyObservation.ps1'
$reply='[CAT1 RX] [FW_VERSION] FW_VERSION={"component":"CAT1","product_build_version":"1.0.2","build":3,"ota_phase":"PAUSED"}'
$ack='[CAT1 TX] ok=1 code=0x0000 bytes=12 dropped=0'
if(-not(Test-Path $module)){
    $pattern='\[CAT1 RX\]\s*\[FW_VERSION\]\s*FW_VERSION=(\{[^\r\n]+\})'
    $parts=@($reply.Substring(0,50),$reply.Substring(50))
    if(-not(@($parts | Where-Object {[regex]::IsMatch($_,$pattern)}).Count)){throw 'LEGACY_SPLIT_RESPONSE_LOST'}
    throw 'OBSERVER_NOT_IMPLEMENTED'
}
. $module
$checks=0
function Assert-Result($state,$expected){
    $actual=(Get-UartObservationResult $state).reason
    if($actual -ne $expected){throw "EXPECTED_$expected`_GOT_$actual"}
    $script:checks++
}
$s=New-UartObservation
Add-UartObservationText $s ($ack+"`r`n"+$reply.Substring(0,50)) 50
Assert-Result $s 'REPLY_INCOMPLETE'
Add-UartObservationText $s ($reply.Substring(50)+"`r`n") 1500
Assert-Result $s 'OBSERVED'
if($s.events[1].elapsed_ms -ne 1500){throw 'LATE_REPLY_TIME_LOST'}
$s=New-UartObservation
Add-UartObservationText $s ($reply+"`r`n") 30
Assert-Result $s 'TX_ACK_MISSING'
$s=New-UartObservation
Add-UartObservationText $s "[CAT1 TX] ok=0 code=0x0001 bytes=12 dropped=0`r`n" 20
Assert-Result $s 'TX_FAILED'
$s=New-UartObservation
Add-UartObservationText $s ($ack+"`r`n") 20
Assert-Result $s 'REPLY_NOT_OBSERVED'
$s=New-UartObservation
Add-UartObservationText $s ($ack+"`r`n"+$reply+"`r`n"+$reply+"`r`n") 20
Assert-Result $s 'AMBIGUOUS_DUPLICATE'
$s=New-UartObservation
Add-UartObservationText $s ($ack+"`r`n"+$reply.Replace('1.0.2','1.5.0')+"`r`n") 20
Assert-Result $s 'UNEXPECTED_VERSION'
$s=New-UartObservation
Add-UartObservationText $s ($ack+"`r`n[CAT1 RX] [FW_VERSION] FW_VERSION={broken}`r`n") 20
Assert-Result $s 'MALFORMED_VERSION'
$s=New-UartObservation
Add-UartObservationText $s "unrelated secret=DO_NOT_RETAIN`r`n[CAT1 ERROR] rx_lost dropped=2 driver=0x00000002`r`n" 20
Assert-Result $s 'DEVICE_RX_ERROR'
if(($s | ConvertTo-Json -Depth 8) -match 'DO_NOT_RETAIN'){throw 'UNRELATED_DATA_RETAINED'}
Add-UartObservationText $s "[CAT1 RX] [FW_VERSION] FW_VERSION={broken}`r`n" 21
Assert-Result $s 'DEVICE_RX_ERROR'
$s=New-UartObservation
foreach($ch in ($ack+"`r`n"+$reply+"`r`n").ToCharArray()){Add-UartObservationText $s ([string]$ch) 25}
Assert-Result $s 'OBSERVED'
"PASS $checks observation cases; no device access"
