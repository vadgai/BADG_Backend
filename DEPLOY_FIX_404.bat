@echo off
REM ============================================
REM Fix 404 Error - Deploy Backend Now
REM ============================================

echo.
echo ============================================
echo   Deploying Backend to Fix 404 Error
echo ============================================
echo.
echo This will deploy your latest code to Cloud Run
echo Time: 3-5 minutes
echo.

cd /d "%~dp0"

echo [1/2] Deploying to Cloud Run (asia-east1)...
echo.

gcloud run deploy vadg-backend ^
  --region=asia-east1 ^
  --source . ^
  --platform=managed ^
  --allow-unauthenticated ^
  --quiet

if errorlevel 1 (
    echo.
    echo ============================================
    echo   Deployment to asia-east1 failed
    echo   Trying asia-south1...
    echo ============================================
    echo.
    
    gcloud run deploy vadg-backend ^
      --region=asia-south1 ^
      --source . ^
      --platform=managed ^
      --allow-unauthenticated ^
      --quiet
)

if errorlevel 1 (
    echo.
    echo ============================================
    echo   ❌ DEPLOYMENT FAILED!
    echo ============================================
    echo.
    echo Please check:
    echo 1. Are you authenticated? Run: gcloud auth login
    echo 2. Is billing enabled?
    echo 3. Check logs: gcloud run services logs read vadg-backend
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   ✅ DEPLOYMENT SUCCESSFUL!
echo ============================================
echo.
echo Your backend has been updated!
echo.
echo Next: Test the endpoint
echo   https://vadg-backend-ld6xrzhwvq-el.a.run.app/docs
echo.
echo Then visit: https://vadg.in/admin/report-analyzer
echo   The 404 error should be fixed!
echo.

pause

