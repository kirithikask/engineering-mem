# Engineering Memory One-Command Startup Script (Offline Platform)
# Launches Local FastAPI Backend & React Frontend Workstation

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " ENGINEERING MEMORY - INDUSTRIAL DIAGNOSTIC WORKSTATION" -ForegroundColor Yellow
Write-Host " Preserving Industrial Knowledge for Faster Maintenance" -ForegroundColor DarkGray
Write-Host " 100% OFFLINE / ZERO CLOUD DEPENDENCY" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan

$RootPath = Resolve-Path "$PSScriptRoot\.."
Set-Location $RootPath

# 1. Verify Local Ollama Service
Write-Host "`n[1/4] Checking Local Ollama AI Engine..." -ForegroundColor White
try {
    $OllamaCheck = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get -TimeoutSec 2
    Write-Host "  -> Ollama is online with local models." -ForegroundColor Green
} catch {
    Write-Host "  -> Warning: Ollama not detected at http://localhost:11434. Diagnostic engine will use evidence-grounded fallback." -ForegroundColor Yellow
}

# 2. Verify Database
Write-Host "`n[2/4] Verifying Local Database..." -ForegroundColor White
& "$RootPath\venv\Scripts\python.exe" "$RootPath\scripts\setup_database.py"

# 3. Start FastAPI Backend
Write-Host "`n[3/4] Launching FastAPI Backend on port 8000..." -ForegroundColor White
$BackendProcess = Start-Process -FilePath "$RootPath\venv\Scripts\python.exe" -ArgumentList "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000" -PassThru

# 4. Start React Frontend
Write-Host "`n[4/4] Launching React Workstation on port 3000..." -ForegroundColor White
Set-Location "$RootPath\frontend"
$FrontendProcess = Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev" -PassThru

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host " PLATFORM READY" -ForegroundColor Green
Write-Host " Workstation UI : http://localhost:3000" -ForegroundColor Cyan
Write-Host " Backend API    : http://localhost:8000" -ForegroundColor Cyan
Write-Host " API Docs       : http://localhost:8000/docs" -ForegroundColor DarkGray
Write-Host " Press Ctrl+C to terminate session." -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Green

# Wait for termination
try {
    while ($true) {
        Start-Sleep -Seconds 2
    }
} finally {
    Write-Host "`nShutting down Engineering Memory services..." -ForegroundColor Yellow
    Stop-Process -Id $BackendProcess.Id -ErrorAction SilentlyContinue
    Stop-Process -Id $FrontendProcess.Id -ErrorAction SilentlyContinue
}
