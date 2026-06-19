# Windows 11 launcher for Global Civil API Catalog
# Requires: Docker Desktop with WSL2 backend
# Usage: .\deploy\start.ps1 [-Stop] [-Logs]
param(
    [switch]$Stop,
    [switch]$Logs
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Set-Location $ProjectRoot

if ($Stop) {
    Write-Host "Stopping Global Civil API Catalog..." -ForegroundColor Yellow
    docker compose down
    exit 0
}

if ($Logs) {
    docker compose logs -f web
    exit 0
}

Write-Host "Starting Global Civil API Catalog on http://localhost:49231 ..." -ForegroundColor Cyan
docker compose up -d --build
Write-Host ""
Write-Host "Health check:" -ForegroundColor Green
Start-Sleep -Seconds 3
try {
    $response = Invoke-WebRequest -Uri "http://localhost:49231/api/health" -UseBasicParsing
    Write-Host "  OK: $($response.Content)" -ForegroundColor Green
} catch {
    Write-Host "  Waiting for service to start. Run: docker compose logs web" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Dashboard: http://localhost:49231" -ForegroundColor Cyan
Write-Host "Stop:      .\deploy\start.ps1 -Stop" -ForegroundColor Gray
