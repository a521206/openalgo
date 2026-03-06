# OpenAlgo PowerShell Module

A PowerShell module for managing the OpenAlgo application from anywhere on your system.

## Features

- **Start-OpenAlgo** - Start the OpenAlgo application with configurable options
- **Stop-OpenAlgo** - Stop running OpenAlgo instances
- **Get-OpenAlgoStatus** - Check if OpenAlgo is running
- **Open-OpenAlgoFolder** - Open the project folder
- **Open-OpenAlgoWeb** - Open the web interface in browser
- **Get-OpenAlgoConfig** - Display module configuration

## Quick Start

### Installation

1. Open PowerShell
2. Navigate to the module directory:
   ```powershell
   cd C:\Users\agraw\GIT\openalgo\openalgo-ps-module
   ```
3. Run the installation script:
   ```powershell
   .\Install-OpenAlgoModule.ps1
   ```
4. Restart PowerShell or run:
   ```powershell
   Import-Module OpenAlgo
   ```

### Basic Usage

```powershell
# Start OpenAlgo with default settings
openalgo

# Or use the full command
Start-OpenAlgo

# Start in debug mode
openalgo -FlaskDebug

# Start on a different port
openalgo -Port 8080

# Start accessible from network
openalgo -HostIP "0.0.0.0"

# Start in a new window (background)
openalgo -Background
```

## Commands Reference

### Start-OpenAlgo

Starts the OpenAlgo Flask application.

```powershell
Start-OpenAlgo [-HostIP <string>] [-Port <int>] [-Debug] [-Background] [-NoActivate]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| HostIP | string | 127.0.0.1 | Host IP to bind |
| Port | int | 5000 | Port to listen on |
| FlaskDebug | switch | false | Enable Flask debug mode |
| Background | switch | false | Run in new window |
| NoActivate | switch | false | Skip venv activation |

**Examples:**
```powershell
# Basic start
Start-OpenAlgo

# Debug mode with custom port
Start-OpenAlgo -FlaskDebug -Port 5001

# Network accessible
Start-OpenAlgo -HostIP "0.0.0.0" -Port 5000

# Background mode
Start-OpenAlgo -Background
```

### Stop-OpenAlgo

Stops all running OpenAlgo instances.

```powershell
Stop-OpenAlgo
```

**Examples:**
```powershell
# Stop all instances
Stop-OpenAlgo

# Using alias
stopalgo
```

### Get-OpenAlgoStatus

Checks if OpenAlgo is running and displays process information.

```powershell
Get-OpenAlgoStatus
```

**Examples:**
```powershell
# Check status
Get-OpenAlgoStatus

# Using alias
algostatus
```

### Open-OpenAlgoFolder

Opens the OpenAlgo project folder.

```powershell
Open-OpenAlgoFolder [-InTerminal]
```

| Parameter | Type | Description |
|-----------|------|-------------|
| InTerminal | switch | Change directory in terminal instead of opening Explorer |

**Examples:**
```powershell
# Open in Windows Explorer
Open-OpenAlgoFolder

# Change directory in terminal
Open-OpenAlgoFolder -InTerminal

# Using alias
algofolder
```

### Open-OpenAlgoWeb

Opens the OpenAlgo web interface in your default browser.

```powershell
Open-OpenAlgoWeb [-Port <int>]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| Port | int | 5000 | Port where OpenAlgo is running |

**Examples:**
```powershell
# Open default URL
Open-OpenAlgoWeb

# Open custom port
Open-OpenAlgoWeb -Port 8080

# Using alias
algoweb
```

### Get-OpenAlgoConfig

Displays the module configuration and validates paths.

```powershell
Get-OpenAlgoConfig
```

**Examples:**
```powershell
# Show configuration
Get-OpenAlgoConfig

# Using alias
algoconfig
```

## Aliases

For convenience, the following aliases are available:

| Alias | Command |
|-------|---------|
| `openalgo` | `Start-OpenAlgo` |
| `stopalgo` | `Stop-OpenAlgo` |
| `algostatus` | `Get-OpenAlgoStatus` |
| `algofolder` | `Open-OpenAlgoFolder` |
| `algoweb` | `Open-OpenAlgoWeb` |
| `algoconfig` | `Get-OpenAlgoConfig` |

## Installation Options

### Standard Installation

```powershell
.\Install-OpenAlgoModule.ps1
```

This will:
1. Copy module files to your PowerShell modules directory
2. Add the module import to your PowerShell profile

### Force Reinstall

```powershell
.\Install-OpenAlgoModule.ps1 -Force
```

### Install Without Profile Update

```powershell
.\Install-OpenAlgoModule.ps1 -NoProfileUpdate
```

### Uninstall

```powershell
.\Install-OpenAlgoModule.ps1 -Uninstall
```

## Configuration

The module is pre-configured for the following paths:

| Setting | Value |
|---------|-------|
| Project Path | `C:\Users\agraw\GIT\openalgo` |
| Virtual Environment | `.venv` |
| App File | `app.py` |

To change these paths, edit the constants at the top of `OpenAlgo.psm1`:

```powershell
$script:OpenAlgoPath = "C:\Users\agraw\GIT\openalgo"
$script:VenvPath = Join-Path $script:OpenAlgoPath ".venv"
$script:AppPath = Join-Path $script:OpenAlgoPath "app.py"
```

## Troubleshooting

### Module Not Found

If you get an error that the module is not found:

1. Verify the module is installed:
   ```powershell
   Get-Module -ListAvailable OpenAlgo
   ```

2. Import manually:
   ```powershell
   Import-Module OpenAlgo
   ```

### Virtual Environment Not Found

If you see an error about the virtual environment:

1. Navigate to the project:
   ```powershell
   cd C:\Users\agraw\GIT\openalgo
   ```

2. Create the virtual environment:
   ```powershell
   python -m venv .venv
   ```

3. Activate and install dependencies:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

### Execution Policy

If scripts won't run due to execution policy:

```powershell
# Check current policy
Get-ExecutionPolicy

# Set policy for current user
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## Requirements

- Windows PowerShell 5.1 or PowerShell Core 7+
- Python 3.x with virtual environment
- OpenAlgo project with dependencies installed

## Files

```
openalgo-ps-module/
├── OpenAlgo.psm1              # Main module script
├── OpenAlgo.psd1              # Module manifest
├── Install-OpenAlgoModule.ps1 # Installation script
└── README.md                  # This file
```

## License

This module is part of the OpenAlgo project.
