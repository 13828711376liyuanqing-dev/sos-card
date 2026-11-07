@echo off
rem YP001 GR5526 J-Link flash tool launcher (ASCII only). Drag a signed .bin onto this file, or double-click.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
python "%~dp0yp001_gr_jlink_flash.py" %*
pause
