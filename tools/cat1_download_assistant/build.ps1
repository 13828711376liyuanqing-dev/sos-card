# SAM | 2026-10-15 11:10 +08:00 | Build the offline Windows download assistant after its host-only state-machine test passes.
$ErrorActionPreference = 'Stop'
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
Push-Location $PSScriptRoot
try {
    New-Item -ItemType Directory -Force bin | Out-Null
    & $compiler /nologo /target:exe /out:bin\DesktopTests.exe DownloadSession.cs tests\DesktopTests.cs
    if ($LASTEXITCODE -ne 0) { throw 'Host test build failed' }
    & .\bin\DesktopTests.exe
    if ($LASTEXITCODE -ne 0) { throw 'Host state-machine tests failed' }
    # SAM | 2026-10-15 11:47 +08:00 | Version the EXE per build because an operator may keep any previous version open during a live Luatools session.
    $output = Join-Path $PSScriptRoot ('bin\CAT1DownloadAssistant_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.exe')
    & $compiler /nologo /target:winexe /out:$output /reference:System.Windows.Forms.dll /reference:System.Drawing.dll DownloadSession.cs MainForm.cs
    if ($LASTEXITCODE -ne 0) { throw 'Application build failed' }
    Set-Content -LiteralPath .\bin\latest.txt -Value $output -Encoding ASCII
    Get-FileHash $output -Algorithm SHA256
} finally { Pop-Location }
