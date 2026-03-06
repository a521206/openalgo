# OpenAlgo PowerShell Module Installation Script
# Version: 1.0.0
# 
# This script installs the OpenAlgo PowerShell module to your user modules directory
# and optionally adds it to your PowerShell profile for auto-loading.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [switch]$Uninstall,

    [Parameter(Mandatory = $false)]
    [switch]$NoProfileUpdate,

    [Parameter(Mandatory = $false)]
    [switch]$Force
)

# Configuration
$ModuleName = "OpenAlgo"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Determine PowerShell modules path
# Check for OneDrive redirection
if ($PSVersionTable.PSEdition -eq "Core") {
    # Check if OneDrive Documents folder exists
    $OneDrivePath = Join-Path $env:USERPROFILE "OneDrive\Documents\PowerShell\Modules"
    $StandardPath = Join-Path $env:USERPROFILE "Documents\PowerShell\Modules"
    
    if (Test-Path (Split-Path $OneDrivePath -Parent)) {
        $ModulesPath = $OneDrivePath
    }
    else {
        $ModulesPath = $StandardPath
    }
}
else {
    # Windows PowerShell 5.1
    $OneDrivePath = Join-Path $env:USERPROFILE "OneDrive\Documents\WindowsPowerShell\Modules"
    $StandardPath = Join-Path $env:USERPROFILE "Documents\WindowsPowerShell\Modules"
    
    if (Test-Path (Split-Path $OneDrivePath -Parent)) {
        $ModulesPath = $OneDrivePath
    }
    else {
        $ModulesPath = $StandardPath
    }
}

$ModuleInstallPath = Join-Path $ModulesPath $ModuleName

function Write-Header {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  OpenAlgo PowerShell Module Installer" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
}

