@echo off
title NetApp Active IQ Dashboard Launcher
echo ===================================================
echo   NetApp Active IQ Dashboard Web Server Launcher
echo ===================================================
echo.
echo Launching browser at http://localhost:8080...
start "" http://localhost:8080
echo.
echo Starting Python web server on port 8080 to bypass CORS...
echo Keep this window open while using the dashboard.
echo Press Ctrl+C in this window to stop the server.
echo.
python -m http.server 8080
pause
