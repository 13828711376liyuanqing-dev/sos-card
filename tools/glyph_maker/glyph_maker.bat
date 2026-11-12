@echo off
chcp 65001 >nul
cd /d "%~dp0"
python glyph_maker.py %*
if errorlevel 1 pause
