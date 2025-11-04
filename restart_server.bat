@echo off
echo ========================================
echo Restarting VADG Backend Server
echo ========================================
echo.

cd /d "%~dp0"

echo Stopping all Python processes...
taskkill /F /IM python.exe 2>nul
if errorlevel 1 (
    echo No Python processes to kill
) else (
    echo Python processes stopped
)

echo.
echo Waiting 2 seconds...
ping 127.0.0.1 -n 3 >nul

echo.
echo Starting fresh backend server...
echo Model updated to: gemini-1.5-flash-latest
echo.

start "VADG Backend" uvicorn app:app --host 0.0.0.0 --port 8000 --reload

echo.
echo ========================================
echo Backend server starting in new window
echo Check the new window for logs
echo ========================================
echo.
pause

