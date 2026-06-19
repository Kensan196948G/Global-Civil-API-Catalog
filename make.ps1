# Windows 11 alternative to Makefile
# Usage: .\make.ps1 [check|compile|validate|test|export]
param([string]$Target = "check")

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Invoke-Compile {
    Write-Host "==> compile" -ForegroundColor Cyan
    python -m compileall scripts tests web
}

function Invoke-Validate {
    Write-Host "==> validate" -ForegroundColor Cyan
    python scripts/validate_catalog.py
}

function Invoke-Test {
    Write-Host "==> test" -ForegroundColor Cyan
    $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
    python -m pytest -q
    Remove-Item Env:PYTEST_DISABLE_PLUGIN_AUTOLOAD -ErrorAction SilentlyContinue
}

function Invoke-Export {
    Write-Host "==> export" -ForegroundColor Cyan
    python scripts/export_markdown.py
}

switch ($Target) {
    "check"    { Invoke-Compile; Invoke-Validate; Invoke-Test; Invoke-Export }
    "compile"  { Invoke-Compile }
    "validate" { Invoke-Validate }
    "test"     { Invoke-Test }
    "export"   { Invoke-Export }
    default    { Write-Error "Unknown target: $Target. Use: check|compile|validate|test|export" }
}
