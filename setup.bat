@echo off
cd /d "%~dp0"

echo ============================================
echo  Install dependencies
echo ============================================
echo.

call "%~dp0get_python.bat"
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo Install Python 3.10+ and check "Add Python to PATH".
    echo Or run select_python.bat to choose an environment.
    echo.
    pause
    exit /b 1
)

echo Using Python: %PYTHON%
echo Default is py -3 or first python on PATH.
echo To pick another environment, run select_python.bat
echo.
"%PYTHON%" --version
echo.
echo Installing packages from requirements.txt...
"%PYTHON%" -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo [ERROR] Install failed.
    pause
    exit /b 1
)

echo.
echo Done. Run run.bat or build_exe.bat
echo.
pause
