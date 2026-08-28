[CmdletBinding()]
param(
    [ValidateSet("Menu", "Start", "Stop", "Status", "Connect", "Send", "Ports")]
    [string]$Action = "Menu",
    [string]$Command
)

$ErrorActionPreference = "Stop"
$ToolDir = Split-Path -Parent $PSCommandPath
$ConfigPath = Join-Path $ToolDir "serial_config.psd1"
$BridgePath = Join-Path $ToolDir "..\scripts\shared_serial_bridge.py"
$RuntimeDir = Join-Path $ToolDir ".runtime"
$PidPath = Join-Path $RuntimeDir "bridge.pid"
$DiagnosticLog = Join-Path $RuntimeDir "bridge_diagnostic.log"
$DiagnosticErrorLog = Join-Path $RuntimeDir "bridge_error.log"
$LogDir = Join-Path $ToolDir "logs"

function Get-SerialConfig {
    if (-not (Test-Path -LiteralPath $ConfigPath)) {
        throw "Config file not found: $ConfigPath"
    }
    return Import-PowerShellDataFile -LiteralPath $ConfigPath
}

function Get-BridgeProcess {
    if (-not (Test-Path -LiteralPath $PidPath)) { return $null }
    $SavedPid = [int](Get-Content -LiteralPath $PidPath -Raw)
    $ProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $SavedPid" -ErrorAction SilentlyContinue
    if ($null -eq $ProcessInfo -or $ProcessInfo.CommandLine -notlike "*shared_serial_bridge.py*bridge*") {
        Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
        return $null
    }
    return $ProcessInfo
}

function Test-TcpEndpoint([string]$HostName, [int]$PortNumber) {
    $Client = [System.Net.Sockets.TcpClient]::new()
    try {
        $Task = $Client.ConnectAsync($HostName, $PortNumber)
        return $Task.Wait(500) -and $Client.Connected
    }
    catch { return $false }
    finally { $Client.Dispose() }
}

function Assert-PythonAndPySerial($Config) {
    & $Config.Python -c "import serial" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "pyserial is missing. Run: $($Config.Python) -m pip install -r `"$ToolDir\requirements.txt`""
    }
}

function Start-SerialBridge {
    $Config = Get-SerialConfig
    $Existing = Get-BridgeProcess
    if ($null -ne $Existing) {
        Write-Host "Bridge is already running (PID $($Existing.ProcessId))." -ForegroundColor Yellow
        return
    }
    Assert-PythonAndPySerial $Config
    New-Item -ItemType Directory -Path $RuntimeDir, $LogDir -Force | Out-Null
    Remove-Item -LiteralPath $DiagnosticLog, $DiagnosticErrorLog -Force -ErrorAction SilentlyContinue
    $SafePortName = ([string]$Config.Port) -replace '[^A-Za-z0-9._-]', '_'
    $SerialLog = Join-Path $LogDir ("serial_{0}_{1}.log" -f $SafePortName, (Get-Date -Format "yyyyMMdd_HHmmss"))
    $Arguments = @(
        $BridgePath, "bridge",
        "--port", [string]$Config.Port,
        "--baud", [string]$Config.Baud,
        "--host", [string]$Config.Host,
        "--tcp", [string]$Config.TcpPort,
        "--chardelay", [string]$Config.CharDelay,
        "--log", $SerialLog
    )
    $Started = Start-Process -FilePath $Config.Python -ArgumentList $Arguments -WorkingDirectory $ToolDir `
        -WindowStyle Hidden -RedirectStandardOutput $DiagnosticLog `
        -RedirectStandardError $DiagnosticErrorLog -PassThru
    Set-Content -LiteralPath $PidPath -Value $Started.Id -Encoding ascii
    Start-Sleep -Milliseconds 900
    $Running = Get-BridgeProcess
    if ($null -eq $Running -or -not (Test-TcpEndpoint $Config.Host $Config.TcpPort)) {
        Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
        $Details = if (Test-Path -LiteralPath $DiagnosticErrorLog) {
            Get-Content -LiteralPath $DiagnosticErrorLog -Raw
        } else { "No diagnostic output." }
        throw "Bridge failed to start. Check the COM port and baud rate.`n$Details"
    }
    Write-Host "Started: $($Config.Port) @ $($Config.Baud) baud" -ForegroundColor Green
    Write-Host "Shared endpoint: $($Config.Host):$($Config.TcpPort)"
    Write-Host "PID: $($Running.ProcessId)"
    Write-Host "Serial log: $SerialLog"
}

