@echo off
rem YP001 wrap-up (ASCII only). wrapup.bat = preview; wrapup.bat --yes = sync to the colleague folder, check, then tidy
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
python "%~dp0wrapup.py" %*
pause
