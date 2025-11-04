@echo off
cls
echo ============================================================
echo   VADG BACKEND SERVER - Starting...
echo ============================================================
echo.

REM Check if .env exists
if not exist .env (
    echo [ERROR] .env file not found!
    echo.
    echo Please create Backend\.env with:
    echo   GOOGLE_API_KEY=your_api_key_here
    echo   ALLOWED_ORIGINS=http://localhost:5173
    echo.
    echo Get API key from: https://makersuite.google.com/app/apikey
    echo.
    pause
    exit /b 1
)

echo [INFO] Checking Python...
python --version
if errorlevel 1 (
    echo [ERROR] Python not found!
    pause
    exit /b 1
)
echo.

echo [INFO] Installing/updating dependencies...
python -m pip install --quiet fastapi uvicorn "uvicorn[standard]" google-generativeai python-dotenv langchain groq pydantic python-multipart motor pymongo 2>nul
echo [OK] Dependencies ready
echo.

echo ============================================================
echo   BACKEND SERVER STARTING ON http://localhost:8000
echo ============================================================
echo.
echo API Documentation: http://localhost:8000/docs
echo Health Check: http://localhost:8000/
echo.
echo Keep this window OPEN while using the app!
echo Press Ctrl+C to stop the server
echo.
echo ============================================================
echo.

python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload

echo.
echo [INFO] Backend server stopped.
pause

