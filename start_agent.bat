@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo Starting AI Research Agent...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_agent.ps1" %*

echo.
echo Press any key to close this window.
pause >nul