function Test-Administrator {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Install-Module {
    Write-Host "Installing OpenAlgo PowerShell Module..." -ForegroundColor Green
    Write-Host ""

    # Check if module already exists
    if ((Test-Path $ModuleInstallPath) -and -not $Force) {
        Write-Warning "Module already installed at: $ModuleInstallPath"
        Write-Host "Use -Force to reinstall." -ForegroundColor Yellow
        return $false
    }

    # Create modules directory if it doesn't exist
    if (-not (Test-Path $ModulesPath)) {
        Write-Host "Creating modules directory: $ModulesPath" -ForegroundColor Yellow
        New-Item -Path $ModulesPath -ItemType Directory -Force | Out-Null
    }

    # Create module directory
    if (Test-Path $ModuleInstallPath) {
        Write-Host "Removing existing installation..." -ForegroundColor Yellow
        Remove-Item -Path $ModuleInstallPath -Recurse -Force
    }

    New-Item -Path $ModuleInstallPath -ItemType Directory -Force | Out-Null
    Write-Host "Created module directory: $ModuleInstallPath" -ForegroundColor Green

    # Copy module files
    $FilesToCopy = @("OpenAlgo.psm1", "OpenAlgo.psd1")
    
    foreach ($file in $FilesToCopy) {
        $sourcePath = Join-Path $ScriptDir $file
        $destPath = Join-Path $ModuleInstallPath $file

        if (Test-Path $sourcePath) {
            Copy-Item -Path $sourcePath -Destination $destPath -Force
            Write-Host "Copied: $file" -ForegroundColor Green
        }
        else {
            Write-Warning "Source file not found: $sourcePath"
        }
    }

    Write-Host ""
    Write-Host "Module files installed successfully!" -ForegroundColor Green
    return $true
}

function Uninstall-Module {
    Write-Host "Uninstalling OpenAlgo PowerShell Module..." -ForegroundColor Yellow
    Write-Host ""

    if (-not (Test-Path $ModuleInstallPath)) {
        Write-Host "Module is not installed." -ForegroundColor Yellow
        return $false
    }

    Remove-Item -Path $ModuleInstallPath -Recurse -Force
    Write-Host "Removed: $ModuleInstallPath" -ForegroundColor Green

    # Remove from profile
    Remove-ProfileEntry

    Write-Host ""
    Write-Host "Module uninstalled successfully!" -ForegroundColor Green
    return $true
}

function Add-ProfileEntry {
    if ($NoProfileUpdate) {
        Write-Host "Skipping profile update (NoProfileUpdate specified)." -ForegroundColor Yellow
        return
    }

    # Determine profile path
    if ($PSVersionTable.PSEdition -eq "Core") {
        $ProfilePath = $PROFILE.CurrentUserCurrentHost
    }
    else {
        $ProfilePath = $PROFILE.CurrentUserCurrentHost
    }

    $ProfileDir = Split-Path -Parent $ProfilePath
    $ImportStatement = "Import-Module OpenAlgo -ErrorAction SilentlyContinue"

    # Create profile directory if it doesn't exist
    if (-not (Test-Path $ProfileDir)) {
        New-Item -Path $ProfileDir -ItemType Directory -Force | Out-Null
    }

    # Check if profile exists
    if (-not (Test-Path $ProfilePath)) {
        Write-Host "Creating PowerShell profile: $ProfilePath" -ForegroundColor Yellow
        New-Item -Path $ProfilePath -ItemType File -Force | Out-Null
    }

    # Check if import already exists
    $profileContent = Get-Content -Path $ProfilePath -Raw -ErrorAction SilentlyContinue
    
    if ($profileContent -and $profileContent -match "Import-Module.*OpenAlgo") {
        Write-Host "Profile already contains OpenAlgo import." -ForegroundColor Green
        return
    }

    # Add import statement to profile
    Add-Content -Path $ProfilePath -Value ""
    Add-Content -Path $ProfilePath -Value "# OpenAlgo PowerShell Module"
    Add-Content -Path $ProfilePath -Value $ImportStatement

    Write-Host "Added module import to profile: $ProfilePath" -ForegroundColor Green
}

function Remove-ProfileEntry {
    # Determine profile path
    if ($PSVersionTable.PSEdition -eq "Core") {
        $ProfilePath = $PROFILE.CurrentUserCurrentHost
    }
    else {
        $ProfilePath = $PROFILE.CurrentUserCurrentHost
    }

    if (-not (Test-Path $ProfilePath)) {
        return
    }

    $profileContent = Get-Content -Path $ProfilePath -ErrorAction SilentlyContinue
    
    if ($profileContent -and ($profileContent -match "OpenAlgo")) {
        $newContent = $profileContent | Where-Object { 
            $_ -notmatch "Import-Module.*OpenAlgo" -and 
            $_ -notmatch "# OpenAlgo PowerShell Module"
        }
        
        Set-Content -Path $ProfilePath -Value $newContent -Force
        Write-Host "Removed module import from profile." -ForegroundColor Green
    }
}

function Show-PostInstallInfo {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Installation Complete!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Module installed to:" -ForegroundColor White
    Write-Host "  $ModuleInstallPath" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Available Commands:" -ForegroundColor White
    Write-Host "  openalgo              - Start OpenAlgo (alias)" -ForegroundColor Yellow
    Write-Host "  Start-OpenAlgo        - Start OpenAlgo" -ForegroundColor Yellow
    Write-Host "  Stop-OpenAlgo         - Stop OpenAlgo" -ForegroundColor Yellow
    Write-Host "  Get-OpenAlgoStatus    - Check status" -ForegroundColor Yellow
    Write-Host "  Open-OpenAlgoFolder   - Open project folder" -ForegroundColor Yellow
    Write-Host "  Open-OpenAlgoWeb      - Open in browser" -ForegroundColor Yellow
    Write-Host "  Get-OpenAlgoConfig    - Show configuration" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To start using the module:" -ForegroundColor White
    Write-Host "  1. Close and reopen PowerShell, OR" -ForegroundColor Gray
    Write-Host "  2. Run: Import-Module OpenAlgo" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Quick Start:" -ForegroundColor White
    Write-Host "  openalgo              # Start with defaults" -ForegroundColor Cyan
    Write-Host "  openalgo -Debug       # Start in debug mode" -ForegroundColor Cyan
    Write-Host "  openalgo -Background  # Start in new window" -ForegroundColor Cyan
    Write-Host ""
}

function Show-UninstallInfo {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Uninstallation Complete!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "The OpenAlgo module has been removed from:" -ForegroundColor White
    Write-Host "  $ModuleInstallPath" -ForegroundColor Gray
    Write-Host ""
    Write-Host "To complete the removal:" -ForegroundColor White
    Write-Host "  1. Close and reopen PowerShell, OR" -ForegroundColor Gray
    Write-Host "  2. Run: Remove-Module OpenAlgo" -ForegroundColor Gray
    Write-Host ""
}

# Main execution
Write-Header

if ($Uninstall) {
    Uninstall-Module
    Show-UninstallInfo
}
else {
    $success = Install-Module
    
    if ($success) {
        Add-ProfileEntry
        Show-PostInstallInfo
    }
}
