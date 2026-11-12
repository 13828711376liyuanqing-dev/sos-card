# SAM | 2026-10-28 18:55 +08:00 | J-Link helpers used by the GR deploy skill. Read-only actions never halt; Reset is the single SYSRESETREQ used after a Keil download leaves PC in the flash-algorithm loop.
# Usage:
#   jlink.ps1 -Action Snapshot -Out <file.bin>        # read-only 1 MiB (0x200000..0x300000) + DHCSR
#   jlink.ps1 -Action Dhcsr                           # read-only DHCSR (S_HALT = bit17)
#   jlink.ps1 -Action Reset -LogDir <dir>             # halt, regs (PC), SYSRESETREQ, DHCSR
param([ValidateSet('Snapshot','Dhcsr','Reset')][string]$Action,[string]$Out,[string]$LogDir)
$jl='C:\Program Files\SEGGER\JLink\JLink.exe'
$tmp=Join-Path $env:TEMP ("yp_jlink_{0}.jlink" -f $PID)
switch($Action){
  'Snapshot' { "savebin $Out,0x200000,0x100000`nmem32 0xE000EDF0,1`nexit" | Set-Content -Encoding ascii $tmp }
  'Dhcsr'    { "mem32 0xE000EDF0,1`nexit" | Set-Content -Encoding ascii $tmp }
  'Reset'    { "mem32 0xE000EDF0,1`nh`nregs`nw4 0xE000ED0C 0x05FA0004`nsleep 2000`nmem32 0xE000EDF0,1`nexit" | Set-Content -Encoding ascii $tmp }
}
$o=& $jl -NoGui 1 -ExitOnError 1 -device CORTEX-M4 -if SWD -speed 4000 -autoconnect 1 -CommandFile $tmp 2>&1
if($LogDir){ $o | Set-Content (Join-Path $LogDir "jlink_$Action.log") }
$o | Select-String 'VTref|E000EDF0|^PC =|Error|Could not'
Remove-Item $tmp -ErrorAction SilentlyContinue
