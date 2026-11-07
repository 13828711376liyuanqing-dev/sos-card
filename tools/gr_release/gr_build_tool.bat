@echo off
rem SAM | 2026-10-29 12:34 +08:00 | Double-click wrapper for gr_build_tool.py; default action is the read-only check.
set PY=C:\Users\SamLi\AppData\Local\Programs\Python\Python312\python.exe
if "%~1"=="" (set ARGS=check) else (set ARGS=%*)
"%PY%" "%~dp0gr_build_tool.py" %ARGS%
pause
