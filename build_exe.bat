@echo off
cd /d "%~dp0"

echo ============================================
echo  Mid-Low Spectrum Player - Build EXE
echo ============================================
echo.

call "%~dp0get_python.bat"
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo Run setup.bat or select_python.bat first.
    echo.
    pause
    exit /b 1
)

echo Using Python: %PYTHON%
echo To change environment, run setup.bat
echo.
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
    echo Installing dependencies...
    "%PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Run setup.bat first.
        pause
        exit /b 1
    )
)
echo.

echo [1/4] Installing PyInstaller...
"%PYTHON%" -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo [ERROR] Failed to install PyInstaller.
    pause
    exit /b 1
)

echo [2/4] Cleaning old build / dist...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist MidLowSpectrumPlayer.spec del /q MidLowSpectrumPlayer.spec

echo [3/4] Building exe (1-3 minutes)...
"%PYTHON%" -m PyInstaller --noconfirm --clean --windowed --name MidLowSpectrumPlayer --collect-all sounddevice --collect-all soundfile --collect-all mutagen --collect-all numpy --hidden-import windnd --hidden-import scipy.special._cdflib --hidden-import scipy.special._ufuncs --hidden-import ctypes.wintypes main_midlow.py

if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo [4/4] Writing readme...
set "DIST_DIR=dist\MidLowSpectrumPlayer"
(
echo Run MidLowSpectrumPlayer.exe to start the player.
echo music_library\ - imported songs
echo playlists.json - playlist data
) > "%DIST_DIR%\README.txt"

echo.
echo Build complete: %CD%\%DIST_DIR%
echo.
pause
