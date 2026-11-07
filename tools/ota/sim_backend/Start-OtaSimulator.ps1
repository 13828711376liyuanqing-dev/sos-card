# SAM | 2026-10-21 +08:00 | Launch the loopback-only test console without device operations.
param([int]$Port = 8768)
$ErrorActionPreference = 'Stop'
$pythonPath = 'C:/Users/SamLi/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Python runtime missing. Run server.py with Python 3 and the project test dependencies installed.'
}
Write-Host "Open http://127.0.0.1:$Port after the server starts. Ctrl+C stops the server."
& $pythonPath (Join-Path $PSScriptRoot 'server.py') --port $Port
