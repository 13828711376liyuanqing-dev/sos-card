@echo off
rem YP001 tree sync launcher (ASCII only). Double-click: menu. Or: sync.bat scan | baseline | push --yes | pull --yes | merge | handoff
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
python "%~dp0tree_sync.py" %*
pause
