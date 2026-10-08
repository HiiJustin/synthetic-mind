@echo off
cd /d "%~dp0"
title Synthetic Mind - Live Console
set SYNTHETIC_MIND_HEADLESS=
set SYNTHETIC_MIND_AUTOSTART=1
python -B tools\minecraft_setup.py start
pause
