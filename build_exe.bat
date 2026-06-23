@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  Mid-Low Spectrum Player — 打包 EXE
echo ============================================
echo.

REM ── 自动查找 Python ──────────────────────────
set "PYTHON="

REM 1. Windows Python 启动器（推荐）
where py >nul 2>&1 && (
    py -3 -c "import sys; print(sys.executable)" > "%TEMP%\sp_python.txt" 2>nul
    if exist "%TEMP%\sp_python.txt" (
        set /p PYTHON=<"%TEMP%\sp_python.txt"
        del "%TEMP%\sp_python.txt"
    )
)

REM 2. PATH 中的 python
if not defined PYTHON (
    where python >nul 2>&1 && set "PYTHON=python"
)

if not defined PYTHON (
    echo [错误] 未找到 Python。
    echo.
    echo 请先安装 Python 3.10 或更高版本：
    echo   https://www.python.org/downloads/
    echo.
    echo 安装时务必勾选 "Add Python to PATH"。
    echo 安装完成后，先双击 setup.bat 安装依赖，再运行本脚本。
    echo.
    pause
    exit /b 1
)

echo 使用 Python: %PYTHON%
"%PYTHON%" --version
if errorlevel 1 (
    echo [错误] Python 无法运行，请检查安装。
    pause
    exit /b 1
)
echo.

REM ── 检查依赖 ─────────────────────────────────
echo [0/4] 检查依赖...
"%PYTHON%" -c "import numpy, sounddevice, soundfile, mutagen" >nul 2>&1
if errorlevel 1 (
    echo 依赖未安装，正在自动安装（首次可能需要几分钟）...
    "%PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败。请手动运行 setup.bat 后重试。
        pause
        exit /b 1
    )
)
echo.

REM ── 安装 PyInstaller ───────────────────────────
echo [1/4] 安装 PyInstaller...
"%PYTHON%" -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo [错误] 安装 PyInstaller 失败，请检查网络连接。
    pause
    exit /b 1
)

REM ── 清理旧产物 ────────────────────────────────
echo [2/4] 清理旧的 build / dist...
if exist build   rmdir /s /q build
if exist dist    rmdir /s /q dist
if exist MidLowSpectrumPlayer.spec del /q MidLowSpectrumPlayer.spec

REM ── 运行 PyInstaller ─────────────────────────
echo [3/4] 开始打包（可能需要 1-3 分钟，请耐心等待）...
"%PYTHON%" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --windowed ^
    --name MidLowSpectrumPlayer ^
    --collect-all sounddevice ^
    --collect-all soundfile ^
    --collect-all mutagen ^
    --collect-all numpy ^
    --hidden-import windnd ^
    --hidden-import scipy.special._cdflib ^
    --hidden-import scipy.special._ufuncs ^
    --hidden-import ctypes.wintypes ^
    main_midlow.py

if errorlevel 1 (
    echo.
    echo [错误] 打包失败，请查看上方错误信息。
    pause
    exit /b 1
)

REM ── 整理输出目录 ──────────────────────────────
echo [4/4] 整理输出文件...

set DIST_DIR=dist\MidLowSpectrumPlayer

(
echo 运行说明
echo ========
echo 双击 MidLowSpectrumPlayer.exe 启动播放器。
echo.
echo music_library\   — 歌曲库，导入的音乐自动复制到此处
echo playlists.json   — 歌单数据，请随 exe 一起保存
echo.
echo 将整个文件夹复制到其他电脑即可使用，无需安装 Python。
) > "%DIST_DIR%\使用说明.txt"

echo.
echo ============================================
echo  打包完成！
echo  输出目录：%CD%\%DIST_DIR%
echo ============================================
echo.
echo 将 dist\MidLowSpectrumPlayer 整个文件夹复制到其他电脑即可运行。
echo.
pause
