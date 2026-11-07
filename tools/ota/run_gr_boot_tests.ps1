# SAM | 2026-10-12 19:28 +08:00 | Standalone host verifier because no hardware Boot backend is approved.
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Push-Location $root
try {
    $compiler = 'D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe'
    $env:PATH = (Split-Path $compiler -Parent) + ';' + $env:PATH
    $out = 'logs/ota_impl_20261012'
    New-Item -ItemType Directory -Force $out | Out-Null
    & $compiler -std=c99 -Wall -Wextra -Werror -pedantic -Ible_app_uart_c/Src/user/ota tools/ota/test_gr_boot.c ble_app_uart_c/Src/user/ota/yp001_ota_boot.c -o "$out/test_gr_boot.exe"
    if ($LASTEXITCODE -ne 0) { throw 'Boot host compilation failed' }
    & "$out/test_gr_boot.exe" 2>&1 | Tee-Object "$out/gr_boot_host.log"
    if ($LASTEXITCODE -ne 0) { throw 'Boot host verification failed' }
} finally { Pop-Location }
