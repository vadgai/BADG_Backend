@echo off
REM ============================================
REM Quick Redeploy Script for VADG Backend
REM ============================================
REM This script redeploys your backend to Google Cloud Run
REM using existing secrets and configuration

echo.
echo ============================================
echo   VADG Backend Redeployment
echo ============================================
echo.
echo This will redeploy your backend with the latest code changes.
echo.
echo Prerequisites:
echo   - Google Cloud SDK installed (gcloud)
echo   - Already authenticated (gcloud auth login)
echo   - Backend previously deployed
echo.
echo Time: ~3-5 minutes
echo Cost: FREE (within free tier)
echo.

pause

echo.
echo [1/4] Checking gcloud installation...
gcloud --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Google Cloud SDK not found!
    echo.
    echo Please install it from:
    echo https://cloud.google.com/sdk/docs/install
    echo.
    pause
    exit /b 1
)
echo   ✓ gcloud is installed

echo.
echo [2/4] Checking authentication...
gcloud auth list --filter=status:ACTIVE --format="value(account)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Not authenticated with Google Cloud!
    echo.
    echo Please run: gcloud auth login
    echo.
    pause
    exit /b 1
)
echo   ✓ Authenticated

echo.
echo [3/4] Getting current project...
for /f "tokens=*" %%i in ('gcloud config get-value project 2^>nul') do set PROJECT_ID=%%i
if "%PROJECT_ID%"=="" (
    echo.
    echo ERROR: No project set!
    echo.
    echo Please set your project:
    echo   gcloud config set project YOUR_PROJECT_ID
    echo.
    pause
    exit /b 1
)
echo   ✓ Project: %PROJECT_ID%

echo.
echo [4/4] Deploying to Cloud Run...
echo.
echo Service: vadg-backend
echo Region: asia-south1
echo.
echo This will take 3-5 minutes...
echo.

REM Change to Backend directory if not already there
cd /d "%~dp0"

REM Deploy using gcloud
gcloud run deploy vadg-backend ^
  --region=asia-south1 ^
  --source . ^
  --platform=managed ^
  --allow-unauthenticated ^
  --max-instances=20 ^
  --min-instances=0 ^
  --memory=1Gi ^
  --cpu=1 ^
  --timeout=300 ^
  --port=8080 ^
  --quiet

if errorlevel 1 (
    echo.
    echo ============================================
    echo   ❌ DEPLOYMENT FAILED!
    echo ============================================
    echo.
    echo Troubleshooting:
    echo   1. Check billing is enabled
    echo   2. Check logs:
    echo      gcloud run services logs read vadg-backend --region=asia-south1
    echo   3. Try manual deployment:
    echo      gcloud run deploy vadg-backend --region=asia-south1 --source .
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   ✅ DEPLOYMENT SUCCESSFUL!
echo ============================================
echo.

REM Get the service URL
for /f "tokens=*" %%i in ('gcloud run services describe vadg-backend --region^=asia-south1 --format^="value(status.url)"') do set SERVICE_URL=%%i

echo Your backend is now live at:
echo   %SERVICE_URL%
echo.
echo Next Steps:
echo.
echo 1. Test the endpoint:
echo    %SERVICE_URL%/docs
echo    (Look for: GET /api/admin/report-analyzer-submissions)
echo.
echo 2. Test your frontend:
echo    https://vadg.in/admin/report-analyzer
echo    (The 404 error should be fixed!)
echo.
echo 3. Verify health:
echo    %SERVICE_URL%/health
echo.
echo ============================================
echo.

pause

