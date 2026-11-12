@echo off
rem SAM | 2026-11-13 00:17 +08:00 | Launch the desktop meter using the existing Python installation.
cd /d "%~dp0"
start "" pythonw.exe "%~dp0c2_meter_gui.py"
