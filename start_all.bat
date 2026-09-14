@echo off
setlocal EnableDelayedExpansion
title Engineering Memory - Startup

echo ============================================================
echo   ENGINEERING MEMORY - starting all services
echo ============================================================

REM ---------- 1. Ollama (model server, port 11434) ----------
netstat -ano | findstr /R /C:":11434 .*LISTENING" >nul
if errorlevel 1 (
    echo [1/4] Starting Ollama...
    start "" /B "C:\Users\kirithka\AppData\Local\Programs\Ollama\ollama.exe" serve
    timeout /t 6 /nobreak >nul
) else (
    echo [1/4] Ollama already running.
)

REM Force correct models directory (stale OLLAMA_MODELS broke this once).
set "OLLAMA_MODELS=C:\Users\kirithka\.ollama\models"

REM Kill orphaned inference runners from previous crashes (they starve the CPU).
taskkill /IM llama-server.exe /F >nul 2>&1

curl -s -m 5 http://127.0.0.1:11434/api/tags | findstr /C:"qwen3:4b" >nul
if errorlevel 1 (
    echo [WARN] qwen3:4b NOT visible to Ollama - check models directory!
) else (
    echo [1/4] Ollama OK - qwen3:4b available.
)

REM ---------- 2. App server (FastAPI serving UI + API, port 8000) ----------
netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul
if errorlevel 1 (
    echo [2/4] Starting app server on 0.0.0.0:8000...
    start "" /B "D:\emm\em\venv\Scripts\python.exe" -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --app-dir D:\emm\em
    echo        waiting for model load (30-60 s first boot)...
    timeout /t 25 /nobreak >nul
) else (
    echo [2/4] App server already running.
)
curl -s -m 5 -o nul -w "" http://127.0.0.1:8000/api/health
echo [2/4] App server: http://127.0.0.1:8000

REM ---------- 3. Public tunnel (any network worldwide) ----------
tasklist | findstr /I "cloudflared.exe" >nul
if errorlevel 1 (
    echo [3/4] Starting public internet tunnel...
    start "" /B "D:\emm\tools\cloudflared.exe" tunnel --url http://127.0.0.1:8000 --no-autoupdate --logfile D:\emm\tunnel.log
    timeout /t 14 /nobreak >nul
) else (
    echo [3/4] Tunnel already running.
)

REM ---------- 4. Health summary + links ----------
echo.
echo ============================================================
set "PUBLIC="
for /f "tokens=1 delims=" %%U in ('findstr /R /C:"https://[a-z0-9-]*\.trycloudflare\.com" D:\emm\tunnel.log 2^>nul') do set "PUBLIC=%%U"
echo   LOCAL / LAN LINK :  http://192.168.1.34:8000
if defined PUBLIC (
    echo   PUBLIC LINK      :  !PUBLIC!
    echo                        works from ANY wifi / mobile data
) else (
    echo   PUBLIC LINK      :  not found yet - wait 10 s and re-run this file
)
echo.
echo   QR code for phones:  D:\emm\public_link_qr.png
echo   STOP everything  :  D:\emm\stop_all.bat
echo   PC must stay ON  -  it is the server.
echo ============================================================
pause
