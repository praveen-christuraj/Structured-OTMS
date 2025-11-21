@echo off
REM ---------------------------------------
REM  OTMS Launcher
REM ---------------------------------------

SET SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM If you use a virtualenv, uncomment and adjust this:
REM call "%SCRIPT_DIR%\.venv\Scripts\activate.bat"

streamlit run main_app.py

pause
