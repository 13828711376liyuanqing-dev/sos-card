@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0验证Keil6交付.ps1"
if errorlevel 1 (
  echo Keil 6 project check failed. Please fix the listed files or Flash settings.
  pause
  exit /b 1
)
set "PATH=C:\Keil_v5\ARM\Segger;%PATH%"
start "" /D "%~dp0" "C:\Keil_v5\UV4\UV4.exe" "%~dp0YP001_GR5526.uvprojx"
