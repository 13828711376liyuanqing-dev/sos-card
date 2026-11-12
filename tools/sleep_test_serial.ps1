param([string]$Port='COM26',[ValidateSet('enter','status','exit')][string]$Action='status',[int]$ListenSeconds=10)
# SAM | 2026-10-16 10:00 +08:00 | Always close the test port because colleagues share it with other tools.
$taskSerial=[System.IO.Ports.SerialPort]::new($Port,115200,[System.IO.Ports.Parity]::None,8,[System.IO.Ports.StopBits]::One)
$taskSerial.ReadTimeout=200
try {
 $taskSerial.Open()
 $taskSerial.Write("sleep_test $Action`r`n")
 $taskDeadline=[DateTime]::UtcNow.AddSeconds($ListenSeconds)
 while([DateTime]::UtcNow -lt $taskDeadline) {
  $taskText=$taskSerial.ReadExisting()
  if($taskText){Write-Host -NoNewline $taskText}
  Start-Sleep -Milliseconds 50
 }
} finally {if($taskSerial.IsOpen){$taskSerial.Close()};$taskSerial.Dispose()}
