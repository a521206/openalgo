# OpenAlgo PowerShell Module
# Version: 1.0.0
# Provides commands to manage OpenAlgo application from anywhere

# Module Constants
$script:OpenAlgoPath = "C:\Users\agraw\GIT\openalgo"
$script:VenvPath = Join-Path $script:OpenAlgoPath ".venv"
$script:AppPath = Join-Path $script:OpenAlgoPath "app.py"
$script:EnvFile = Join-Path $script:OpenAlgoPath ".env"
$script:ModuleName = "OpenAlgo"

<#
.SYNOPSIS
    Starts the OpenAlgo application.

.DESCRIPTION
    Starts the OpenAlgo Flask application with the specified configuration.
    The function automatically navigates to the project directory, activates
    the virtual environment, and starts the application.

.PARAMETER HostIP
    The host IP address to bind the application to.
    Default: 127.0.0.1

.PARAMETER Port
    The port number for the application.
    Default: 5000

.PARAMETER FlaskDebug
    Enable Flask debug mode with auto-reload.

.PARAMETER Background
    Run the application in a new PowerShell window.

.PARAMETER NoActivate
    Skip virtual environment activation (use if already activated).

.EXAMPLE
    Start-OpenAlgo
    Starts OpenAlgo with default settings.

.EXAMPLE
    Start-OpenAlgo -Debug
    Starts OpenAlgo in debug mode.

.EXAMPLE
    Start-OpenAlgo -Port 8080 -HostIP "0.0.0.0"
    Starts OpenAlgo on port 8080, accessible from the network.

.EXAMPLE
    Start-OpenAlgo -Background
    Starts OpenAlgo in a new window.

.NOTES
    Requires Python virtual environment at .venv in the project directory.
#>
function Start-OpenAlgo {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $false)]
        [ValidateNotNullOrEmpty()]
        [string]$HostIP = "127.0.0.1",

        [Parameter(Mandatory = $false)]
        [ValidateRange(1, 65535)]
        [int]$Port = 5000,

        [Parameter(Mandatory = $false)]
        [switch]$FlaskDebug,

        [Parameter(Mandatory = $false)]
        [switch]$Background,

        [Parameter(Mandatory = $false)]
        [switch]$NoActivate
    )

    begin {
        Write-Host "OpenAlgo Startup" -ForegroundColor Cyan
        Write-Host "================" -ForegroundColor Cyan
    }

    process {
        # Validate project path
        if (-not (Test-Path $script:OpenAlgoPath)) {
            Write-Error "OpenAlgo project directory not found at: $($script:OpenAlgoPath)"
            return
        }

        # Validate app.py exists
        if (-not (Test-Path $script:AppPath)) {
            Write-Error "app.py not found at: $($script:AppPath)"
            return
        }

        # Check for .env file
        if (-not (Test-Path $script:EnvFile)) {
            Write-Warning ".env file not found. Using default configuration."
        }

        # Validate virtual environment
        $activateScript = Join-Path $script:VenvPath "Scripts\Activate.ps1"
        if (-not $NoActivate -and -not (Test-Path $activateScript)) {
            Write-Error "Virtual environment not found at: $($script:VenvPath)"
            Write-Host "Please create a virtual environment first:" -ForegroundColor Yellow
            Write-Host "  cd $($script:OpenAlgoPath)" -ForegroundColor Yellow
            Write-Host "  python -m venv .venv" -ForegroundColor Yellow
            Write-Host "  .\.venv\Scripts\Activate.ps1" -ForegroundColor Yellow
            Write-Host "  pip install -r requirements.txt" -ForegroundColor Yellow
            return
        }

        # Build environment variables
        $envVars = @{
            "FLASK_HOST_IP" = $HostIP
            "FLASK_PORT" = $Port.ToString()
            "FLASK_DEBUG" = if ($FlaskDebug) { "True" } else { "False" }
        }

        # Build the command to run
        $pythonExe = if (-not $NoActivate) {
            Join-Path $script:VenvPath "Scripts\python.exe"
        } else {
            "python"
        }

        # Validate Python executable exists
        if (-not $NoActivate -and -not (Test-Path $pythonExe)) {
            Write-Error "Python executable not found in virtual environment: $pythonExe"
            return
        }

        if ($Background) {
            # Start in a new PowerShell window
            Write-Host "Starting OpenAlgo in a new window..." -ForegroundColor Green
            
            $scriptBlock = {
                param($ProjectPath, $VenvPath, $AppPath, $HostIP, $Port, $FlaskDebug)
                
                Set-Location $ProjectPath
                
                # Activate virtual environment
                $activateScript = Join-Path $VenvPath "Scripts\Activate.ps1"
                if (Test-Path $activateScript) {
                    . $activateScript
                }
                
                # Set environment variables
                $env:FLASK_HOST_IP = $HostIP
                $env:FLASK_PORT = $Port.ToString()
                $env:FLASK_DEBUG = if ($FlaskDebug) { "True" } else { "False" }
                
                # Run the application
                python $AppPath
            }
            
            Start-Process powershell -ArgumentList @(
                "-NoExit",
                "-Command", "& { $scriptBlock } '$($script:OpenAlgoPath)' '$($script:VenvPath)' '$($script:AppPath)' '$HostIP' '$Port' '$FlaskDebug'"
            )
            
            Write-Host "OpenAlgo started in background window." -ForegroundColor Green
            Write-Host "Access the application at: http://$HostIP`:$Port" -ForegroundColor Cyan
        }
        else {
            # Run in current terminal
            Write-Host "Project Path: $($script:OpenAlgoPath)" -ForegroundColor Gray
            Write-Host "Host: $HostIP" -ForegroundColor Gray
            Write-Host "Port: $Port" -ForegroundColor Gray
            Write-Host "Debug: $FlaskDebug" -ForegroundColor Gray
            Write-Host ""

            # Change to project directory
            Set-Location $script:OpenAlgoPath

            # Activate virtual environment
            if (-not $NoActivate) {
                Write-Host "Activating virtual environment..." -ForegroundColor Yellow
                . $activateScript
            }

            # Set environment variables
            $env:FLASK_HOST_IP = $HostIP
            $env:FLASK_PORT = $Port.ToString()
                $env:FLASK_DEBUG = if ($FlaskDebug) { "True" } else { "False" }

            # Start the application
            Write-Host "Starting OpenAlgo..." -ForegroundColor Green
            Write-Host ""

            & $pythonExe $script:AppPath
        }
    }
}

