@echo off
title Engineering Memory - Shutdown

echo Stopping Engineering Memory services...
taskkill /IM cloudflared.exe /F >nul 2>&1
echo   - public tunnel stopped
taskkill /IM llama-server.exe /F >nul 2>&1
echo   - inference runners stopped
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":8000 .*LISTENING"') do taskkill /PID %%P /F >nul 2>&1
echo   - app server stopped (port 8000)

choice /C YN /M "Also stop Ollama (the model)"
if errorlevel 2 (
    echo   - Ollama left running
) else (
    taskkill /IM ollama.exe /F >nul 2>&1
    taskkill /IM "ollama app.exe" /F >nul 2>&1
    echo   - Ollama stopped
)
echo Done.
pause
