@echo off
REM Quick redeploy script for Windows
REM This script uses --source . to automatically build in the current project
REM No need to manually build/push Docker images!

REM Get current project
for /f "delims=" %%i in ('gcloud config get-value project 2^>nul') do set PROJECT_ID=%%i

if "%PROJECT_ID%"=="" (
    echo ❌ Error: No GCP project set
    echo Please run: gcloud config set project YOUR_PROJECT_ID
    exit /b 1
)

echo.
echo ============================================
echo 🚀 Quick Redeploy to Cloud Run
echo ============================================
echo.
echo 📋 Project: %PROJECT_ID%
echo 📍 Region: asia-south1
echo.
echo 🔨 Building and deploying (this may take 3-5 minutes)...
echo.

REM Deploy using --source . which automatically builds in the correct project
gcloud run deploy vadg-backend ^
  --source . ^
  --platform managed ^
  --region asia-south1 ^
  --allow-unauthenticated ^
  --quiet

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ❌ Deployment failed!
    echo.
    echo 💡 Troubleshooting:
    echo    1. Make sure you're authenticated: gcloud auth login
    echo    2. Check your project: gcloud config get-value project
    echo    3. Ensure billing is enabled for this project
    echo    4. Check logs: gcloud run services logs read vadg-backend --region asia-south1 --limit 50
    exit /b 1
)

echo.
echo ✅ Deployment complete!
echo.
echo 📋 Next steps:
echo    1. Check logs: gcloud run services logs read vadg-backend --region asia-south1 --limit 50
echo    2. Get service URL: gcloud run services describe vadg-backend --region asia-south1 --format="value(status.url)"
echo    3. Test the service: curl https://YOUR_SERVICE_URL/health
echo.







