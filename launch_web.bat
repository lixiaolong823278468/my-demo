@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" api_server.py --open-browser
) else (
  python api_server.py --open-browser
)
