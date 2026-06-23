@echo off
cd /d "%~dp0"

echo ============================================
echo  Mid-Low Spectrum Player - Build EXE
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
    echo.
    echo Install Python 3.10+ from https://www.python.org/downloads/
    echo Check "Add Python to PATH" during install.
    echo Then run setup.bat first.
    echo.
    pause
    exit /b 1
)

echo Using Python: %PYTHON%
"%PYTHON%" --version
if errorlevel 1 (
    echo [ERROR] Python failed to run.
    pause
    exit /b 1
)
echo.

echo [0/4] Checking dependencies...
"%PYTHON%" -c "import numpy, sounddevice, soundfile, mutagen" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies from requirements.txt...
    "%PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies. Run setup.bat first.
        pause
        exit /b 1
    )
)
echo.

echo [1/4] Installing PyInstaller...
"%PYTHON%" -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo [ERROR] Failed to install PyInstaller. Check your network.
    pause
    exit /b 1
)

echo [2/4] Cleaning old build / dist...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist MidLowSpectrumPlayer.spec del /q MidLowSpectrumPlayer.spec

echo [3/4] Building exe (may take 1-3 minutes)...
"%PYTHON%" -m PyInstaller --noconfirm --clean --windowed --name MidLowSpectrumPlayer --collect-all sounddevice --collect-all soundfile --collect-all mutagen --collect-all numpy --hidden-import windnd --hidden-import scipy.special._cdflib --hidden-import scipy.special._ufuncs --hidden-import ctypes.wintypes main_midlow.py

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. See messages above.
    pause
    exit /b 1
)

echo [4/4] Writing readme in output folder...
set "DIST_DIR=dist\MidLowSpectrumPlayer"

(
echo Run MidLowSpectrumPlayer.exe to start the player.
echo.
echo music_library\  - imported songs are copied here
echo playlists.json  - playlist data, keep with the exe
echo.
echo Copy the whole MidLowSpectrumPlayer folder to another PC.
) > "%DIST_DIR%\README.txt"

echo.
echo ============================================
echo  Build complete!
echo  Output: %CD%\%DIST_DIR%
echo ============================================
echo.
pause
