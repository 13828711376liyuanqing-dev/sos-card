# SAM | 2026-10-22 +08:00 | UTF-8 BOM is required because Windows PowerShell 5.1 must decode the Chinese delivery path correctly.
# SAM | 2026-10-24 +08:00 | Set GR main and CAT1 identities only; the user canceled automatic delivery synchronization. Never patch compiled binaries.
param([Parameter(Mandatory=$true)][string]$Version,[int]$Build=0)
$ErrorActionPreference='Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if($Version -notmatch '^(0|[1-9][0-9]{0,2})\.(0|[1-9][0-9]{0,2})(?:\.(0|[1-9][0-9]{0,2}))?$'){throw 'Version must have 2 or 3 numeric parts, each 0..999'}
$taskParts=@($Version.Split('.') | ForEach-Object {[int]$_});if($taskParts.Count -eq 2){$taskParts+=0}
$taskNormal=($taskParts -join '.')
$taskCanonical=('{0:D3}.{1:D3}.{2:D3}' -f $taskParts[0],$taskParts[1],$taskParts[2])
$taskMetadata=Join-Path $taskRoot 'firmware_version.json'
$taskOld=$null
if(Test-Path -LiteralPath $taskMetadata){
 $taskOld=Get-Content -LiteralPath $taskMetadata -Raw | ConvertFrom-Json
 if([Version]$taskNormal -lt [Version]$taskOld.release_version){throw 'Controlled source version cannot go backwards'}
 if($Build -eq 0){$Build=[int]$taskOld.gr_build;if($taskNormal -ne $taskOld.release_version){$Build++}}
 if($taskNormal -ne $taskOld.release_version -and $Build -le [int]$taskOld.gr_build){throw 'A new release requires an increasing GR build counter'}
 if($taskNormal -eq $taskOld.release_version -and $Build -ne [int]$taskOld.gr_build){throw 'Same version cannot change its build identity'}
}elseif($Build -eq 0){$Build=1}
if($Build -lt 1 -or $Build -gt 65535){throw 'GR build counter must stay within 1..65535'}
$taskMain=Join-Path $taskRoot 'ble_app_uart_c'
# SAM | 2026-10-24 +08:00 | Main-only operation must also work when the independently maintained delivery tree is absent or different.
if(!(Test-Path -LiteralPath (Join-Path $taskMain 'Src/config/yp001_fw_version.h'))){throw 'Main GR version header is missing'}
$taskLua=Join-Path $taskRoot 'Air780EGH/main.lua'
$taskLuaText=[IO.File]::ReadAllText($taskLua)
$taskMatch=[regex]::Matches($taskLuaText,'(?m)^VERSION\s*=\s*"([0-9]{3}\.[0-9]{3}\.[0-9]{3})"')
if($taskMatch.Count -ne 1){throw 'main.lua VERSION is not uniquely controlled'}
if($null -ne $taskOld -and $taskMatch[0].Groups[1].Value -ne $taskOld.component_version){throw 'CAT1 source version differs from controlled metadata'}
$taskStamp=[DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(8)).ToString('yyyy-MM-dd HH:mm')
$taskHeader=@"
/* SAM | $taskStamp +08:00 | Generated release identity; use tools/ota/Set-FirmwareVersion.ps1. */
#ifndef YP001_FW_VERSION_H
#define YP001_FW_VERSION_H
#define YP001_FW_VERSION "$taskCanonical"
#define YP001_PRODUCT_VERSION "$taskNormal"
#define YP001_FW_BUILD ${Build}U
#define YP001_FW_BUILD_TEXT "$Build"
#define YP001_FW_IDENTITY "YP001_FW|GR5526|" YP001_FW_VERSION "|" YP001_FW_BUILD_TEXT "|END"
#endif
"@
$taskLuaText=[regex]::Replace($taskLuaText,'(?m)^VERSION\s*=\s*"[0-9.]+"',([System.Text.RegularExpressions.MatchEvaluator]{param($m) 'VERSION = "'+$taskCanonical+'"'}))
$taskLuaText=[regex]::Replace($taskLuaText,'(?m)^PRODUCT_VERSION\s*=\s*"[0-9.]+"',([System.Text.RegularExpressions.MatchEvaluator]{param($m) 'PRODUCT_VERSION = "'+$taskNormal+'"'}))
$taskLuaText=[regex]::Replace($taskLuaText,'(?m)^FW_RELEASE_BUILD\s*=\s*[0-9]+',([System.Text.RegularExpressions.MatchEvaluator]{param($m) 'FW_RELEASE_BUILD = '+$Build}))
# SAM | 2026-10-24 +08:00 | Stamp the generated Lua identity beside VERSION as required by the project change record, without accumulating notes.
$taskLuaText=[regex]::Replace($taskLuaText,'(?m)^-- SAM \| [^\r\n]* \| Generated source identity;[^\r\n]*\r?\n','')
$taskVersionNote="-- SAM | $taskStamp +08:00 | Generated source identity; rebuild GR main and CAT1 before use."
$taskLuaText=[regex]::Replace($taskLuaText,'(?m)^VERSION\s*=',([System.Text.RegularExpressions.MatchEvaluator]{param($m) $taskVersionNote+"`nVERSION ="}))
$taskBackup=Join-Path $taskRoot ('logs/firmware_versions/set_'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $taskBackup -Force | Out-Null
Copy-Item -LiteralPath $taskLua -Destination (Join-Path $taskBackup 'cat1_main_before.lua')
Copy-Item -LiteralPath (Join-Path $taskMain 'Src/config/yp001_fw_version.h') -Destination (Join-Path $taskBackup 'gr_version_before.h')
$taskUtf8=New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText((Join-Path $taskMain 'Src/config/yp001_fw_version.h'),$taskHeader,$taskUtf8)
[IO.File]::WriteAllText($taskLua,$taskLuaText,$taskUtf8)
$taskRecord=[ordered]@{schema=1;product='YP001';release_version=$taskNormal;component_version=$taskCanonical;gr_build=$Build;updated_local=($taskStamp+' +08:00');source='SOURCE_IDENTITY_ONLY_REBUILD_REQUIRED';main_header='ble_app_uart_c/Src/config/yp001_fw_version.h';cat1_source='Air780EGH/main.lua'}
[IO.File]::WriteAllText($taskMetadata,($taskRecord|ConvertTo-Json),$taskUtf8)
Write-Output "SOURCE VERSION SET: product=$taskNormal GR=$taskCanonical build=$Build CAT1=$taskCanonical. Rebuild main Keil project and regenerate SOTA; nothing flashed."
