@echo off
rem SAM | 2026-10-13 +08:00 | One-click offline release check because Luatools must receive a complete bounded file set.
setlocal
set "TASK_PYTHON=C:\Users\SamLi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%TASK_PYTHON%" goto run
where py >nul 2>nul
if not errorlevel 1 goto run_py
echo BLOCKED: Python runtime not found. See doc\2026-10-13_CAT1一键发布检查工具.md
pause
exit /b 1
:run_py
py -3 "%~dp0cat1_release.py"
goto done
:run
"%TASK_PYTHON%" "%~dp0cat1_release.py"
:done
set "TASK_EXIT=%ERRORLEVEL%"
rem SAM | 2026-10-13 09:21 +08:00 | Point failure diagnostics to the project-local release folder because operators use Air780EGH only.
if not "%TASK_EXIT%"=="0" echo BLOCKED: No new release published. Read Air780EGH\_luatools_release\last_run.json
pause
exit /b %TASK_EXIT%
