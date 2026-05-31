@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHON_CMD="
set "TRIED_PYTHON="

call :try_python ".venv\Scripts\python.exe"
call :try_python "D:\SoftWare\Work\Python\python.exe"
call :try_python "D:\SoftWare\other\Python\python.exe"
call :try_python "python"
call :try_python "py -3"

if not defined PYTHON_CMD (
  echo.
  echo launch_desktop failed: no usable Python executable was found.
  echo Tried:
  echo %TRIED_PYTHON%
  echo.
  echo Please install Python or repair the .venv environment before starting the desktop app.
  pause
  exit /b 1
)

echo Using Python: %PYTHON_CMD%
%PYTHON_CMD% desktop_app.py
if errorlevel 1 (
  echo.
  echo launch_desktop failed. Please check the error message above.
  pause
)
exit /b %errorlevel%

:try_python
if defined PYTHON_CMD exit /b 0
set "CANDIDATE=%~1"
set "TRIED_PYTHON=%TRIED_PYTHON%  %CANDIDATE%"
if exist "%CANDIDATE%" (
  set "CANDIDATE_CMD="%CANDIDATE%""
) else (
  set "CANDIDATE_CMD=%CANDIDATE%"
)
%CANDIDATE_CMD% "--version" >nul 2>nul
if errorlevel 1 exit /b 0
set "PYTHON_CMD=%CANDIDATE_CMD%"
exit /b 0
