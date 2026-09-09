@echo off
chcp 65001 >nul 2>&1
title TE102 问卷本地预览服务器
cd /d "%~dp0"

echo ========================================================
echo   TE102 助听器用户内测问卷 - 本地预览
echo ========================================================
echo.

REM 检测 Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python 3.x
    echo        下载地址: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo [信息] 正在启动本地服务器...
echo [信息] 服务器启动后将自动打开浏览器
echo [信息] 关闭本窗口或按 Ctrl+C 可停止服务器
echo.

python start_server.py

echo.
pause
