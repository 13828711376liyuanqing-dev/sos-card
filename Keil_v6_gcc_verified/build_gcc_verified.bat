@echo off
setlocal

set "PROJECT_ROOT=D:\CODEX\sos-card"
set "TOOLCHAIN_ROOT=D:\CODEX\sos-card_toolchains\runtime"
set "PATH=%TOOLCHAIN_ROOT%\arm-gcc-xpack\xpack-arm-none-eabi-gcc-15.2.1-1.1\bin;%TOOLCHAIN_ROOT%\mingw\mingw64\bin;%PATH%"

echo [GCC verified build] Building the validated GCC project...
mingw32-make -C "%PROJECT_ROOT%\ble_app_uart_c\GCC" all
if errorlevel 1 goto :fail

copy /y "%PROJECT_ROOT%\ble_app_uart_c\GCC\out\ble_app_uart_c.hex" "%~dp0Objects\ble_app_uart_c.hex" >nul
if errorlevel 1 goto :fail
copy /y "%PROJECT_ROOT%\ble_app_uart_c\GCC\out\ble_app_uart_c.bin" "%~dp0Listings\ble_app_uart_c.bin" >nul
if errorlevel 1 goto :fail

fc /b "%PROJECT_ROOT%\ble_app_uart_c\GCC\out\ble_app_uart_c.hex" "%~dp0Objects\ble_app_uart_c.hex" >nul
if errorlevel 1 goto :fail

echo [GCC verified build] Keil Objects\ble_app_uart_c.hex is byte-identical to the GCC HEX.
exit /b 0

:fail
set "BUILD_RC=%ERRORLEVEL%"
echo [GCC verified build] FAILED. Keil delivery HEX was not replaced.
exit /b %BUILD_RC%
