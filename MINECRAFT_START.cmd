@echo off
setlocal
title Synthetic Mind - Minecraft Laboratory
cd /d "%~dp0"
python -B tools\brain_check.py
if errorlevel 1 (
  pause
  exit /b 1
)
python -B tools\minecraft_setup.py start
set "resultCode=%errorlevel%"
echo.
echo Minecraft laboratory stopped. Your identity and memories are saved.
pause
exit /b %resultCode%
