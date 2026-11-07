param(
    [Parameter(Mandatory=$true)][string]$EvidenceDirectory,
    [string]$Port='COM26',
    [ValidateRange(1,20)][int]$Count=5,
    [ValidateRange(2,10)][int]$ObservationSeconds=5
)
# SAM | 2026-10-26 +08:00 | Single-flight parsing retains TX ACK and timestamps; no OTA commands or retries.
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'UartReadOnlyObservation.ps1')
$evidenceRoot=[IO.Path]::GetFullPath($EvidenceDirectory)
$initialEvidence=Get-Content -LiteralPath (Join-Path $evidenceRoot 'decoded_evidence.json') -Raw | ConvertFrom-Json
if(-not $initialEvidence.device_image_matches_new_symbols){throw 'NEW_INSTALLED_IMAGE_NOT_VERIFIED'}
$reportPath=Join-Path $evidenceRoot 'uart_readonly_check_v2.json'
if(Test-Path -LiteralPath $reportPath){throw 'PRESERVE_PRIOR_UART_CHECK'}
$serial=[IO.Ports.SerialPort]::new($Port,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$serial.DtrEnable=$false;$serial.RtsEnable=$false;$serial.WriteTimeout=1000
$timer=[Diagnostics.Stopwatch]::StartNew()
$report=@{schema=2;started_utc=[DateTime]::UtcNow.ToString('o');requested=$Count;observations=@();
    observation_seconds=$ObservationSeconds;ota_commands_sent=0;power_commands_sent=0;
    meaning='Diagnostic observation deadline, not a validated firmware response-time requirement';failed=$false}
function Read-Observation($State,[double]$Seconds){
    $until=$timer.Elapsed.TotalSeconds+$Seconds
    while($timer.Elapsed.TotalSeconds -lt $until){
        Add-UartObservationText $State $serial.ReadExisting() $timer.Elapsed.TotalMilliseconds
        Start-Sleep -Milliseconds 20
    }
}
$active=$null
try{
    $serial.Open();Start-Sleep -Milliseconds 250
    $baseline=New-UartObservation
    Read-Observation $baseline 0.5
    $serial.Write("`rfw_version`r`n")
    Read-Observation $baseline 2
    if(-not $baseline.gr){throw 'NORMAL_GR_CLI_NOT_CONFIRMED'}
    $report.gr_cli=$baseline.gr
    for($i=1;$i -le $Count;$i++){
        # Stop on late/duplicate versions instead of attributing them to a new request.
        $settle=New-UartObservation
        Read-Observation $settle 0.3
        if($settle.tx.Count -or $settle.replies.Count -or $settle.error -or $settle.pending -match '\[FW_VERSION\]'){
            $report.late_observation=Get-UartObservationResult $settle
            throw 'STALE_OR_LATE_RESPONSE'
        }
        $active=New-UartObservation
        $sent=$timer.Elapsed.TotalMilliseconds
        $serial.Write("`rcat_at FW_VERSION`r`n")
        Read-Observation $active $ObservationSeconds
        $result=Get-UartObservationResult $active
        $result.index=$i;$result.sent_ms=$sent
        $report.observations+=@($result)
        if($result.reason -ne 'OBSERVED'){throw $result.reason}
        $active=$null
    }
}catch{
    $report.failed=$true
    $reason=$_.Exception.Message
    $report.reason=if($reason -match '^[A-Z0-9_]+$'){$reason}else{'HOST_SERIAL_EXCEPTION'}
    if($null -ne $active){$report.final_observation=Get-UartObservationResult $active}
}finally{
    if($serial.IsOpen){$serial.Close()};$serial.Dispose()
    $report.elapsed_ms=$timer.Elapsed.TotalMilliseconds
    $report | ConvertTo-Json -Depth 10 | Set-Content -Encoding utf8 -LiteralPath $reportPath
}
@{failed=$report.failed;reason=$report.reason;completed=@($report.observations | Where-Object {$_.reason -eq 'OBSERVED'}).Count;report=$reportPath;ota_commands_sent=0} | ConvertTo-Json
if($report.failed){throw $report.reason}
