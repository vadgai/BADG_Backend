@echo off
REM VADG Backend Local Development Server Startup Script
REM This script helps you start the backend server quickly

echo ================================================
echo  VADG Backend - Local Development Server
echo ================================================
echo.

REM Check if .env file exists
if not exist .env (
    echo [WARNING] .env file not found!
    echo.
    echo Please create a .env file with your Google Gemini API key:
    echo.
    echo 1. Copy .env.example to .env
    echo 2. Add your API key: GOOGLE_API_KEY=your_key_here
    echo 3. Get API key from: https://makersuite.google.com/app/apikey
    echo.
    pause
    exit /b 1
)

REM Check if virtual environment exists
if not exist venv\ (
    echo [INFO] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
)

REM Activate virtual environment
echo [INFO] Activating virtual environment...
call venv\Scripts\activate.bat

REM Check if dependencies are installed
python -c "import fastapi" 2>nul
if errorlevel 1 (
    echo [INFO] Installing dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies
        pause
        exit /b 1
    )
)

echo.
echo [SUCCESS] Starting VADG backend server...
echo.
echo Server will be available at:
echo   - API: http://localhost:8080
echo   - Docs: http://localhost:8080/docs
echo   - WebSocket: ws://localhost:8080/followup/{session_id}
echo.
echo Press Ctrl+C to stop the server
echo.

REM Start the server
uvicorn app:app --reload --host 0.0.0.0 --port 8080

