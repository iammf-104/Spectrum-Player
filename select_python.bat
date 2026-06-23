@echo off
REM Only change Python without reinstalling packages (shortcut to setup.ps1)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" -SelectOnly
