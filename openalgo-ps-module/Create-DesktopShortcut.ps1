# OpenAlgo Desktop Shortcut Creator
# This script creates a desktop shortcut to launch OpenAlgo

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [switch]$Force
)

# Configuration
$ShortcutName = "OpenAlgo"
$ProjectPath = "C:\Users\agraw\GIT\openalgo"

# Get desktop path
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $DesktopPath "$ShortcutName.lnk"

# Check if shortcut already exists
if ((Test-Path $ShortcutPath) -and -not $Force) {
    Write-Host "Desktop shortcut already exists at: $ShortcutPath" -ForegroundColor Yellow
    Write-Host "Use -Force to recreate it." -ForegroundColor Yellow
    exit 0
}

# Create the shortcut
$WScriptShell = New-Object -ComObject WScript.Shell
$Shortcut = $WScriptShell.CreateShortcut($ShortcutPath)

# Set shortcut properties
$Shortcut.TargetPath = "pwsh.exe"
$Shortcut.Arguments = "-NoExit -Command `"Import-Module OpenAlgo; Start-OpenAlgo`""
$Shortcut.WorkingDirectory = $ProjectPath
$Shortcut.Description = "Launch OpenAlgo Trading Platform"
$Shortcut.IconLocation = "pwsh.exe,0"

# Save the shortcut
$Shortcut.Save()

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Desktop Shortcut Created!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Shortcut location: $ShortcutPath" -ForegroundColor White
Write-Host ""
Write-Host "Double-click the shortcut on your desktop to launch OpenAlgo." -ForegroundColor Yellow
Write-Host ""
