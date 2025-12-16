@echo off
REM ---------------------------------------
REM  OTMS Frontend Launcher (React)
REM ---------------------------------------

SET SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%OTMS-FastAPI\frontend"

IF NOT EXIST "node_modules" (
  echo Installing frontend dependencies...
  npm install
)

REM Set API base URL if you are not using Vite proxy (optional)
REM set VITE_API_BASE_URL=http://localhost:8000/api

npm run dev

pause
