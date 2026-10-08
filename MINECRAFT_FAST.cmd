@echo off
setlocal
title Synthetic Mind - Minecraft Laboratory - Optional Fast Mode
cd /d "%~dp0"
python -B tools\brain_check.py
if errorlevel 1 (
  pause
  exit /b 1
)
python -B tools\minecraft_setup.py start --tempo fast
set "resultCode=%errorlevel%"
echo.
echo Minecraft laboratory stopped. Your identity and memories are saved.
pause
exit /b %resultCode%
