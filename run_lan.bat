@echo off
REM Double-click to start the scoring server on the LAN.
REM Uses the project's .venv if it exists, otherwise the system Python.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" run_lan.py %*
) else (
  python run_lan.py %*
)
pause
