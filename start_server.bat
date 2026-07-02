@echo off
echo ========================================
echo Starting VADG Backend Server
echo ========================================
echo.

cd /d "%~dp0"

echo Checking Python installation...
python --version
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    pause
    exit /b 1
)

echo.
echo Checking if uvicorn is installed...
python -c "import uvicorn; print('Uvicorn installed')"
if errorlevel 1 (
    echo ERROR: uvicorn is not installed
    echo Installing uvicorn...
    pip install uvicorn
)

echo.
echo Starting server on http://0.0.0.0:8080...
echo WebSocket endpoint: ws://localhost:8080/followup/{session_id}
echo.
echo Press Ctrl+C to stop the server
echo.

uvicorn app:app --host 0.0.0.0 --port 8080 --reload