<#
.SYNOPSIS
    Stops running OpenAlgo instances.

.DESCRIPTION
    Finds and stops any running OpenAlgo Python processes.

.EXAMPLE
    Stop-OpenAlgo
    Stops all running OpenAlgo instances.

.NOTES
    This will stop all Python processes running app.py from the OpenAlgo directory.
#>
function Stop-OpenAlgo {
    [CmdletBinding()]
    param()

    Write-Host "Stopping OpenAlgo..." -ForegroundColor Yellow

    # Find Python processes running app.py
    $processes = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*app.py*" -or $_.CommandLine -like "*openalgo*" }

    if ($processes) {
        foreach ($proc in $processes) {
            try {
                Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
                Write-Host "Stopped process ID: $($proc.ProcessId)" -ForegroundColor Green
            }
            catch {
                Write-Warning "Failed to stop process $($proc.ProcessId): $_"
            }
        }
        Write-Host "OpenAlgo stopped." -ForegroundColor Green
    }
    else {
        Write-Host "No running OpenAlgo processes found." -ForegroundColor Yellow
    }
}

<#
.SYNOPSIS
    Gets the status of OpenAlgo instances.

.DESCRIPTION
    Checks if OpenAlgo is currently running and displays process information.

.EXAMPLE
    Get-OpenAlgoStatus
    Shows the status of running OpenAlgo instances.

.OUTPUTS
    System.Management.Automation.PSCustomObject
    Returns an object with Status and Processes properties.
#>
function Get-OpenAlgoStatus {
    [CmdletBinding()]
    param()

    # Find Python processes running app.py
    $processes = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*app.py*" -or $_.CommandLine -like "*openalgo*" }

    if ($processes) {
        Write-Host "OpenAlgo is RUNNING" -ForegroundColor Green
        Write-Host ""
        Write-Host "Process Details:" -ForegroundColor Cyan
        Write-Host "================" -ForegroundColor Cyan

        foreach ($proc in $processes) {
            $processInfo = Get-Process -Id $proc.ProcessId -ErrorAction SilentlyContinue
            if ($processInfo) {
                Write-Host "  PID:            $($proc.ProcessId)" -ForegroundColor White
                Write-Host "  Memory (MB):    $([math]::Round($processInfo.WorkingSet64 / 1MB, 2))" -ForegroundColor White
                Write-Host "  Start Time:     $($processInfo.StartTime)" -ForegroundColor White
                Write-Host "  Command:        $($proc.CommandLine.Substring(0, [Math]::Min(100, $proc.CommandLine.Length)))..." -ForegroundColor Gray
                Write-Host ""
            }
        }

        # Check if port is listening
        $port5000 = Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue
        if ($port5000) {
            Write-Host "Port 5000: LISTENING" -ForegroundColor Green
        }

        return [PSCustomObject]@{
            Status = "Running"
            ProcessCount = @($processes).Count
            Processes = $processes | ForEach-Object { $_.ProcessId }
        }
    }
    else {
        Write-Host "OpenAlgo is NOT RUNNING" -ForegroundColor Red

        return [PSCustomObject]@{
            Status = "Stopped"
            ProcessCount = 0
            Processes = @()
        }
    }
}

