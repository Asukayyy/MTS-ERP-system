@echo off
title BH-ERP Frontend (close this window to stop)

rem Double-click this file to start the frontend. The browser opens automatically.
rem The frontend also needs the backend running: double-click the backend script too.
rem NOTE: keep this file plain ASCII - non-ASCII text breaks cmd parsing
rem       under the default GBK code page.

cd /d "%~dp0..\frontend"

echo ============================================
echo   BH-ERP Frontend
echo ============================================
echo.

rem ---- Guard: refuse to start a second copy on the same port ----
netstat -ano | findstr ":5173" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [WARN] Port 5173 is already in use.
    echo        The frontend is probably ALREADY RUNNING in another window.
    echo.
    echo        Opening http://localhost:5173 in your browser ...
    echo        To restart: close that other window first, then run this file again.
    echo.
    start "" "http://localhost:5173"
    pause
    exit /b 0
)

if not exist "node_modules" (
    echo [Setup] node_modules not found. Installing dependencies, please wait ...
    call npm install
    if errorlevel 1 (
        echo.
        echo [ERROR] Failed to install dependencies.
        echo         Install Node.js 18+ and make sure "npm" is on PATH.
        echo         See docs\development\getting-started.md
        echo.
        pause
        exit /b 1
    )
    echo.
)

echo Frontend: http://localhost:5173
echo.
echo The browser will open automatically once the server is ready.
echo If it does not, open the address above manually.
echo Close this window to stop the frontend.
echo.

rem Open the browser after 8 seconds (hidden window, does not block this one)
rem Use "localhost", NOT "127.0.0.1": Vite binds localhost only by default.
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 8; Start-Process 'http://localhost:5173'"

call npm run dev

echo.
echo [Done] Frontend stopped.
pause
