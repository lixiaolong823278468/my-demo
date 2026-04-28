@echo off
cd /d "%~dp0"
pyinstaller -F -w desktop_app.py --name dayahead_predictor_desktop
