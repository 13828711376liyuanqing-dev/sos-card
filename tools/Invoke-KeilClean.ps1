param([switch]$Preview, [switch]$NoPause)

# SAM | 2026-10-07 11:50 +08:00 | Replace recursive BAT deletion with bounded
# output cleanup because *.sct is a required linker input, not a temporary file.
$ErrorActionPreference = 'Stop'
# SAM | 2026-10-07 11:50 +08:00 | Explicit module loading matches the existing
# delivery tool; this Windows host does not always auto-load Get-FileHash.
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop
$workspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$projectDirs = @(
    (Join-Path $workspace 'ble_app_uart_c\Keil_6'),
    (Join-Path $workspace 'SVN交付_YP001_GR5526_20261001\ble_app_uart_c\Keil_6')
)
$temporaryExtensions = @('.o', '.obj', '.d', '.dep', '.lnp', '.crf', '.lst', '.map', '.htm')

function Assert-LocalPath([string]$Path) {
    $absolute = [IO.Path]::GetFullPath($Path)
    $prefix = $workspace.TrimEnd('\') + '\'
    if (-not $absolute.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path outside project: $absolute"
    }
    # Reject junctions/symlinks in every path component before deleting.
    $cursor = $absolute
    while ($cursor.Length -ge $workspace.Length) {
        if (Test-Path -LiteralPath $cursor) {
            if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Linked path is not allowed for cleanup: $cursor"
            }
        }
        if ($cursor -eq $workspace) { break }
        $cursor = Split-Path -Parent $cursor
    }
}

function Assert-NoBuild {
    if (Get-Process -Name armclang, armcc, armlink, armasm, fromelf -ErrorAction SilentlyContinue) {
        throw 'Compiler/linker is running. Wait for the build to finish before cleaning.'
    }
}

try {
    Assert-NoBuild
    $protected = @{}
    $candidates = @()
    # Validate BOTH projects before allowing the first deletion.
    foreach ($projectDir in $projectDirs) {
        Assert-LocalPath $projectDir
        $validator = Join-Path $projectDir '验证Keil6交付.ps1'
        Assert-LocalPath $validator
        & $validator
        foreach ($name in @('YP001_GR5526.sct', 'YP001_GR5526.uvprojx', 'ac6_debug.ini',
                             'YP001_GR5526.uvoptx', '验证Keil6交付.ps1',
                             'Objects\YP001_GR5526.axf', 'Objects\YP001_GR5526.hex')) {
            $path = Join-Path $projectDir $name
            Assert-LocalPath $path
            if (Test-Path -LiteralPath $path -PathType Leaf) {
                $protected[$path] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
            }
        }
        foreach ($folderName in @('Objects', 'Listings')) {
            $folder = Join-Path $projectDir $folderName
            Assert-LocalPath $folder
            if (Test-Path -LiteralPath $folder -PathType Container) {
                # No recursion: files elsewhere in the repository are never candidates.
                $candidates += @(Get-ChildItem -LiteralPath $folder -File -Force |
                    Where-Object { $_.Extension.ToLowerInvariant() -in $temporaryExtensions })
            }
        }
    }
    foreach ($file in $candidates) { Assert-LocalPath $file.FullName }
    Write-Output "Generated intermediate files: $($candidates.Count)"
    if ($Preview) {
        $candidates | ForEach-Object { Write-Output "WOULD REMOVE $($_.FullName)" }
    } else {
        Assert-NoBuild
        foreach ($file in $candidates) {
            Assert-LocalPath $file.FullName
            Remove-Item -LiteralPath $file.FullName -Force
        }
    }
    foreach ($path in $protected.Keys) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
            (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $protected[$path]) {
            throw "Protected file changed or missing: $path"
        }
    }
    foreach ($projectDir in $projectDirs) { & (Join-Path $projectDir '验证Keil6交付.ps1') }
    if ($Preview) { Write-Output 'Preview passed; no files removed.' }
    else { Write-Output 'Cleanup passed; required files and existing AXF/HEX preserved. Rebuild before download.' }
} catch {
    Write-Error -ErrorAction Continue $_
    exit 1
}
