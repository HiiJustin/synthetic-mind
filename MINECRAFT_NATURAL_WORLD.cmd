@echo off
setlocal
cd /d "%~dp0"
python -B tools\minecraft_setup.py prepare
if errorlevel 1 goto failed
python -B tools\world_profile.py
if errorlevel 1 goto failed
call MINECRAFT_START.cmd
exit /b %errorlevel%
:failed
pause
exit /b 1
