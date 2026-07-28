@echo off
title NetApp Active IQ TAM Dashboard
echo ===================================================
echo   NetApp Active IQ TAM Dashboard
echo ===================================================
echo.

:: Kill any existing server on port 8080
echo Checking for existing server processes...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8080" ^| findstr "LISTENING" 2^>nul') do (
    echo   Stopping old server process PID %%a...
    taskkill /F /PID %%a >nul 2>&1
)

:: Small delay to let the port release
timeout /t 1 /nobreak >nul

echo.
echo Starting server on http://localhost:8080 ...
echo Keep this window open while using the dashboard.
echo Press Ctrl+C to stop the server.
echo.

:: Start server then open browser
start "" http://localhost:8080
python server.py
pause
