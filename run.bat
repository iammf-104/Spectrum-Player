@echo off
cd /d "%~dp0"

call "%~dp0get_python.bat"
if errorlevel 1 (
    echo [ERROR] Python not found. Run setup.bat or select_python.bat
    pause
    exit /b 1
)

"%PYTHON%" main_midlow.py
if errorlevel 1 pause
