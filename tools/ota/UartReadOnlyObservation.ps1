# SAM | 2026-10-26 +08:00 | Preserve stream boundaries and TX evidence; a host deadline does not identify a firmware root cause.
function New-UartObservation {
    return @{pending='';events=[Collections.Generic.List[object]]::new();tx=[Collections.Generic.List[object]]::new();
        replies=[Collections.Generic.List[object]]::new();gr=$null;error=$null;bytes=0;lines=0}
}
function Add-UartObservationText($State,[string]$Text,[double]$ElapsedMs){
    $State.bytes+=$Text.Length
    $State.pending+=$Text
    while(($end=$State.pending.IndexOf("`n")) -ge 0){
        $line=$State.pending.Substring(0,$end).TrimEnd("`r")
        $State.pending=$State.pending.Substring($end+1)
        $State.lines++
        $entry=$null
        if($line -match '^\[CAT1 TX\] ok=(\d+) code=(0x[0-9A-Fa-f]+) bytes=(\d+) dropped=(\d+)'){
            $entry=@{kind='tx_ack';ok=[int]$Matches[1];code=$Matches[2];bytes=[int]$Matches[3];dropped=[long]$Matches[4]}
            $State.tx.Add($entry)
        }elseif($line -match '^\[CAT1 RX\]\s*\[FW_VERSION\]\s*FW_VERSION=(.*)$'){
            try{
                $v=$Matches[1] | ConvertFrom-Json -ErrorAction Stop
                # Fixed identity fields only; unsolicited user values and URLs are never persisted.
                $expected=$v.component -eq 'CAT1' -and $v.product_build_version -eq '1.0.2' -and $v.build -eq 3
                if(-not $expected -and -not $State.error){$State.error='UNEXPECTED_VERSION'}
                $entry=@{kind='cat_version';expected_identity=$expected}
                if($entry.expected_identity){$entry.component='CAT1';$entry.product='1.0.2';$entry.build=3}
                if([string]$v.ota_phase -match '^[A-Z_]{1,32}$'){$entry.phase=[string]$v.ota_phase}
                $State.replies.Add($entry)
            }catch{if(-not $State.error){$State.error='MALFORMED_VERSION'};$entry=@{kind='malformed_version';characters=$line.Length}}
        }elseif($line -match '^\[FW_VERSION\] YP001_FW\|GR5526\|[0-9.]+\|\d+\|END product=[0-9.]+ app_numeric=\d+ ota_provisioned=\d+ usb_bench_test=\d+'){
            $State.gr=$Matches[0];$entry=@{kind='gr_version';value=$State.gr}
        }elseif($line -match '^\[BAT\] raw=\d+ ADC=\d+mV BAT=\d+mV EST=\d+%'){
            $entry=@{kind='adc';value=$Matches[0]}
        }elseif($line -match '^\[CAT1 ERROR\] rx_lost dropped=(\d+) driver=(0x[0-9A-Fa-f]+)'){
            if(-not $State.error){$State.error='DEVICE_RX_ERROR'};$entry=@{kind='rx_error';dropped=[long]$Matches[1];driver=$Matches[2]}
        }elseif($line -match '^\[OTA\] UART change denied'){
            if(-not $State.error){$State.error='COMMAND_DENIED'};$entry=@{kind='command_denied'}
        }
        if($null -ne $entry){$entry.elapsed_ms=[math]::Round($ElapsedMs,3);$State.events.Add($entry)}
    }
    if($State.pending.Length -gt 8192){$State.pending='';if(-not $State.error){$State.error='HOST_LINE_LIMIT'}}
}
function Get-UartObservationResult($State){
    $reason='OBSERVED'
    if($State.error){$reason=$State.error}
    elseif($State.tx.Count -gt 1 -or $State.replies.Count -gt 1){$reason='AMBIGUOUS_DUPLICATE'}
    elseif($State.tx.Count -eq 0){$reason='TX_ACK_MISSING'}
    elseif($State.tx[0].ok -ne 1 -or $State.tx[0].code -ne '0x0000' -or $State.tx[0].bytes -ne 12){$reason='TX_FAILED'}
    elseif($State.replies.Count -eq 0){
        if($State.pending -match '\[CAT1 RX\].*\[FW_VERSION\]'){$reason='REPLY_INCOMPLETE'}else{$reason='REPLY_NOT_OBSERVED'}
    }
    return @{reason=$reason;tx_ack_count=$State.tx.Count;reply_count=$State.replies.Count;events=@($State.events.ToArray());
        received_characters=$State.bytes;complete_lines=$State.lines;partial_characters=$State.pending.Length;
        partial_is_version=($State.pending -match '\[FW_VERSION\]');
        attribution='Host timing and selected complete lines; no wire nonce, physical capture required for definitive association'}
}
