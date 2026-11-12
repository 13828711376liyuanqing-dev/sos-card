@echo off
setlocal
rem SAM 2026-10-20 16:51 +08:00: launch the published build; do not rebuild on every retry or create confusing EXE versions.
if not exist "%~dp0bin\latest.txt" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1"
    if errorlevel 1 (
        pause
        exit /b 1
    )
)
set /p "assistantExe="<"%~dp0bin\latest.txt"
if not exist "%assistantExe%" (
    echo Published EXE missing. Run build.ps1 to restore it.
    pause
    exit /b 1
)
start "CAT1 Download Assistant" "%assistantExe%"
