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
where cloudflared >nul 2>nul
if %errorlevel% equ 0 (
    echo Starting Cloudflare Tunnel for Instagram Reels...
    if exist cloudflared.log del /f /q cloudflared.log >nul 2>nul
    start /min "GSP Cloudflare Tunnel" cmd /c "cloudflared tunnel --url http://127.0.0.1:8088 > cloudflared.log 2>&1"
    python -c "import re, time, os, database; pat = re.compile(r'https://[a-z0-9-]+\.trycloudflare\.com'); url = None; [ (url := pat.search(open('cloudflared.log', encoding='utf-8', errors='ignore').read()).group(0)) if os.path.exists('cloudflared.log') and pat.search(open('cloudflared.log', encoding='utf-8', errors='ignore').read()) else time.sleep(0.5) for _ in range(30) if not url ]; database.set_setting('public_media_base_url', url) if url else None; print('[OK] Tunnel URL saved:', url) if url else print('[WARN] Tunnel URL not detected yet; check cloudflared.log')"
) else (
    echo [WARN] cloudflared not found in PATH. Facebook and YouTube will work; Instagram Reels requires cloudflared.
)

echo.
echo Starting GSP server on http://127.0.0.1:8088 ...
echo Press Ctrl+C in this window to stop the server.
echo.

start "" http://127.0.0.1:8088
python -m uvicorn main:app --host 127.0.0.1 --port 8088

taskkill /FI "WINDOWTITLE eq GSP Cloudflare Tunnel*" /T /F >nul 2>nul
pause
