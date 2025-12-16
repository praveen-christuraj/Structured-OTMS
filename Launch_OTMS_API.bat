@echo off
REM ---------------------------------------
REM  OTMS API Launcher (FastAPI)
REM ---------------------------------------

SET SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%OTMS-FastAPI\backend"

REM If you use a virtualenv, uncomment and adjust this:
REM call "%SCRIPT_DIR%OTMS-FastAPI\backend\.venv\Scripts\activate.bat"

python run_api.py

pause
