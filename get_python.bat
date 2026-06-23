@echo off
REM Sets PYTHON to the interpreter path. Call from other .bat files:
REM   call "%~dp0get_python.bat"
REM   if errorlevel 1 ...

set "PYTHON="
set "ROOT=%~dp0"

if exist "%ROOT%.python_path" (
    set /p PYTHON=<"%ROOT%.python_path"
    if defined PYTHON if exist "%PYTHON%" goto :verify
    echo [WARN] Saved Python missing, using auto-detect...
    set "PYTHON="
)

REM Default: Windows py launcher, Python 3
where py >nul 2>&1 && (
    py -3 -c "import sys; print(sys.executable)" > "%TEMP%\sp_python.txt" 2>nul
    if exist "%TEMP%\sp_python.txt" (
        set /p PYTHON=<"%TEMP%\sp_python.txt"
        del "%TEMP%\sp_python.txt"
    )
)

REM Fallback: python on PATH
if not defined PYTHON (
    where python >nul 2>&1 && set "PYTHON=python"
)

if not defined PYTHON exit /b 1

:verify
"%PYTHON%" --version >nul 2>&1
if errorlevel 1 exit /b 1
exit /b 0
