# SAM | 2026-10-07 11:50 +08:00 | Regression-test cleanup using disposable
# files, including required-file failure and invocation from another directory.
$ErrorActionPreference = 'Stop'
$sourceRoot = Split-Path -Parent $PSScriptRoot
$fixture = Join-Path ([IO.Path]::GetTempPath()) ('YP001 clean test ' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $fixture 'tools') -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $sourceRoot 'keilkilll.bat') -Destination $fixture
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Invoke-KeilClean.ps1') -Destination (Join-Path $fixture 'tools')
$dirs = @('ble_app_uart_c\Keil_6', 'SVN交付_YP001_GR5526_20261001\ble_app_uart_c\Keil_6')
$keep = @{}
$remove = @()
foreach ($dir in $dirs) {
    $project = Join-Path $fixture $dir
    foreach ($folder in @('Objects', 'Listings')) {
        New-Item -ItemType Directory -Path (Join-Path $project $folder) -Force | Out-Null
    }
    foreach ($name in @('YP001_GR5526.uvprojx', 'YP001_GR5526.sct', 'ac6_debug.ini', '验证Keil6交付.ps1')) {
        Copy-Item -LiteralPath (Join-Path (Join-Path $sourceRoot $dir) $name) -Destination $project
        $path = Join-Path $project $name
        $keep[$path] = (Get-FileHash -LiteralPath $path).Hash
    }
    $package = Split-Path -Parent (Split-Path -Parent $project)
    foreach ($name in @('SDK\platform\soc\linker\keil\ble_sdk.lib', 'SDK\build\keil\GR5xxx_16MB_Flash.FLM', 'SDK\keep.o')) {
        $path = Join-Path $package $name
        New-Item -ItemType Directory -Path (Split-Path -Parent $path) -Force | Out-Null
        [IO.File]::WriteAllText($path, 'protected fixture')
        $keep[$path] = (Get-FileHash -LiteralPath $path).Hash
    }
    foreach ($name in @('Objects\YP001_GR5526.axf', 'Objects\YP001_GR5526.hex',
                        'Objects\keep.sct', 'Objects\keep.c', 'Objects\keep.lib',
                        'Objects\keep.bak', 'Listings\keep.ini')) {
        $path = Join-Path $project $name
        [IO.File]::WriteAllText($path, 'protected fixture')
        $keep[$path] = (Get-FileHash -LiteralPath $path).Hash
    }
    foreach ($name in @('Objects\remove.o', 'Objects\remove.d', 'Listings\remove.lst')) {
        $path = Join-Path $project $name
        [IO.File]::WriteAllText($path, 'generated fixture')
        $remove += $path
    }
}
function Run-Clean([switch]$Preview) {
    Push-Location ([IO.Path]::GetTempPath())
    try {
        if ($Preview) { & (Join-Path $fixture 'keilkilll.bat') -NoPause -Preview | Out-Host }
        else { & (Join-Path $fixture 'keilkilll.bat') -NoPause | Out-Host }
        return $LASTEXITCODE
    } finally { Pop-Location }
}
if ((Run-Clean -Preview) -ne 0) { throw 'Preview failed' }
foreach ($path in $remove) { if (-not (Test-Path -LiteralPath $path)) { throw 'Preview deleted a file' } }
$scatter = Join-Path (Join-Path $fixture $dirs[1]) 'YP001_GR5526.sct'
Move-Item -LiteralPath $scatter -Destination ($scatter + '.held')
if ((Run-Clean) -eq 0) { throw 'Missing scatter did not block cleanup' }
foreach ($path in $remove) { if (-not (Test-Path -LiteralPath $path)) { throw 'Deleted file before validating both projects' } }
Move-Item -LiteralPath ($scatter + '.held') -Destination $scatter
if ((Run-Clean) -ne 0) { throw 'Cleanup failed' }
foreach ($path in $remove) { if (Test-Path -LiteralPath $path) { throw "Intermediate retained: $path" } }
foreach ($path in $keep.Keys) {
    if (-not (Test-Path -LiteralPath $path) -or (Get-FileHash -LiteralPath $path).Hash -ne $keep[$path]) {
        throw "Protected fixture changed: $path"
    }
}
if ((Run-Clean) -ne 0) { throw 'Repeated cleanup failed' }
Write-Output 'PASS: preview, missing-file stop-before-delete, allowed deletion, protected hashes, foreign working directory, repeated cleanup.'
Write-Output "Disposable test evidence: $fixture"
