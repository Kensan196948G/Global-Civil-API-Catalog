@echo off
REM Windows 11 launcher for Global Civil API Catalog (CMD version)
REM Requires: Docker Desktop with WSL2 backend

cd /d "%~dp0.."

echo Starting Global Civil API Catalog on http://localhost:49231 ...
docker compose up -d --build
if %ERRORLEVEL% neq 0 (
    echo ERROR: docker compose failed. Is Docker Desktop running?
    pause
    exit /b 1
)
echo.
echo Dashboard: http://localhost:49231
echo Stop:      docker compose down
