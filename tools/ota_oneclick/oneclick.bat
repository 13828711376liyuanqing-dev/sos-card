@echo off
rem YP001 one-click OTA tool launcher (ASCII only). Double-click: menu.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
python "%~dp0oneclick.py" %*
pause
