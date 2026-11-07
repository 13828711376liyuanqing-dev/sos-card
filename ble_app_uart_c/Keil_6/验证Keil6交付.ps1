$ErrorActionPreference = 'Stop'
$projectDir = $PSScriptRoot
$packageRoot = (Resolve-Path -LiteralPath (Join-Path $projectDir '..\..')).Path
$required = @(
    (Join-Path $projectDir 'YP001_GR5526.uvprojx'),
    (Join-Path $projectDir 'YP001_GR5526.sct'),
    (Join-Path $projectDir 'ac6_debug.ini'),
    (Join-Path $packageRoot 'SDK\platform\soc\linker\keil\ble_sdk.lib'),
    (Join-Path $packageRoot 'SDK\build\keil\GR5xxx_16MB_Flash.FLM')
)
$missing = @($required | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) })
if ($missing.Count -gt 0) {
    $missing | ForEach-Object { Write-Error "Missing Keil 6 delivery file: $_" }
    exit 1
}
$project = Get-Content -LiteralPath (Join-Path $projectDir 'YP001_GR5526.uvprojx') -Raw
if ($project -notmatch '<ScatterFile>YP001_GR5526\.sct</ScatterFile>') {
    Write-Error 'Project scatter setting does not match YP001_GR5526.sct'
    exit 1
}
if ($project -notmatch '-FD20000000 -FC8000.*-FS0200000 -FL01000000') {
    Write-Error 'Project Flash algorithm RAM/Flash range differs from verified GR5526 settings'
    exit 1
}
$userOptions = Join-Path $projectDir 'YP001_GR5526.uvoptx'
if (Test-Path -LiteralPath $userOptions -PathType Leaf) {
    $options = Get-Content -LiteralPath $userOptions -Raw
    if ($options -match '-FC1000|-FS0100000') {
        Write-Error 'Local Keil Debug options still contain the 4 KB RAM or wrong Flash base setting'
        exit 1
    }
}
Write-Output "Keil 6 delivery files OK: $projectDir"