function Stop-SerialBridge {
    $Running = Get-BridgeProcess
    if ($null -eq $Running) {
        Write-Host "Bridge is not running." -ForegroundColor Yellow
        return
    }
    Stop-Process -Id $Running.ProcessId -Force
    Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped bridge PID $($Running.ProcessId)." -ForegroundColor Green
}

function Show-SerialStatus {
    $Config = Get-SerialConfig
    $Running = Get-BridgeProcess
    Write-Host "Port:       $($Config.Port)"
    Write-Host "Baud:       $($Config.Baud)"
    Write-Host "Endpoint:   $($Config.Host):$($Config.TcpPort)"
    Write-Host "Line ending: $($Config.LineEnding)"
    if ($null -eq $Running) {
        Write-Host "State:      STOPPED" -ForegroundColor Yellow
    } else {
        Write-Host "State:      RUNNING (PID $($Running.ProcessId))" -ForegroundColor Green
    }
}

function Show-SerialPorts {
    $Config = Get-SerialConfig
    Assert-PythonAndPySerial $Config
    Write-Host "Detected serial ports:" -ForegroundColor Cyan
    & $Config.Python -m serial.tools.list_ports -v
}

function Open-SerialTerminal {
    $Config = Get-SerialConfig
    if ($null -eq (Get-BridgeProcess)) { throw "Bridge is stopped. Start it first." }
    Write-Host "Interactive terminal opened. Press Ctrl+C to return to the menu." -ForegroundColor Cyan
    & $Config.Python $BridgePath connect --host $Config.Host --tcp $Config.TcpPort `
        --encoding $Config.Encoding --line-ending $Config.LineEnding
}

function Send-SerialCommand([string]$Text) {
    $Config = Get-SerialConfig
    if ($null -eq (Get-BridgeProcess)) { throw "Bridge is stopped. Start it first." }
    & $Config.Python $BridgePath send $Text --host $Config.Host --tcp $Config.TcpPort `
        --encoding $Config.Encoding --line-ending $Config.LineEnding --newline
    if ($LASTEXITCODE -ne 0) { throw "The command result is uncertain; inspect the terminal or log before retrying." }
}

function Show-Menu {
    while ($true) {
        Clear-Host
        Write-Host "========== Shared Serial Console ==========" -ForegroundColor Cyan
        Show-SerialStatus
        Write-Host ""
        Write-Host "1. Start bridge"
        Write-Host "2. Open interactive terminal"
        Write-Host "3. Send one command"
        Write-Host "4. Stop bridge"
        Write-Host "5. List serial ports"
        Write-Host "6. Edit configuration"
        Write-Host "7. Open log folder"
        Write-Host "0. Exit menu (bridge keeps running)"
        Write-Host ""
        $Choice = Read-Host "Choose"
        try {
            switch ($Choice) {
                "1" { Start-SerialBridge }
                "2" { Open-SerialTerminal }
                "3" { $Text = Read-Host "Command"; Send-SerialCommand $Text }
                "4" { Stop-SerialBridge }
                "5" { Show-SerialPorts }
                "6" { Start-Process notepad.exe -ArgumentList $ConfigPath -Wait }
                "7" { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null; Start-Process explorer.exe $LogDir }
                "0" { return }
                default { Write-Host "Unknown option." -ForegroundColor Yellow }
            }
        }
        catch {
            Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
        }
        if ($Choice -notin @("0", "2", "6", "7")) {
            Write-Host ""
            Read-Host "Press Enter to continue" | Out-Null
        }
    }
}

switch ($Action) {
    "Start"   { Start-SerialBridge }
    "Stop"    { Stop-SerialBridge }
    "Status"  { Show-SerialStatus }
    "Connect" { Open-SerialTerminal }
    "Send"    { if ([string]::IsNullOrWhiteSpace($Command)) { throw "Use -Command to provide text." }; Send-SerialCommand $Command }
    "Ports"   { Show-SerialPorts }
    default   { Show-Menu }
}

