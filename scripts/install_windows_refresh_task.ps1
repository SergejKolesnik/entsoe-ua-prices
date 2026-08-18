param(
    [string]$TaskName = "RDN Market Daily Refresh"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = (Get-Command python).Source
$arguments = '"' + (Join-Path $projectRoot "refresh_operator.py") + '"'

$action = New-ScheduledTaskAction `
    -Execute $pythonPath `
    -Argument $arguments `
    -WorkingDirectory $projectRoot

$triggers = @(
    New-ScheduledTaskTrigger -Daily -At "14:15"
    New-ScheduledTaskTrigger -Daily -At "15:00"
    New-ScheduledTaskTrigger -Daily -At "16:00"
    New-ScheduledTaskTrigger -Daily -At "17:00"
)

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $triggers `
    -Settings $settings `
    -Description "Downloads and validates next-day Ukrainian DAM prices." `
    -Force

Write-Host "Scheduled task '$TaskName' installed."
Write-Host "Runs daily at 14:15, 15:00, 16:00 and 17:00 in the Windows local timezone."