<#
.SYNOPSIS
    Opens the OpenAlgo project folder.

.DESCRIPTION
    Opens the OpenAlgo project directory in Windows Explorer or the current terminal.

.PARAMETER InTerminal
    Change to the project directory in the current terminal instead of opening Explorer.

.EXAMPLE
    Open-OpenAlgoFolder
    Opens the project folder in Windows Explorer.

.EXAMPLE
    Open-OpenAlgoFolder -InTerminal
    Changes to the project directory in the current terminal.
#>
function Open-OpenAlgoFolder {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $false)]
        [switch]$InTerminal
    )

    if (-not (Test-Path $script:OpenAlgoPath)) {
        Write-Error "OpenAlgo project directory not found at: $($script:OpenAlgoPath)"
        return
    }

    if ($InTerminal) {
        Set-Location $script:OpenAlgoPath
        Write-Host "Changed to: $($script:OpenAlgoPath)" -ForegroundColor Green
    }
    else {
        explorer.exe $script:OpenAlgoPath
        Write-Host "Opened folder: $($script:OpenAlgoPath)" -ForegroundColor Green
    }
}

<#
.SYNOPSIS
    Opens the OpenAlgo web interface in a browser.

.DESCRIPTION
    Opens the OpenAlgo web application in the default browser.

.PARAMETER Port
    The port number where OpenAlgo is running.
    Default: 5000

.EXAMPLE
    Open-OpenAlgoWeb
    Opens http://127.0.0.1:5000 in the default browser.
#>
function Open-OpenAlgoWeb {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $false)]
        [ValidateRange(1, 65535)]
        [int]$Port = 5000
    )

    $url = "http://127.0.0.1:$Port"
    Write-Host "Opening $url in browser..." -ForegroundColor Cyan
    Start-Process $url
}

<#
.SYNOPSIS
    Gets the OpenAlgo project configuration.

.DESCRIPTION
    Displays the current configuration paths and settings for the OpenAlgo module.

.EXAMPLE
    Get-OpenAlgoConfig
    Shows the current module configuration.
#>
function Get-OpenAlgoConfig {
    [CmdletBinding()]
    param()

    Write-Host "OpenAlgo Module Configuration" -ForegroundColor Cyan
    Write-Host "==============================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Project Path:    $($script:OpenAlgoPath)" -ForegroundColor White
    Write-Host "Virtual Env:     $($script:VenvPath)" -ForegroundColor White
    Write-Host "App File:        $($script:AppPath)" -ForegroundColor White
    Write-Host "Env File:        $($script:EnvFile)" -ForegroundColor White
    Write-Host ""
    
    Write-Host "Path Validation:" -ForegroundColor Cyan
    Write-Host "  Project exists:    $(if (Test-Path $script:OpenAlgoPath) { 'YES' } else { 'NO' })" -ForegroundColor $(if (Test-Path $script:OpenAlgoPath) { 'Green' } else { 'Red' })
    Write-Host "  Venv exists:       $(if (Test-Path $script:VenvPath) { 'YES' } else { 'NO' })" -ForegroundColor $(if (Test-Path $script:VenvPath) { 'Green' } else { 'Red' })
    Write-Host "  App.py exists:     $(if (Test-Path $script:AppPath) { 'YES' } else { 'NO' })" -ForegroundColor $(if (Test-Path $script:AppPath) { 'Green' } else { 'Red' })
    Write-Host "  .env exists:       $(if (Test-Path $script:EnvFile) { 'YES' } else { 'NO' })" -ForegroundColor $(if (Test-Path $script:EnvFile) { 'Green' } else { 'Yellow' })
}

# Create aliases
Set-Alias -Name openalgo -Value Start-OpenAlgo
Set-Alias -Name stopalgo -Value Stop-OpenAlgo
Set-Alias -Name algostatus -Value Get-OpenAlgoStatus
Set-Alias -Name algofolder -Value Open-OpenAlgoFolder
Set-Alias -Name algoweb -Value Open-OpenAlgoWeb
Set-Alias -Name algoconfig -Value Get-OpenAlgoConfig

# Export functions and aliases
Export-ModuleMember -Function @(
    'Start-OpenAlgo',
    'Stop-OpenAlgo',
    'Get-OpenAlgoStatus',
    'Open-OpenAlgoFolder',
    'Open-OpenAlgoWeb',
    'Get-OpenAlgoConfig'
)

Export-ModuleMember -Alias @(
    'openalgo',
    'stopalgo',
    'algostatus',
    'algofolder',
    'algoweb',
    'algoconfig'
)
