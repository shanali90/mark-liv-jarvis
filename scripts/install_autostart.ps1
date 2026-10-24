# install_autostart.ps1 - Registers per-user scheduled task for JARVIS
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$PythonW = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"

if (-not (Test-Path $PythonW)) {
    $PythonW = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path $PythonW)) {
    Write-Error "Could not find Python environment at $PythonW"
}

$TaskName = "JARVIS"

$Service = New-Object -ComObject("Schedule.Service")
$Service.Connect()
$RootFolder = $Service.GetFolder("\")
$TaskDef = $Service.NewTask(0)
$TaskDef.RegistrationInfo.Description = "JARVIS Assistant wake-word background autostart"

# Triggers:
# 1. At user logon (trigger type 9 = TASK_TRIGGER_LOGON)
$LogonTrigger = $TaskDef.Triggers.Create(9)
$LogonTrigger.Enabled = $true
$LogonTrigger.Delay = "PT20S"
$LogonTrigger.UserId = "$env:USERDOMAIN\$env:USERNAME"

# 2. At workstation unlock (trigger type 11 = TASK_TRIGGER_SESSION_STATE_CHANGE, state 8 = TASK_SESSION_UNLOCK)
$UnlockTrigger = $TaskDef.Triggers.Create(11)
$UnlockTrigger.Enabled = $true
$UnlockTrigger.Delay = "PT20S"
$UnlockTrigger.StateChange = 8
$UnlockTrigger.UserId = "$env:USERDOMAIN\$env:USERNAME"

# Settings
$TaskDef.Settings.DisallowStartIfOnBatteries = $false
$TaskDef.Settings.StopIfGoingOnBatteries = $false
$TaskDef.Settings.ExecutionTimeLimit = "PT0S"

# Action
$Action = $TaskDef.Actions.Create(0)
$Action.Path = $PythonW
$Action.Arguments = "main.py"
$Action.WorkingDirectory = $ProjectRoot

# Register as current interactive user (no admin rights required)
# 6 = TASK_CREATE_OR_UPDATE, 3 = TASK_LOGON_INTERACTIVE_TOKEN
$RootFolder.RegisterTaskDefinition($TaskName, $TaskDef, 6, $null, $null, 3) | Out-Null

Write-Host "==========================================================" -ForegroundColor Green
Write-Host "JARVIS Autostart Task Successfully Created!" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "Task Name:        $TaskName"
Write-Host "Program:          $PythonW"
Write-Host "Arguments:        main.py"
Write-Host "Working Directory:$ProjectRoot"
Write-Host "Triggers:         Logon and Workstation Unlock (20s delay)"
Write-Host "Mode:             Hidden/asleep start listening for wake word"
Write-Host "Security:         Per-user least privilege, no API keys stored"
Write-Host "----------------------------------------------------------"
Write-Host "To remove this autostart task, run:" -ForegroundColor Cyan
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\uninstall_autostart.ps1" -ForegroundColor Yellow
Write-Host "=========================================================="
