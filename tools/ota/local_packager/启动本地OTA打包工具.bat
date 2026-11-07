@echo off
rem SAM 2026-10-22 +08:00: Compatibility entry uses schema 6 STORE bundle.
if not exist "%~dp0..\..\..\OTA_Packager\YP001OtaPackager_Bundle.exe" (
  echo Missing OTA_Packager\YP001OtaPackager_Bundle.exe
  pause
  exit /b 1
)
start "" "%~dp0..\..\..\OTA_Packager\YP001OtaPackager_Bundle.exe"
