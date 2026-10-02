@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run install_windows.bat first.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" app.py
if errorlevel 1 pause
