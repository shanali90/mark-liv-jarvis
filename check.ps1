# PowerShell script to run checks on NEW Phase 1 code only
# Legacy code is excluded because it contains 1000+ pre-existing ruff errors 
# and relies on system packages not installed in this strict dev .venv.
param (
    [switch]$CiMode = $false
)

$ErrorActionPreference = "Stop"
$failed = $false

Write-Host "Running Ruff Linter..." -ForegroundColor Cyan
# Check only new files
if ($CiMode) { ruff check --ignore=BLE001,DTZ003,S110,PLW1510 core/config_schema.py core/logger.py core/audit.py core/permissions.py core/registry.py core/kill_switch.py core/health.py core/vault.py set_secret.py tests/test_phase1.py } else { .\.venv\Scripts\ruff check --ignore=BLE001,DTZ003,S110,PLW1510 core/config_schema.py core/logger.py core/audit.py core/permissions.py core/registry.py core/kill_switch.py core/health.py core/vault.py set_secret.py tests/test_phase1.py }
if ($LASTEXITCODE -ne 0) { $failed = $true; Write-Host "Ruff failed." -ForegroundColor Red }

Write-Host "Running MyPy Type Checker..." -ForegroundColor Cyan
if ($CiMode) { mypy core/config_schema.py core/logger.py core/audit.py core/permissions.py core/registry.py core/kill_switch.py core/health.py core/vault.py set_secret.py tests/test_phase1.py } else { .\.venv\Scripts\mypy core/config_schema.py core/logger.py core/audit.py core/permissions.py core/registry.py core/kill_switch.py core/health.py core/vault.py set_secret.py tests/test_phase1.py }
if ($LASTEXITCODE -ne 0) { $failed = $true; Write-Host "MyPy failed." -ForegroundColor Red }

Write-Host "Running Pytest..." -ForegroundColor Cyan
if ($CiMode) { pytest tests/test_phase1.py } else { .\.venv\Scripts\pytest tests/test_phase1.py }
if ($LASTEXITCODE -ne 0) { $failed = $true; Write-Host "Pytest failed." -ForegroundColor Red }

if ($failed) {
    Write-Host "Checks failed!" -ForegroundColor Red
    exit 1
} else {
    Write-Host "All checks passed!" -ForegroundColor Green
    exit 0
}
