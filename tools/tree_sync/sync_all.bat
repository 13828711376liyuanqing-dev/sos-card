@echo off
rem YP001 finish-the-round sync (ASCII only). sync_all.bat = preview; sync_all.bat --yes = push, verify, baseline, handoff
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
python "%~dp0sync_all.py" %*
pause
