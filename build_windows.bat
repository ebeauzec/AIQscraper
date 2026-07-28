@echo off
setlocal enabledelayedexpansion

title NetApp AIQ Advisor - Windows Build

echo.
echo ================================================================
echo   NetApp Active IQ Advisor - Windows Desktop App Builder
echo ================================================================
echo.
echo This script packages the dashboard into a self-contained Windows
echo executable. No browser or Python required on target machines.
echo.

:: -------------------------------------------------------------------
:: 1. Check Python is available
:: -------------------------------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found on PATH.
    echo         Install Python 3.9+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER% detected.
echo.

:: -------------------------------------------------------------------
:: 2. Install / upgrade required packages
:: -------------------------------------------------------------------
echo [1/4] Installing build dependencies...
echo       (pywebview, pyinstaller, pythonnet)
echo.
pip install --upgrade pywebview pyinstaller pythonnet pywin32 ^
    --quiet --no-warn-script-location
if errorlevel 1 (
    echo [ERROR] pip install failed. Check your internet connection.
    pause
    exit /b 1
)
echo [OK] Dependencies installed.
echo.

:: -------------------------------------------------------------------
:: 3. Clean previous build artefacts
:: -------------------------------------------------------------------
echo [2/4] Cleaning previous build output...
if exist "build\"  rmdir /s /q "build"
if exist "dist\"   rmdir /s /q "dist"
echo [OK] Cleaned.
echo.

:: -------------------------------------------------------------------
:: 4. Run PyInstaller
:: -------------------------------------------------------------------
echo [3/4] Building Windows executable with PyInstaller...
echo.
pyinstaller AIQscraper.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller build failed. See output above for details.
    pause
    exit /b 1
)
echo.
echo [OK] Build complete.
echo.

:: -------------------------------------------------------------------
:: 5. Report output location
:: -------------------------------------------------------------------
echo [4/4] Packaging complete!
echo.
echo ================================================================
echo   Output location:
echo   dist\NetApp_AIQ_Advisor\NetApp_AIQ_Advisor.exe
echo.
echo   Distribute the entire dist\NetApp_AIQ_Advisor\ folder.
echo   Users double-click NetApp_AIQ_Advisor.exe to launch.
echo.
echo   NOTE: Target Windows machines must have the WebView2 Runtime
echo   installed. It is pre-installed on Windows 10 (1803+) and
echo   Windows 11. Download for older systems:
echo   https://developer.microsoft.com/en-us/microsoft-edge/webview2/
echo ================================================================
echo.
pause