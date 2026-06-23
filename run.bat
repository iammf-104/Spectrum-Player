@echo off
cd /d "%~dp0"

REM 优先使用 conda 环境的 Python（已安装 windnd 等依赖）
set CONDA_PYTHON=D:\python project\.conda\python.exe

if exist "%CONDA_PYTHON%" (
    "%CONDA_PYTHON%" main_midlow.py
) else (
    REM 回退到 PATH 中的 python
    where python >nul 2>&1 || (
        echo Python not found. Please edit run.bat to point to your Python.
        pause
        exit /b 1
    )
    python main_midlow.py
)
if errorlevel 1 pause
