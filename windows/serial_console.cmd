@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0serial_console.ps1"
if errorlevel 1 (
  echo.
  echo The serial console exited with an error.
  pause
)


