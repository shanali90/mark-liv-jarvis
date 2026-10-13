# Informational check for legacy code. Does not exit non-zero.
param (
    [switch]$CiMode = $false
)

Write-Host "Running Ruff Linter (Legacy)..." -ForegroundColor Cyan
if ($CiMode) { ruff check . } else { .\.venv\Scripts\ruff check . }

Write-Host "Running MyPy Type Checker (Legacy)..." -ForegroundColor Cyan
if ($CiMode) { mypy core actions plugins } else { .\.venv\Scripts\mypy core actions plugins }

Write-Host "Running Pytest (Legacy)..." -ForegroundColor Cyan
if ($CiMode) { pytest tests } else { .\.venv\Scripts\pytest tests }

Write-Host "Legacy checks complete (Informational only)." -ForegroundColor Green
exit 0
