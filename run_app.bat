@echo off
cd /d "%~dp0"
title Quantum Computer Simulator
echo.
echo  Quantum Computer Simulator
echo  -------------------------
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\run_local.ps1"
echo.
echo The application has stopped.
pause
