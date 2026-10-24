# uninstall_autostart.ps1 - Removes per-user scheduled task for JARVIS
$ErrorActionPreference = "Continue"

$TaskName = "JARVIS"

try {
    $Service = New-Object -ComObject("Schedule.Service")
    $Service.Connect()
    $RootFolder = $Service.GetFolder("\")
    $RootFolder.DeleteTask($TaskName, 0)
    Write-Host "JARVIS Scheduled Task '$TaskName' successfully removed." -ForegroundColor Green
} catch {
    Write-Host "Task '$TaskName' was not found or has already been removed." -ForegroundColor Yellow
}
