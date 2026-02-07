@echo off
echo ================================================
echo Restarting VADG Backend
echo ================================================
echo.
echo Stopping any running backend processes...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *app.py*" 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *uvicorn*" 2>nul
timeout /t 2 /nobreak >nul

echo.
echo Starting backend...
echo.
python app.py














