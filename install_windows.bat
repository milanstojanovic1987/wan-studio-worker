@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist logs mkdir logs
set "LOG=%~dp0logs\install.log"
>"%LOG%" echo Wan Studio install %DATE% %TIME%

echo Wan Studio installer
echo Log: %LOG%

set "PY_CMD="
py -3.12 -c "import sys; print(sys.version)" >>"%LOG%" 2>&1 && set "PY_CMD=py -3.12"
if not defined PY_CMD py -3.11 -c "import sys; print(sys.version)" >>"%LOG%" 2>&1 && set "PY_CMD=py -3.11"
if not defined PY_CMD py -3.10 -c "import sys; print(sys.version)" >>"%LOG%" 2>&1 && set "PY_CMD=py -3.10"
if not defined PY_CMD (
  echo ERROR: Install 64-bit Python 3.12 first.
  pause
  exit /b 1
)

if not exist .venv\Scripts\python.exe %PY_CMD% -m venv .venv >>"%LOG%" 2>&1
if errorlevel 1 goto failed
"%~dp0.venv\Scripts\python.exe" -m pip install --upgrade pip wheel >>"%LOG%" 2>&1
if errorlevel 1 goto failed
"%~dp0.venv\Scripts\python.exe" -m pip install -r requirements.txt >>"%LOG%" 2>&1
if errorlevel 1 goto failed
"%~dp0.venv\Scripts\python.exe" -c "import PySide6, requests; print('OK')" >>"%LOG%" 2>&1
if errorlevel 1 goto failed

echo SUCCESS. Double-click launch_windows.bat
pause
exit /b 0

:failed
echo INSTALL FAILED. See %LOG%
powershell -NoProfile -Command "Get-Content -LiteralPath '%LOG%' -Tail 30"
pause
exit /b 1
