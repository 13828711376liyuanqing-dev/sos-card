# SAM | 2026-10-16 +08:00 | Use installed .NET Framework compiler for an offline standalone GUI.
# SAM | 2026-10-16 17:00 +08:00 | Keep the running v1 tool intact while producing the v2 UI.
param([string]$OutputName='GR5526_SleepTest_v2.exe')
$ErrorActionPreference='Stop'
$taskCompiler=Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
Push-Location $PSScriptRoot
try {
 New-Item -ItemType Directory -Force bin | Out-Null
 $taskOutput=Join-Path 'bin' $OutputName
 & $taskCompiler /nologo /target:winexe /platform:anycpu /out:$taskOutput /reference:System.Windows.Forms.dll /reference:System.Drawing.dll MainForm.cs
 if($LASTEXITCODE -ne 0){throw 'GUI compile failed'}
 Get-FileHash $taskOutput
} finally {Pop-Location}
