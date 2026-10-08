@echo off
setlocal
title Synthetic Mind - Local Minecraft Server
cd /d "%~dp0"
python -B tools\minecraft_setup.py server
set "resultCode=%errorlevel%"
pause
exit /b %resultCode%
