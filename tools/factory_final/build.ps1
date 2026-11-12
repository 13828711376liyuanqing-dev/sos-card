# SAM | 2026-10-13 15:00 +08:00 | Offline .NET Framework/Windows SDK build
# using local assemblies; the factory PC does not need the SDK or compiler.
$ErrorActionPreference='Stop'
$ftCompiler=Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$ftFramework=Split-Path $ftCompiler
$ftMetadata=Get-ChildItem 'C:\Program Files (x86)\Windows Kits\10\UnionMetadata' -Filter Windows.winmd -Recurse | Select-Object -First 1
if(!$ftMetadata){throw 'Windows SDK union metadata not found'}
$ftRefs=@(('/reference:'+$ftMetadata.FullName),('/reference:'+ (Join-Path $ftFramework 'System.Runtime.WindowsRuntime.dll')),('/reference:'+ (Join-Path $ftFramework 'System.Runtime.InteropServices.WindowsRuntime.dll')))
foreach($ftName in @('System.Runtime','System.Threading.Tasks','System.Collections','System.ObjectModel')){
 $ftFacade=Get-ChildItem (Join-Path $env:WINDIR ('Microsoft.NET\assembly\GAC_MSIL\'+$ftName)) -Filter ($ftName+'.dll') -Recurse | Select-Object -First 1
 if(!$ftFacade){throw ('Missing local facade '+$ftName)};$ftRefs+=('/reference:'+$ftFacade.FullName)
}
Push-Location $PSScriptRoot
try{
 New-Item -ItemType Directory -Force bin | Out-Null
 & $ftCompiler /nologo /target:exe /out:bin\DesktopTests.exe Core.cs tests\DesktopTests.cs
 if($LASTEXITCODE){throw 'Host tests compile failed'}
 & .\bin\DesktopTests.exe
 if($LASTEXITCODE){throw 'Host tests failed'}
 & $ftCompiler /nologo /target:winexe /platform:x64 /out:bin\YP001FactoryFinal.exe /reference:System.Windows.Forms.dll /reference:System.Drawing.dll $ftRefs Core.cs BleLink.cs MainForm.cs
 if($LASTEXITCODE){throw 'Factory application compile failed'}
 & $ftCompiler /nologo /target:exe /platform:x64 /out:bin\BleSmoke.exe $ftRefs Core.cs BleLink.cs tests\BleSmoke.cs
 if($LASTEXITCODE){throw 'Read-only BLE smoke-test build failed'}
 Get-FileHash .\bin\YP001FactoryFinal.exe -Algorithm SHA256
}finally{Pop-Location}
