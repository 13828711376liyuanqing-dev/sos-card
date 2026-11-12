# SAM | 2026-10-10 16:53 +08:00 | Build offline using installed .NET Framework and run protocol tests.
$ErrorActionPreference = 'Stop'
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
Push-Location $PSScriptRoot
try {
    New-Item -ItemType Directory -Force bin | Out-Null
    & $compiler /nologo /target:exe /out:bin\DesktopTests.exe Protocol.cs Journal.cs tests\DesktopTests.cs
    if ($LASTEXITCODE -ne 0) { throw 'Test build failed' }
    # SAM | 2026-10-10 20:14 +08:00 | Keep automated builds non-interactive while manual double-click tests retain their results.
    & .\bin\DesktopTests.exe --no-pause
    if ($LASTEXITCODE -ne 0) { throw 'Protocol tests failed' }
    & $compiler /nologo /target:winexe /out:bin\CAT1Antenna.exe /reference:System.Windows.Forms.dll /reference:System.Drawing.dll Protocol.cs Journal.cs MainForm.cs
    if ($LASTEXITCODE -ne 0) { throw 'Application build failed' }
    Get-FileHash .\bin\CAT1Antenna.exe -Algorithm SHA256
} finally { Pop-Location }


