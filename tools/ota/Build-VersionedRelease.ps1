# SAM | 2026-10-22 +08:00 | UTF-8 BOM is required because Windows PowerShell 5.1 must decode the Chinese delivery path correctly.
# SAM | 2026-10-24 +08:00 | Build only the main GR project and CAT1; the user canceled automatic delivery synchronization/builds. Never flash.
param([Parameter(Mandatory=$true)][string]$Version,[string]$LuatoolsRoot='D:\Installers',[string]$Keil='C:\Keil_v5\UV4\UV4.exe')
$ErrorActionPreference='Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if($Version -notmatch '^(0|[1-9][0-9]{0,2})\.(0|[1-9][0-9]{0,2})\.(0|[1-9][0-9]{0,2})$'){throw 'Use a three-part product version, such as 1.0.1'}
$taskReleaseRoot=Join-Path $taskRoot 'firmware_releases'
$taskFinal=Join-Path $taskReleaseRoot $Version
if(Test-Path -LiteralPath $taskFinal){throw "Release already exists; no overwrite: $taskFinal"}
$taskMeta=Join-Path $taskRoot 'firmware_version.json'
if(!(Test-Path -LiteralPath $taskMeta) -or (Get-Content -LiteralPath $taskMeta -Raw|ConvertFrom-Json).release_version -ne $Version){& (Join-Path $PSScriptRoot 'Set-FirmwareVersion.ps1') -Version $Version}
$taskRecord=Get-Content -LiteralPath $taskMeta -Raw|ConvertFrom-Json
$taskCli=Join-Path $taskRoot 'logs/portable_packager_build/ReleaseCli.exe'
if(!(Test-Path -LiteralPath $taskCli)){
 # SAM | 2026-10-22 +08:00 | A fresh project copy must be able to prepare releases without a personal cached helper or rebuilding a running GUI.
 New-Item -ItemType Directory -Path (Split-Path $taskCli -Parent) -Force|Out-Null
 $taskCompiler=Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
 $taskSources=@('PackCore.cs','Cat1Native.cs','BundleSigning.cs','FirmwareIdentity.cs','StoredZipWriter.cs','GrProjectNative.cs','ReleaseCli.cs')|ForEach-Object {(Resolve-Path (Join-Path $PSScriptRoot ('portable/'+$_))).Path}
 & $taskCompiler /nologo /codepage:65001 /target:exe "/out:$taskCli" /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll /reference:System.Web.Extensions.dll /reference:System.Numerics.dll $taskSources
 if($LASTEXITCODE -ne 0){throw 'Release helper compilation failed'}
}
$taskStage=Join-Path $taskReleaseRoot ('_building_'+$Version+'_'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $taskStage -Force|Out-Null
$taskArtifacts=@()
foreach($taskPair in @(@{name='GR5526';tree='ble_app_uart_c'})){
 $taskTree=Join-Path $taskRoot $taskPair.tree
 # SAM | 2026-10-24 +08:00 | Do not inspect, compare, copy or build any delivery checkout as a release precondition.
 $taskFolder=Join-Path $taskStage $taskPair.name
 New-Item -ItemType Directory -Path $taskFolder -Force|Out-Null
 $taskProject=Join-Path $taskTree 'Keil_6/YP001_GR5526.uvprojx'
 $taskLog=Join-Path $taskFolder 'build.log'
 Write-Output "Building $($taskPair.name) product=$Version component=$($taskRecord.component_version) build=$($taskRecord.gr_build)"
 $taskArguments=@('-b',('"'+$taskProject+'"'),'-t','"YP001_GR5526_AC6"','-j0','-o',('"'+$taskLog+'"'))
 $taskProcess=Start-Process -FilePath $Keil -ArgumentList $taskArguments -WindowStyle Hidden -PassThru
 if(!$taskProcess.WaitForExit(900000)){throw 'Keil timeout; release remains in _building and is not ready'}
 $taskProcess.Refresh();if($taskProcess.ExitCode -ne 0){throw "Keil failed: exit $($taskProcess.ExitCode), $taskLog"}
 $taskLogText=Get-Content -LiteralPath $taskLog -Raw
 if($taskLogText -notmatch '0 Error\(s\), 0 Warning\(s\)'){throw "Build did not report zero errors and warnings: $taskLog"}
 foreach($taskExtension in @('hex','axf')){
  $taskInput=Join-Path $taskTree ('Keil_6/Objects/YP001_GR5526.'+$taskExtension)
  if(!(Test-Path -LiteralPath $taskInput)){throw "Missing newly built artifact: $taskInput"}
  Copy-Item -LiteralPath $taskInput -Destination $taskFolder
 }
 $taskInfoText=& $taskCli gr (Join-Path $taskFolder 'YP001_GR5526.hex')
 if($LASTEXITCODE -ne 0){throw 'GR identity/capacity validation failed'}
 $taskInfo=$taskInfoText|ConvertFrom-Json
 if($taskInfo.version -ne $taskRecord.component_version -or $taskInfo.build -ne $taskRecord.gr_build){throw 'Compiled GR version does not match release control'}
 Copy-Item -LiteralPath (Join-Path $taskTree 'Src/config/yp001_fw_version.h') -Destination $taskFolder
 $taskArtifacts+=@{component=$taskPair.name;version=$taskInfo.version;build=$taskInfo.build;bytes=$taskInfo.bytes;sha256=$taskInfo.sha256;hex=($taskPair.name+'/YP001_GR5526.hex')}
}
$taskCatFolder=Join-Path $taskStage 'CAT1'
Write-Output "Generating native CAT1 SOTA product=$Version"
$taskCatText=& $taskCli cat1 (Join-Path $taskRoot 'Air780EGH') $LuatoolsRoot $taskCatFolder
if($LASTEXITCODE -ne 0){throw 'CAT1 native generation failed'}
$taskCat=$taskCatText|ConvertFrom-Json
if($taskCat.version -ne $taskRecord.component_version){throw 'CAT1 version does not match release control'}
$taskArtifacts+=@{component='CAT1';version=$taskCat.version;sha256=$taskCat.sha256;bytes=$taskCat.bytes;script_bytes=$taskCat.script_bytes;sota=('CAT1/'+[IO.Path]::GetFileName($taskCat.file))}
Copy-Item -LiteralPath (Join-Path $taskRoot 'Air780EGH/main.lua') -Destination (Join-Path $taskCatFolder 'main_version_source.lua')
$taskCatReport=Get-Content -LiteralPath ($taskCat.file+'.json') -Raw|ConvertFrom-Json
$taskScriptBin=Join-Path $taskCatFolder ((Split-Path $taskCatReport.vendor_log -Parent)+'/script.bin')
& $taskCli usb-scripts $taskScriptBin (Join-Path $taskCatFolder 'main_version_source.lua') (Join-Path $taskCatFolder 'luatools_precompiled')
if($LASTEXITCODE -ne 0){throw 'CAT1 USB baseline export failed'}
# SAM | 2026-10-22 +08:00 | Preserve versioned CAT1 source snapshots so later source increments cannot overwrite the baseline inputs.
$taskSourceCopy=Join-Path $taskCatFolder 'source'
New-Item -ItemType Directory -Path $taskSourceCopy -Force|Out-Null
Get-ChildItem -LiteralPath (Join-Path $taskRoot 'Air780EGH') -File | Where-Object {$_.Extension -eq '.lua' -or $_.Name -eq 'sample-6s.mp3'} | ForEach-Object {Copy-Item -LiteralPath $_.FullName -Destination $taskSourceCopy}
Copy-Item -LiteralPath $taskMeta -Destination (Join-Path $taskStage 'firmware_version.json')
$taskSummary=[ordered]@{schema=1;product='YP001';release_version=$Version;component_version=$taskRecord.component_version;gr_build=$taskRecord.gr_build;artifacts=$taskArtifacts;device_installed=$false;device_ota_verified=$false;generated_at=[DateTimeOffset]::Now.ToString('o');boundary='Built and capacity/identity checked only. No flash, no device install approval.'}
$taskSummary|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $taskStage 'release.json') -Encoding utf8
Move-Item -LiteralPath $taskStage -Destination $taskFinal
$taskActive=Get-Content -LiteralPath $taskMeta -Raw|ConvertFrom-Json
if($taskActive.release_version -eq $Version -and $taskActive.gr_build -eq $taskRecord.gr_build){
 $taskActive.source='BUILT_RELEASE_AVAILABLE_NOT_FLASHED'
 $taskActive|Add-Member -NotePropertyName built_release -NotePropertyValue ('firmware_releases/'+$Version) -Force
 $taskActive|Add-Member -NotePropertyName device_version -NotePropertyValue 'UNKNOWN_UNTIL_DEVICE_READ' -Force
 [IO.File]::WriteAllText($taskMeta,($taskActive|ConvertTo-Json),(New-Object Text.UTF8Encoding($false)))
}
Write-Output "RELEASE_READY: $taskFinal (not flashed)"
