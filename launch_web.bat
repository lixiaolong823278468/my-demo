@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHON_EXE=python"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" --version >nul 2>nul
  if not errorlevel 1 set "PYTHON_EXE=.venv\Scripts\python.exe"
)

"%PYTHON_EXE%" api_server.py --open-browser
if errorlevel 1 (
  echo.
  echo launch_web failed. Please check the error message above.
  pause
)
