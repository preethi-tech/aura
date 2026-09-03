# Aura launcher (Windows / PowerShell)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) {
    Write-Host "Creating virtual environment..."
    py -3 -m venv .venv
}

Write-Host "Installing dependencies..."
& .\.venv\Scripts\python -m pip install --upgrade pip | Out-Null
& .\.venv\Scripts\python -m pip install -r backend\requirements.txt

Write-Host "Starting Aura on http://127.0.0.1:8000"
& .\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
