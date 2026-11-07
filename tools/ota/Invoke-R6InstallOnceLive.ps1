param([Parameter(Mandatory=$true)][string]$CaptureSession)
# SAM | 2026-10-27 20:58 +08:00 | Reserve the explicitly approved install-only R6 request before writing; never resend after an uncertain result.
$ErrorActionPreference='Stop'
if($CaptureSession -notmatch '^\d+$'){throw 'CAPTURE_SESSION_REQUIRED'}
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../logs/r6_install_only_once_20261027'))
[IO.Directory]::CreateDirectory($root) | Out-Null
$marker=Join-Path $root 'command_reserved.json'
if(Test-Path -LiteralPath $marker){throw 'HOST_COMMAND_ALREADY_RESERVED_DO_NOT_RESEND'}
$p=[IO.Ports.SerialPort]::new('COM26',115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$p.DtrEnable=$false;$p.RtsEnable=$false;$p.WriteTimeout=1000
$timer=[Diagnostics.Stopwatch]::StartNew();$events=[Collections.Generic.List[object]]::new();$pending=''
$report=@{session=$CaptureSession;send_attempted=$false;commands_sent=0;events=$events}
try {
  $p.Open();Start-Sleep -Milliseconds 100;$null=$p.ReadExisting()
  $reservation=@{reserved_utc=[DateTime]::UtcNow.ToString('o');selector=5;job='1a092304771d1850f747237e3964fc5e071c63618f661c349494efe75e14b752';epoch=4;limit=1;capture_session=$CaptureSession;outcome='RESERVED_BEFORE_WRITE'} | ConvertTo-Json -Compress
  $f=[IO.File]::Open($marker,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
  try {$b=[Text.Encoding]::UTF8.GetBytes($reservation);$f.Write($b,0,$b.Length);$f.Flush($true)} finally {$f.Dispose()}
  $report.send_attempted=$true
  $p.Write("`rcat_at OTA_HANDOFF_RESUME=782fc7f0bca7b0ef37f67a4e633604e4,5`r`n")
  $report.commands_sent=1
  while($timer.Elapsed.TotalSeconds -lt 45){
    $pending+=$p.ReadExisting()
    while(($i=$pending.IndexOf("`n")) -ge 0){
      $line=$pending.Substring(0,$i).TrimEnd("`r");$pending=$pending.Substring($i+1)
      if(($line -match '^\[CAT1 (TX|RX|ERROR)\]|^\[(OTA|OTA_OWNER|OTA_WIRE|OTA_PORT|OTA_REJECT|FW_VERSION)\]') -and $line -notmatch 'https?://|Address|Token|password|BUS_EVT|IMEI|IMSI'){
        $events.Add(@{ms=[math]::Round($timer.Elapsed.TotalMilliseconds,2);line=$line});Write-Output $line
      }
    }
    if($pending.Length -gt 32768){$pending='';$report.host_line_overflow=$true}
    Start-Sleep -Milliseconds 25
  }
} catch {$report.error='HOST_SERIAL_EXCEPTION';Write-Output 'HOST_SERIAL_EXCEPTION'} finally {
  if($p.IsOpen){$p.Close()};$p.Dispose();$report.elapsed_ms=$timer.Elapsed.TotalMilliseconds
  $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $root 'observation.json') -Encoding UTF8
}
