@echo off
setlocal
cd /d "%~dp0"
python -B tools\minecraft_setup.py prepare
set "resultCode=%errorlevel%"
echo.
pause
exit /b %resultCode%
