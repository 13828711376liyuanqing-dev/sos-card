# SAM | 2026-10-22 +08:00 | Build and test a self-contained Windows/.NET operator folder without personal Python paths.
param([switch]$TestNative,[string]$LuatoolsRoot='D:\Installers',[string]$ExeName='YP001OtaPackager.exe')
$ErrorActionPreference='Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$compiler=Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
$taskOut=Join-Path $taskRoot 'OTA_Packager'
$taskLogs=Join-Path $taskRoot 'logs/portable_packager_build'
New-Item -ItemType Directory -Force -Path $taskOut,$taskLogs | Out-Null
$core=Join-Path $PSScriptRoot 'PackCore.cs'
$native=Join-Path $PSScriptRoot 'Cat1Native.cs'
$device=Join-Path $PSScriptRoot 'DeviceSpace.cs'
$signing=Join-Path $PSScriptRoot 'BundleSigning.cs'
$identity=Join-Path $PSScriptRoot 'FirmwareIdentity.cs'
$stored=Join-Path $PSScriptRoot 'StoredZipWriter.cs'
# SAM | 2026-10-23 +08:00 | Native GR CNG/PSS signing is part of GUI and CLI builds.
$grNative=Join-Path $PSScriptRoot 'GrProjectNative.cs'
$tests=Join-Path $PSScriptRoot 'CoreTests.cs'
$form=Join-Path $PSScriptRoot 'MainForm.cs'
$testExe=Join-Path $taskLogs 'CoreTests.exe'
& $compiler /nologo /codepage:65001 /target:exe "/out:$testExe" /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll /reference:System.Web.Extensions.dll /reference:System.Numerics.dll $core $native $device $signing $identity $stored $grNative $tests
if($LASTEXITCODE -ne 0){throw 'Core test build failed'}
Push-Location $taskRoot
try { & $testExe; if($LASTEXITCODE -ne 0){throw 'Core capacity test failed'} } finally { Pop-Location }
# SAM | 2026-10-24 +08:00 | Installation generation is separate from offline archives; every build must reject incomplete admission records.
$admissionTest=Join-Path $taskLogs 'InstallAdmissionTests.exe'
& $compiler /nologo /codepage:65001 /target:exe "/out:$admissionTest" /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll /reference:System.Web.Extensions.dll /reference:System.Numerics.dll $core $native $signing $identity $stored $grNative (Join-Path $PSScriptRoot 'InstallAdmissionTests.cs')
if($LASTEXITCODE -ne 0){throw 'Installation admission test build failed'}
& $admissionTest
if($LASTEXITCODE -ne 0){throw 'Installation admission tests failed'}
# SAM | 2026-10-22 +08:00 | Verify signing with temporary test identities; persistent operator keys are initialized separately.
$signTests=Join-Path $PSScriptRoot 'SigningTests.cs'
$signExe=Join-Path $taskLogs 'SigningTests.exe'
& $compiler /nologo /codepage:65001 /target:exe "/out:$signExe" /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll /reference:System.Web.Extensions.dll /reference:System.Numerics.dll $core $native $signing $identity $stored $grNative $signTests
if($LASTEXITCODE -ne 0){throw 'Signing test build failed'}
Push-Location $taskRoot
try { & $signExe; if($LASTEXITCODE -ne 0){throw 'Signing tests failed'} } finally { Pop-Location }
$grTests=Join-Path $PSScriptRoot 'GrProjectNativeTests.cs'
$grTestExe=Join-Path $taskLogs 'GrProjectNativeTests.exe'
& $compiler /nologo /codepage:65001 /target:exe "/out:$grTestExe" /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll /reference:System.Web.Extensions.dll /reference:System.Numerics.dll $core $native $signing $identity $stored $grNative $grTests
if($LASTEXITCODE -ne 0){throw 'GR native signing test build failed'}
Push-Location $taskRoot
try { & $grTestExe; if($LASTEXITCODE -ne 0){throw 'GR native signing tests failed'} } finally { Pop-Location }
$releaseSource=Join-Path $PSScriptRoot 'ReleaseCli.cs'
# SAM | 2026-10-24 +08:00 | Regress the observed Luatools 23-byte filename limit on every packager build.
$taskNameTest=Join-Path $taskLogs 'ScriptNameTests.exe'
& $compiler /nologo /codepage:65001 /target:exe "/out:$taskNameTest" /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll /reference:System.Web.Extensions.dll /reference:System.Numerics.dll $core $native $signing $identity $stored $grNative (Join-Path $PSScriptRoot 'ScriptNameTests.cs')
if($LASTEXITCODE -ne 0){throw 'Script name test build failed'}
& $taskNameTest
if($LASTEXITCODE -ne 0){throw 'Script name test failed'}
$releaseExe=Join-Path $taskLogs 'ReleaseCli.exe'
# SAM | 2026-10-24 +08:00 | Prevent the capacity fix from excluding a referenced legacy installer or changing an uncontrolled project.
$selectionExe=Join-Path $taskLogs 'RuntimeSelectionTests.exe'
& $compiler /nologo /codepage:65001 /target:exe "/out:$selectionExe" /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll /reference:System.Web.Extensions.dll /reference:System.Numerics.dll $core $native $signing $identity $stored $grNative (Join-Path $PSScriptRoot 'RuntimeSelectionTests.cs')
if($LASTEXITCODE -ne 0){throw 'Runtime selection test build failed'}
& $selectionExe
if($LASTEXITCODE -ne 0){throw 'Runtime selection tests failed'}
& $compiler /nologo /codepage:65001 /target:exe "/out:$releaseExe" /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll /reference:System.Web.Extensions.dll /reference:System.Numerics.dll $core $native $signing $identity $stored $grNative $releaseSource
if($LASTEXITCODE -ne 0){throw 'Release CLI build failed'}
$exe=Join-Path $taskOut $ExeName
& $compiler /nologo /codepage:65001 /target:winexe "/out:$exe" /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll /reference:System.Web.Extensions.dll /reference:System.Numerics.dll $core $native $device $signing $identity $stored $grNative $form
if($LASTEXITCODE -ne 0){throw 'GUI build failed'}
$preview=Join-Path $taskLogs 'startup_preview.png'
$process=Start-Process -FilePath $exe -ArgumentList @('--startup-check',('"'+$preview+'"')) -WindowStyle Hidden -PassThru
if(-not $process.WaitForExit(15000)){$process.Kill();throw 'GUI startup check timed out'}
$process.Refresh()
if($process.ExitCode -ne 0){throw 'GUI startup failed; inspect startup_error.log'}
# SAM | 2026-10-22 11:35 +08:00 | Optional vendor round trip is host-only; failures are logged without application crash dialogs.
if($TestNative){
 $nativeTests=Join-Path $PSScriptRoot 'NativeTests.cs'
 $nativeExe=Join-Path $taskLogs 'NativeTests.exe'
 & $compiler /nologo /codepage:65001 /target:exe "/out:$nativeExe" /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll /reference:System.Web.Extensions.dll /reference:System.Numerics.dll $core $native $signing $identity $stored $grNative $nativeTests
 if($LASTEXITCODE -ne 0){throw 'Native test build failed'}
 Push-Location $taskRoot
 try {
  $nativeOutput=@(& $nativeExe (Join-Path $taskRoot 'Air780EGH') $LuatoolsRoot (Join-Path $taskLogs 'native_generation') 2>&1 | Tee-Object -FilePath (Join-Path $taskLogs 'native_tests.txt'))
  $nativeOutput | Write-Output
  if($LASTEXITCODE -ne 0){throw 'Native generation/readback tests failed'}
  # SAM | 2026-10-23 +08:00 | Regress sidecar tampering against this run's exact SOTA, never a newest-file guess.
  $generated=@($nativeOutput | Where-Object { "$_".StartsWith('GENERATED ') })
  if($generated.Count -ne 1){throw 'Missing exact generated SOTA path'}
  $identityTestExe=Join-Path $taskLogs 'IdentityRecordTests.exe'
  & $compiler /nologo /codepage:65001 /target:exe "/out:$identityTestExe" /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll /reference:System.Web.Extensions.dll /reference:System.Numerics.dll $core $native $signing $identity $stored $grNative (Join-Path $PSScriptRoot 'IdentityRecordTests.cs')
  if($LASTEXITCODE -ne 0){throw 'Identity record test build failed'}
  & $identityTestExe ("$($generated[0])".Substring(10)) $LuatoolsRoot (Join-Path $taskLogs 'identity_record_tests')
  if($LASTEXITCODE -ne 0){throw 'Identity record tests failed'}
 } finally {Pop-Location}
}
Get-FileHash $exe -Algorithm SHA256
