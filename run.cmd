@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
python -B -m synthetic_mind %*
exit /b %errorlevel%
