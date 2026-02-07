@echo off
REM Quick fix and redeploy script

echo.
echo ============================================
echo 🔧 Fixing and Redeploying VADG Backend
echo ============================================
echo.

REM Check if API key is provided
if "%~1"=="" (
    echo ❌ Error: Please provide your Google API Key
    echo.
    echo Usage: FIX_AND_REDEPLOY.bat YOUR_GOOGLE_API_KEY
    echo.
    pause
    exit /b 1
)

set GOOGLE_API_KEY=%~1
set MONGO_URI=mongodb+srv://vadg_db_user:Yh96u81FmZucN6p8@cluster0.zyu50c9.mongodb.net/
set PROJECT_ID=positive-shell-475102-t5
set SERVICE_NAME=vadg-backend
set REGION=asia-south1

echo 📋 Configuration:
echo    Project: %PROJECT_ID%
echo    Service: %SERVICE_NAME%
echo    Region:  %REGION%
echo.

echo 🔧 Step 1: Setting project...
gcloud config set project %PROJECT_ID%

echo.
echo 🔐 Step 2: Updating secrets...
echo %GOOGLE_API_KEY% | gcloud secrets versions add google-api-key --data-file=- 2>nul || echo %GOOGLE_API_KEY% | gcloud secrets create google-api-key --data-file=-
echo %MONGO_URI% | gcloud secrets versions add mongo-uri --data-file=- 2>nul || echo %MONGO_URI% | gcloud secrets create mongo-uri --data-file=-

echo.
echo 📦 Step 3: Deploying with fixed Dockerfile...
echo This will take 3-5 minutes...
echo.

gcloud run deploy %SERVICE_NAME% ^
  --region=%REGION% ^
  --source . ^
  --platform=managed ^
  --allow-unauthenticated ^
  --set-env-vars="ALLOWED_ORIGINS=https://vadg.netlify.app,https://www.vadg.in,https://vadg.in,http://localhost:5173,http://localhost:5174,LOG_LEVEL=INFO,ENVIRONMENT=production,PORT=8080" ^
  --set-secrets="GOOGLE_API_KEY=google-api-key:latest,MONGO_URI=mongo-uri:latest" ^
  --max-instances=20 ^
  --min-instances=0 ^
  --memory=2Gi ^
  --cpu=2 ^
  --timeout=600 ^
  --port=8080 ^
  --quiet

if errorlevel 1 (
    echo.
    echo ❌ Deployment failed!
    echo.
    echo Checking logs...
    gcloud run services logs read %SERVICE_NAME% --region=%REGION% --limit=30
    echo.
    pause
    exit /b 1
)

echo.
echo ✅ Deployment successful!

echo.
echo 🌐 Step 4: Ensuring public access...
gcloud run services add-iam-policy-binding %SERVICE_NAME% ^
  --region=%REGION% ^
  --member="allUsers" ^
  --role="roles/run.invoker" ^
  --quiet

echo.
echo 🔍 Step 5: Getting service URL...
for /f "delims=" %%i in ('gcloud run services describe %SERVICE_NAME% --region=%REGION% --format="value(status.url)"') do set SERVICE_URL=%%i

echo.
echo ============================================
echo ✅ DEPLOYMENT COMPLETE!
echo ============================================
echo.
echo 🎉 Your backend is live at:
echo    %SERVICE_URL%
echo.
echo 🧪 Testing...
timeout /t 5 /nobreak >nul
curl -s "%SERVICE_URL%/health"
echo.
echo.
echo 📝 Next steps:
echo 1. Update Frontend/.env with:
echo    VITE_API_BASE_URL=%SERVICE_URL%
echo    VITE_WS_BASE_URL=%SERVICE_URL:https=wss%
echo.
echo 2. View logs: gcloud run services logs read %SERVICE_NAME% --region=%REGION%
echo.
pause

