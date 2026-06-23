@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON="

where py >nul 2>&1 && (
    py -3 -c "import sys; print(sys.executable)" > "%TEMP%\sp_python.txt" 2>nul
    if exist "%TEMP%\sp_python.txt" (
        set /p PYTHON=<"%TEMP%\sp_python.txt"
        del "%TEMP%\sp_python.txt"
    )
)

if not defined PYTHON (
    where python >nul 2>&1 && set "PYTHON=python"
)

if not defined PYTHON (
    echo [错误] 未找到 Python。请先安装 Python 并运行 setup.bat。
    pause
    exit /b 1
)

"%PYTHON%" main_midlow.py
if errorlevel 1 pause
