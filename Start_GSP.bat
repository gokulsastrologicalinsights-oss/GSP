@echo off
setlocal
title Gokul Social Publisher (GSP)
cd /d "%~dp0"

echo ============================================
echo   Gokul Social Publisher (GSP) - Launcher
echo ============================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    pause
    exit /b 1
)

echo Checking dependencies...
python -c "import fastapi, uvicorn" >nul 2>nul
if %errorlevel% neq 0 (
    echo Installing required Python packages...
    python -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install requirements.
        pause
        exit /b 1
    )
)

echo.
echo Starting GSP server on http://127.0.0.1:8088 ...
echo Press Ctrl+C in this window to stop the server.
echo.

start "" http://127.0.0.1:8088
python -m uvicorn main:app --host 127.0.0.1 --port 8088

pause
