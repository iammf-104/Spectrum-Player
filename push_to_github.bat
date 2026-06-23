@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  推送到 GitHub: Spectrum-Player
echo ============================================
echo.
echo 仓库地址: https://github.com/iammf-104/Spectrum-Player
echo.

git remote set-url origin https://github.com/iammf-104/Spectrum-Player.git

echo 正在推送...
git push -u origin main

if errorlevel 1 (
    echo.
    echo [推送失败] 通常是需要登录 GitHub。
    echo.
    echo 请按下面步骤操作：
    echo   1. 浏览器打开: https://github.com/settings/tokens/new
    echo   2. Note 填: Spectrum Player
    echo   3. 勾选 repo 权限
    echo   4. 点 Generate token，复制生成的 token
    echo   5. 再次运行本脚本，用户名填 iammf-104，密码粘贴 token
    echo.
) else (
    echo.
    echo 推送成功！打开: https://github.com/iammf-104/Spectrum-Player
    echo.
)

pause
