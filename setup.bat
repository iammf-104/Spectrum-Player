@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  安装播放器依赖
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
    echo [错误] 未找到 Python。
    echo.
    echo 请先安装 Python 3.10+： https://www.python.org/downloads/
    echo 安装时勾选 "Add Python to PATH"。
    echo.
    pause
    exit /b 1
)

echo 使用 Python: %PYTHON%
"%PYTHON%" --version
echo.
echo 正在安装依赖，请稍候...
"%PYTHON%" -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo [错误] 安装失败，请检查网络或 Python 安装。
    pause
    exit /b 1
)

echo.
echo 依赖安装完成！现在可以：
echo   - 双击 run.bat       运行播放器
echo   - 双击 build_exe.bat 打包 exe
echo.
pause
