# SAM | 2026-10-24 +08:00 | Enforce main-only version/release scripts because the user canceled automatic delivery synchronization and builds.
$ErrorActionPreference='Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
foreach($taskName in @('Set-FirmwareVersion.ps1','Build-VersionedRelease.ps1')){
 $taskPath=Join-Path $PSScriptRoot $taskName
 $taskTokens=$null;$taskErrors=$null
 $taskAst=[Management.Automation.Language.Parser]::ParseFile($taskPath,[ref]$taskTokens,[ref]$taskErrors)
 if($taskErrors.Count){throw "Parse failed: $taskName"}
 $taskStrings=$taskAst.FindAll({param($node) $node -is [Management.Automation.Language.StringConstantExpressionAst] -and $node.Value.StartsWith('SVN')},$true)
 if($taskStrings.Count){throw "Forbidden delivery input: $taskName"}
 $taskText=[IO.File]::ReadAllText($taskPath)
 if($taskText -match 'taskDelivery|GR5526_delivery'){throw "Forbidden delivery operation: $taskName"}
 if($taskText -notmatch "'ble_app_uart_c'"){throw "Missing main project: $taskName"}
 if(!(Test-Path -LiteralPath (Join-Path $taskRoot 'ble_app_uart_c'))){throw 'Main project does not exist'}
 Write-Output "PASS main-only script parsing: $taskName"
}
# SAM | 2026-10-24 +08:00 | Run the setter only in a synthetic workspace; never change the real main/delivery versions during regression.
$taskFixture=Join-Path $taskRoot ('logs/ota_release_main_only_20261024/fixture_'+[Guid]::NewGuid().ToString('N'))
foreach($taskDirectory in @('tools/ota','Air780EGH','ble_app_uart_c/Src/config')){
 New-Item -ItemType Directory -Path (Join-Path $taskFixture $taskDirectory) -Force|Out-Null
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Set-FirmwareVersion.ps1') -Destination (Join-Path $taskFixture 'tools/ota/Set-FirmwareVersion.ps1')
$taskEncoding=New-Object Text.UTF8Encoding($false)
$taskLua=Join-Path $taskFixture 'Air780EGH/main.lua'
$taskHeader=Join-Path $taskFixture 'ble_app_uart_c/Src/config/yp001_fw_version.h'
[IO.File]::WriteAllText($taskLua,"VERSION = `"001.000.002`"`nPRODUCT_VERSION = `"1.0.2`"`nFW_RELEASE_BUILD = 3`n",$taskEncoding)
[IO.File]::WriteAllText($taskHeader,'fixture header before version change',$taskEncoding)
[IO.File]::WriteAllText((Join-Path $taskFixture 'firmware_version.json'),'{"release_version":"1.0.2","component_version":"001.000.002","gr_build":3}',$taskEncoding)
$taskSetter=Join-Path $taskFixture 'tools/ota/Set-FirmwareVersion.ps1'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $taskSetter -Version '1.5.0' -Build 4
if($LASTEXITCODE -ne 0){throw 'Setter failed without a delivery checkout'}
if([IO.File]::ReadAllText($taskLua) -notmatch 'VERSION = "001\.005\.000"' -or [IO.File]::ReadAllText($taskHeader) -notmatch 'YP001_FW_BUILD 4U'){throw 'Fixture version mismatch'}
$taskSentinel=Join-Path $taskFixture 'SVN_independent/user_owned.txt'
New-Item -ItemType Directory -Path (Split-Path $taskSentinel -Parent) -Force|Out-Null
[IO.File]::WriteAllText($taskSentinel,'independent delivery content',$taskEncoding)
$taskSentinelHash=(Get-FileHash -LiteralPath $taskSentinel).Hash
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $taskSetter -Version '1.5.1' -Build 5
if($LASTEXITCODE -ne 0 -or (Get-FileHash -LiteralPath $taskSentinel).Hash -ne $taskSentinelHash){throw 'Independent checkout affected version preparation'}
$taskBeforeReject=(Get-FileHash -LiteralPath $taskLua).Hash
try{
 # Expected child-process rejections arrive on stderr under Windows PowerShell 5.1.
 $ErrorActionPreference='Continue'
 $taskRejected=@(& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $taskSetter -Version '1.0.2' -Build 6 2>&1)
 if($LASTEXITCODE -eq 0 -or (Get-FileHash -LiteralPath $taskLua).Hash -ne $taskBeforeReject){throw 'Downgrade was accepted or changed source'}
 $taskRejected=@(& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $taskSetter -Version '1.5.1' -Build 6 2>&1)
 if($LASTEXITCODE -eq 0 -or (Get-FileHash -LiteralPath $taskLua).Hash -ne $taskBeforeReject){throw 'Same-version build change was accepted or changed source'}
}finally{$ErrorActionPreference='Stop'}
Write-Output 'PASS isolated main/CAT1 version updates; absent/independent delivery untouched; invalid version operations rejected'
Write-Output "FIXTURE=$taskFixture (synthetic files only; not firmware)"
