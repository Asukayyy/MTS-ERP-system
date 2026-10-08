@echo off
title BH-ERP Backend (close this window to stop)

rem Double-click this file to start the backend.
rem First run creates the virtualenv and installs dependencies automatically.
rem NOTE: keep this file plain ASCII - non-ASCII text breaks cmd parsing
rem       under the default GBK code page.

cd /d "%~dp0..\backend"

echo ============================================
echo   BH-ERP Backend
echo ============================================
echo.

rem ---- Guard: refuse to start a second copy on the same port ----
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [WARN] Port 8000 is already in use.
    echo        The backend is probably ALREADY RUNNING in another window.
    echo.
    echo        Check it  : http://127.0.0.1:8000/docs
    echo        To restart: close that other window first, then run this file again.
    echo.
    echo        This window will not start a second copy.
    pause
    exit /b 0
)

if not exist ".venv\Scripts\python.exe" (
    echo [Setup] Virtualenv not found. Creating one ...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo [ERROR] Failed to create virtualenv.
        echo         Install Python 3.10+ and make sure "python" is on PATH.
        echo         See docs\development\getting-started.md
        echo.
        pause
        exit /b 1
    )
    echo [Setup] Installing dependencies. This may take a few minutes ...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [ERROR] Failed to install dependencies. Check your network and retry.
        echo.
        pause
        exit /b 1
    )
    echo.
)

if not exist ".env" (
    copy ".env.example" ".env" > nul
    echo [Setup] .env not found. Copied from .env.example.
    echo [IMPORTANT] Open backend\.env and fill in your database settings
    echo             ^(DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD^),
    echo             then double-click this script again.
    echo.
    pause
    exit /b 1
)

echo Backend : http://127.0.0.1:8000
echo API docs: http://127.0.0.1:8000/docs
echo.
echo Close this window to stop the backend.
echo.

".venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port 8000

echo.
echo [Done] Backend stopped.
pause
