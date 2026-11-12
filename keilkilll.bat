@echo off
setlocal
rem SAM | 2026-10-07 11:50 +08:00 | Clean generated intermediates only; preserve linker inputs.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\Invoke-KeilClean.ps1" %*
set "cleanExit=%errorlevel%"
if /I "%~1"=="-NoPause" exit /b %cleanExit%
pause
exit /b %cleanExit%
