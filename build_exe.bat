@echo off
chcp 65001 >nul
cd /d "%~dp0"

set PYTHON=D:\python project\.conda\python.exe

echo ============================================
echo  Mid-Low Spectrum Player — 打包 EXE
echo ============================================
echo.

REM ── 检查 Python ──────────────────────────────
if not exist "%PYTHON%" (
    echo [错误] 找不到 Python：%PYTHON%
    echo 请在本文件中修改 PYTHON 变量为正确路径。
    pause & exit /b 1
)

REM ── 安装 / 升级 PyInstaller ───────────────────
echo [1/4] 安装 PyInstaller...
"%PYTHON%" -m pip install --quiet --upgrade pyinstaller
if errorlevel 1 (
    echo [错误] 安装 PyInstaller 失败，请检查网络连接。
    pause & exit /b 1
)

REM ── 清理旧产物 ────────────────────────────────
echo [2/4] 清理旧的 build / dist...
if exist build   rmdir /s /q build
if exist dist    rmdir /s /q dist
if exist MidLowSpectrumPlayer.spec del /q MidLowSpectrumPlayer.spec

REM ── 运行 PyInstaller ─────────────────────────
echo [3/4] 开始打包（可能需要 1-3 分钟）...
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
    pause & exit /b 1
)

REM ── 整理输出目录 ──────────────────────────────
echo [4/4] 整理输出文件...

set DIST_DIR=dist\MidLowSpectrumPlayer

REM 写入启动说明
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
