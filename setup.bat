@echo off
cd /d "%~dp0"

echo ============================================
echo  Install dependencies
echo ============================================
echo.

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
    echo [ERROR] Python not found.
    echo Install Python 3.10+ from https://www.python.org/downloads/
    echo Check "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

echo Using Python: %PYTHON%
"%PYTHON%" --version
echo.
echo Installing packages from requirements.txt...
"%PYTHON%" -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo [ERROR] Install failed. Check network or Python install.
    pause
    exit /b 1
)

echo.
echo Done. You can now run run.bat or build_exe.bat
echo.
pause
