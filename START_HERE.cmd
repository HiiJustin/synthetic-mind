@echo off
setlocal
title Synthetic Mind - Interactive Laboratory
call "%~dp0run.cmd" repl
set "resultCode=%errorlevel%"
if not "%resultCode%"=="0" (
    echo.
    echo Synthetic Mind stopped with an error. The message is above.
    pause
)
exit /b %resultCode%
