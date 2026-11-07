param([int]$ObserveSeconds=25,[Parameter(Mandatory=$true)][string]$CaptureSession)
# SAM | 2026-10-26 +08:00 | Execute the user's one exact release-deadline R6 recovery; a durable host marker forbids blind resend after lost ACK.
$ErrorActionPreference='Stop'
$root=Join-Path $PSScriptRoot '../../logs/r6_release_deadline_20261026/live'
$root=[IO.Path]::GetFullPath($root)
$marker=Join-Path $root 'command_reserved.json'
if(Test-Path -LiteralPath $marker){throw 'HOST_COMMAND_ALREADY_RESERVED_DO_NOT_RESEND'}
$identity=Get-Content -LiteralPath (Join-Path $root 'generated_identity.json') -Raw | ConvertFrom-Json
$preflight=Get-Content -LiteralPath (Join-Path $root 'preflight.json') -Raw | ConvertFrom-Json
if(-not $identity.generated_file_matches -or -not $preflight.rail_ack){throw 'PREFLIGHT_NOT_CONFIRMED'}
$authorization=Get-Content -LiteralPath (Join-Path $root 'authorization.json') -Raw | ConvertFrom-Json
if(-not $authorization.approved -or -not $authorization.download_confirmed -or $authorization.selector -ne 3 -or $authorization.additional_attempt_limit -ne 1){throw 'EXACT_SINGLE_AUTHORIZATION_MISSING'}
if($CaptureSession -notmatch '^[0-9]+$'){throw 'CAPTURE_SESSION_REQUIRED'}
$serial=[IO.Ports.SerialPort]::new('COM26',115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$serial.DtrEnable=$false;$serial.RtsEnable=$false;$serial.WriteTimeout=1000
$events=[Collections.Generic.List[object]]::new();$pending='';$timer=[Diagnostics.Stopwatch]::StartNew()
$report=@{started_utc=[DateTime]::UtcNow.ToString('o');send_attempted=$false;commands_sent=0;events=$events}
try{
    $serial.Open();Start-Sleep -Milliseconds 250;$serial.ReadExisting() | Out-Null
    @{reserved_utc=[DateTime]::UtcNow.ToString('o');selector=3;job='1a092304771d1850f747237e3964fc5e071c63618f661c349494efe75e14b752';epoch=4;
      limit=1;capture_session=$CaptureSession;outcome='RESERVED_BEFORE_WRITE'} | ConvertTo-Json | ForEach-Object {
        $bytes=[Text.Encoding]::UTF8.GetBytes($_);$file=[IO.File]::Open($marker,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
        try{$file.Write($bytes,0,$bytes.Length);$file.Flush()}finally{$file.Dispose()}
    }
    $report.send_attempted=$true
    $serial.Write("`rcat_at OTA_HANDOFF_RESUME=782fc7f0bca7b0ef37f67a4e633604e4,3`r`n")
    $report.commands_sent=1
    while($timer.Elapsed.TotalSeconds -lt $ObserveSeconds){
        $pending+=$serial.ReadExisting()
        while(($n=$pending.IndexOf("`n")) -ge 0){
            $line=$pending.Substring(0,$n).TrimEnd("`r");$pending=$pending.Substring($n+1)
            # Keep only bounded internal diagnostics; never persist arbitrary business payloads, user values or authenticated URLs.
            if($line -match '^\[CAT1 TX\] ok=\d+ code=0x[0-9A-Fa-f]+ bytes=\d+ dropped=\d+' -or
               $line -match '^\[CAT1 RX\] \[OTA_HANDOFF_RESUME\]\s+OTA_HANDOFF_RESUME=[A-Z0-9_]+$' -or
               $line -match '^\[CAT1 ERROR\] rx_lost dropped=\d+ driver=0x[0-9A-Fa-f]+' -or
               ($line -match '^\[(OTA|OTA_OWNER|OTA_WIRE|OTA_PORT|OTA_REJECT|CAT1 POWER|FW_VERSION)\]' -and $line -notmatch 'https?://|Address|Token|password|BUS_EVT|IMEI|imsi')){
                $entry=@{ms=[math]::Round($timer.Elapsed.TotalMilliseconds,3);line=$line}
                $events.Add($entry);Write-Output $line
            }
        }
        if($pending.Length -gt 32768){$pending='';$report.host_line_overflow=$true}
        Start-Sleep -Milliseconds 20
    }
}catch{
    $report.host_error=if($_.Exception.Message -match '^[A-Z0-9_]+$'){$_.Exception.Message}else{'HOST_SERIAL_EXCEPTION'}
    Write-Output $report.host_error
}finally{
    if($serial.IsOpen){$serial.Close()};$serial.Dispose()
    $report.elapsed_ms=$timer.Elapsed.TotalMilliseconds
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $root 'one_shot_observation.json') -Encoding utf8
}
