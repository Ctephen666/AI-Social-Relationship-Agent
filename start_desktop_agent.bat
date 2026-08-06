@echo off
setlocal
if exist "%~dp0backend\dist\StephenAgent\StephenAgent.exe" (
  start "Stephen Agent" "%~dp0backend\dist\StephenAgent\StephenAgent.exe"
  exit /b 0
)
cd /d "%~dp0backend"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Backend virtual environment was not found.
  echo Run: python -m venv .venv
  pause
  exit /b 1
)
start "Stephen Agent" ".venv\Scripts\pythonw.exe" -m app.desktop_app
endlocal
