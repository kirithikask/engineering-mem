@echo off
title Engineering Memory - Offline Diagnostic Workstation
echo ============================================================
echo  ENGINEERING MEMORY - INDUSTRIAL DIAGNOSTIC WORKSTATION
echo  100%% OFFLINE / ZERO CLOUD DEPENDENCY
echo ============================================================

cd /d "%~dp0\.."

echo [1/3] Verifying Database and Migrations...
call ".\venv\Scripts\python.exe" ".\scripts\setup_database.py"

echo [2/3] Starting FastAPI Backend on port 8000...
start "Engineering Memory Backend" ".\venv\Scripts\python.exe" -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000

echo [3/3] Starting React Frontend Workstation on port 3000...
cd frontend
start "Engineering Memory Frontend" npm run dev

echo ============================================================
echo  Workstation available at http://localhost:3000
echo ============================================================
pause
