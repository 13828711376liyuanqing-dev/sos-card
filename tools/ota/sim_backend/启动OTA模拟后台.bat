@echo off
rem SAM 2026-10-21: Local test console only, no Flash/download actions.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-OtaSimulator.ps1"
pause
