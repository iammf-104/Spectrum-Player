@echo off
cd /d "%~dp0"

echo Pushing to https://github.com/iammf-104/Spectrum-Player
echo.

git remote set-url origin https://github.com/iammf-104/Spectrum-Player.git
git push -u origin main

if errorlevel 1 (
    echo.
    echo Push failed. You may need a GitHub token.
    echo Create one at: https://github.com/settings/tokens/new
    echo Username: iammf-104   Password: paste your token
    echo.
) else (
    echo.
    echo Success: https://github.com/iammf-104/Spectrum-Player
    echo.
)

pause
