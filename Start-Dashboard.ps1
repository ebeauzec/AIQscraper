<#
.SYNOPSIS
    NetApp Active IQ TAM Dashboard Launcher (PowerShell)
.DESCRIPTION
    Stops any existing server on port 8080, starts server.py,
    and opens the dashboard in your default browser.
.NOTES
    Usage:  .\Start-Dashboard.ps1
    Stop:   Press Ctrl+C or close this window
#>

$Port = 8080
$Host.UI.RawUI.WindowTitle = "NetApp Active IQ TAM Dashboard"

Write-Host ""
Write-Host "  =================================================" -ForegroundColor Cyan
Write-Host "    NetApp Active IQ TAM Dashboard" -ForegroundColor White
Write-Host "  =================================================" -ForegroundColor Cyan
Write-Host ""

# --- Kill any existing server on the port ---
Write-Host "[1/3] Checking for existing processes on port $Port..." -ForegroundColor Yellow
$existing = netstat -ano | Select-String ":$Port" | Select-String "LISTENING"
if ($existing) {
    foreach ($line in $existing) {
        $pid = ($line -split '\s+')[-1]
        if ($pid -match '^\d+$') {
            Write-Host "  Stopping old server (PID $pid)..." -ForegroundColor DarkYellow
            try { Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue } catch {}
            try { taskkill /F /PID $pid 2>$null | Out-Null } catch {}
        }
    }
    Start-Sleep -Seconds 1
    Write-Host "  Old processes cleared." -ForegroundColor Green
} else {
    Write-Host "  Port $Port is free." -ForegroundColor Green
}

# --- Verify Python is available ---
Write-Host "[2/3] Checking Python..." -ForegroundColor Yellow
try {
    $pyVer = python --version 2>&1
    Write-Host "  $pyVer" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: Python not found. Install Python 3.8+ from python.org" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# --- Start the server ---
Write-Host "[3/3] Starting server..." -ForegroundColor Yellow
Write-Host ""
Write-Host "  Dashboard URL:  http://localhost:$Port" -ForegroundColor Cyan
Write-Host "  Press Ctrl+C to stop the server." -ForegroundColor DarkGray
Write-Host ""

# Open browser after short delay
Start-Job -ScriptBlock {
    Start-Sleep -Seconds 2
    Start-Process "http://localhost:8080"
} | Out-Null

# Run server (blocks until Ctrl+C)
Set-Location $PSScriptRoot
python server.py
