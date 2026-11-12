# SAM | 2026-10-28 18:55 +08:00 | GR CLI helper on COM26 (115200 8N1, CRLF). Sends each command and captures everything for WaitMs. CAT1 passthrough replies (`cat_at ...`) need ~8000 ms.
# Usage: gr_cli.ps1 -Commands 'fw_version','business status' [-WaitMs 3000] [-Log file] [-Port COM26]
param([string[]]$Commands=@('fw_version'),[int]$WaitMs=3000,[string]$Log,[string]$Port='COM26')
$p=[IO.Ports.SerialPort]::new($Port,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$p.NewLine="`r`n";$p.ReadTimeout=200;$p.Open()
$sb=[Text.StringBuilder]::new()
try{
  Start-Sleep -Milliseconds 300;[void]$sb.Append($p.ReadExisting())
  foreach($c in $Commands){
    [void]$sb.Append("`n>>> $c`n");$p.Write("$c`r`n")
    $end=[DateTime]::Now.AddMilliseconds($WaitMs)
    while([DateTime]::Now -lt $end){Start-Sleep -Milliseconds 100;[void]$sb.Append($p.ReadExisting())}
  }
}finally{$p.Close()}
$out=$sb.ToString();if($Log){$out|Set-Content -Encoding utf8 $Log};$out
