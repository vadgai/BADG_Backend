@echo off
REM Quick script to check Cloud Run logs

echo Fetching latest logs for vadg-backend...
echo.

gcloud run services logs read vadg-backend ^
  --region=asia-south1 ^
  --limit=100 ^
  --format="table(timestamp,severity,textPayload)"

echo.
echo Press any key to see ERROR logs only...
pause >nul

echo.
echo ============================================
echo ERROR LOGS ONLY:
echo ============================================
gcloud run services logs read vadg-backend ^
  --region=asia-south1 ^
  --limit=50 ^
  --filter="severity>=ERROR"

echo.
pause



