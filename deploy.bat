@echo off
REM ============================================
REM VADG Backend Deployment Script for Windows
REM For Google Cloud Run
REM ============================================
REM Usage: deploy.bat YOUR_GOOGLE_API_KEY [OPTIONS]
REM 
REM Examples:
REM   deploy.bat AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
REM   deploy.bat YOUR_KEY --mongo-uri "mongodb+srv://..."
REM   deploy.bat YOUR_KEY --email your@gmail.com --email-pass app_password
REM ============================================

SETLOCAL EnableDelayedExpansion

echo.
echo ============================================
echo 🚀 VADG Backend Deployment to Google Cloud Run
echo ============================================
echo.

REM Check if API key is provided
if "%~1"=="" (
    echo ❌ Error: Google API Key not provided
    echo.
    echo Usage: deploy.bat YOUR_GOOGLE_API_KEY [OPTIONS]
    echo.
    echo Required:
    echo   YOUR_GOOGLE_API_KEY    Google Gemini API key
    echo.
    echo Optional flags:
    echo   --mongo-uri URI        MongoDB connection string
    echo   --email EMAIL          Sender email for contact form
    echo   --email-pass PASS      Email password (Gmail app password^)
    echo   --region REGION        GCP region (default: asia-south1^)
    echo   --project PROJECT      GCP project ID (auto-detect if not set^)
    echo   --service-name NAME    Service name (default: vadg-backend^)
    echo   --skip-secrets         Skip Secret Manager setup
    echo.
    echo Examples:
    echo   deploy.bat AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
    echo   deploy.bat YOUR_KEY --mongo-uri "mongodb+srv://user:pass@cluster.net/"
    echo   deploy.bat YOUR_KEY --email your@gmail.com --email-pass app_password
    pause
    exit /b 1
)

REM Required parameters
set GOOGLE_API_KEY=%~1
shift

REM Default values
set SERVICE_NAME=vadg-backend
set REGION=asia-south1
set MONGO_URI=
set SENDER_EMAIL=
set SENDER_PASSWORD=
set SKIP_SECRETS=false

REM Get project ID
for /f "delims=" %%i in ('gcloud config get-value project 2^>nul') do set PROJECT_ID=%%i

REM Parse optional arguments
:parse_args
if "%~1"=="" goto end_parse_args

if "%~1"=="--mongo-uri" (
    set MONGO_URI=%~2
    shift
    shift
    goto parse_args
)

if "%~1"=="--email" (
    set SENDER_EMAIL=%~2
    shift
    shift
    goto parse_args
)

if "%~1"=="--email-pass" (
    set SENDER_PASSWORD=%~2
    shift
    shift
    goto parse_args
)

if "%~1"=="--region" (
    set REGION=%~2
    shift
    shift
    goto parse_args
)

if "%~1"=="--project" (
    set PROJECT_ID=%~2
    shift
    shift
    goto parse_args
)

if "%~1"=="--service-name" (
    set SERVICE_NAME=%~2
    shift
    shift
    goto parse_args
)

if "%~1"=="--skip-secrets" (
    set SKIP_SECRETS=true
    shift
    goto parse_args
)

echo ❌ Unknown option: %~1
pause
exit /b 1

:end_parse_args

REM Validate project ID
if "%PROJECT_ID%"=="" (
    echo ❌ Error: Could not detect GCP project ID
    echo Please set it with: gcloud config set project YOUR_PROJECT_ID
    echo Or use: deploy.bat YOUR_KEY --project YOUR_PROJECT_ID
    pause
    exit /b 1
)

echo.
echo 📋 Configuration Summary:
echo    Project ID:  %PROJECT_ID%
echo    Service:     %SERVICE_NAME%
echo    Region:      %REGION%
if not "%MONGO_URI%"=="" (
    echo    MongoDB:     Configured
) else (
    echo    MongoDB:     Not configured (in-memory mode^)
)
if not "%SENDER_EMAIL%"=="" (
    echo    Email:       Configured (%SENDER_EMAIL%^)
) else (
    echo    Email:       Not configured
)
echo.

REM Validate gcloud is authenticated
gcloud auth list --filter=status:ACTIVE --format="value(account)" >nul 2>&1
if errorlevel 1 (
    echo ❌ Error: Not authenticated with gcloud
    echo Please run: gcloud auth login
    pause
    exit /b 1
)

REM Set project
echo 🔧 Setting project...
gcloud config set project %PROJECT_ID%

REM Enable required APIs
echo.
echo 🔌 Step 1/5: Enabling required APIs...
gcloud services enable run.googleapis.com --quiet
gcloud services enable containerregistry.googleapis.com --quiet
gcloud services enable cloudbuild.googleapis.com --quiet

if "%SKIP_SECRETS%"=="false" (
    if not "%MONGO_URI%"=="" (
        gcloud services enable secretmanager.googleapis.com --quiet
    )
    if not "%SENDER_EMAIL%"=="" (
        gcloud services enable secretmanager.googleapis.com --quiet
    )
)

echo ✅ APIs enabled

REM Create secrets if needed
if "%SKIP_SECRETS%"=="false" (
    echo.
    echo 🔐 Step 2/5: Setting up Secret Manager...
    
    REM Create Google API Key secret
    echo %GOOGLE_API_KEY% | gcloud secrets create google-api-key --data-file=- 2>nul
    if errorlevel 1 (
        echo 📝 Updating existing secret: google-api-key
        echo %GOOGLE_API_KEY% | gcloud secrets versions add google-api-key --data-file=-
    ) else (
        echo ✅ Created secret: google-api-key
    )
    
    REM Create MongoDB URI secret if provided
    if not "%MONGO_URI%"=="" (
        echo %MONGO_URI% | gcloud secrets create mongo-uri --data-file=- 2>nul
        if errorlevel 1 (
            echo 📝 Updating existing secret: mongo-uri
            echo %MONGO_URI% | gcloud secrets versions add mongo-uri --data-file=-
        ) else (
            echo ✅ Created secret: mongo-uri
        )
    )
    
    REM Create email password secret if provided
    if not "%SENDER_PASSWORD%"=="" (
        echo %SENDER_PASSWORD% | gcloud secrets create email-password --data-file=- 2>nul
        if errorlevel 1 (
            echo 📝 Updating existing secret: email-password
            echo %SENDER_PASSWORD% | gcloud secrets versions add email-password --data-file=-
        ) else (
            echo ✅ Created secret: email-password
        )
    )
    
    echo ✅ Secrets configured
)

REM Build environment variables
set ENV_VARS=ALLOWED_ORIGINS=https://vadg.netlify.app,https://www.vadg.in,https://vadg.in,http://localhost:5173,http://localhost:5174
set ENV_VARS=%ENV_VARS%,LOG_LEVEL=INFO
set ENV_VARS=%ENV_VARS%,ENVIRONMENT=production
set ENV_VARS=%ENV_VARS%,PORT=8080

if not "%SENDER_EMAIL%"=="" (
    set ENV_VARS=%ENV_VARS%,SENDER_EMAIL=%SENDER_EMAIL%
    set ENV_VARS=%ENV_VARS%,SMTP_SERVER=smtp.gmail.com
    set ENV_VARS=%ENV_VARS%,SMTP_PORT=587
    set ENV_VARS=%ENV_VARS%,RECIPIENT_EMAILS=vadg.office@gmail.com
)

REM Build secrets mapping
set SECRET_ARGS=
if "%SKIP_SECRETS%"=="false" (
    set SECRET_ARGS=--set-secrets=GOOGLE_API_KEY=google-api-key:latest
    
    if not "%MONGO_URI%"=="" (
        set SECRET_ARGS=!SECRET_ARGS!,MONGO_URI=mongo-uri:latest
    )
    
    if not "%SENDER_PASSWORD%"=="" (
        set SECRET_ARGS=!SECRET_ARGS!,SENDER_PASSWORD=email-password:latest
    )
) else (
    set ENV_VARS=%ENV_VARS%,GOOGLE_API_KEY=%GOOGLE_API_KEY%
    if not "%MONGO_URI%"=="" (
        set ENV_VARS=!ENV_VARS!,MONGO_URI=%MONGO_URI%
    )
    if not "%SENDER_PASSWORD%"=="" (
        set ENV_VARS=!ENV_VARS!,SENDER_PASSWORD=%SENDER_PASSWORD%
    )
)

REM Deploy the service
echo.
echo 📦 Step 3/5: Deploying to Cloud Run...
echo This may take 3-5 minutes...
echo.

gcloud run deploy %SERVICE_NAME% ^
  --region=%REGION% ^
  --source . ^
  --platform=managed ^
  --allow-unauthenticated ^
  --set-env-vars="%ENV_VARS%" ^
  %SECRET_ARGS% ^
  --max-instances=20 ^
  --min-instances=0 ^
  --memory=1Gi ^
  --cpu=1 ^
  --timeout=300 ^
  --port=8080 ^
  --quiet

if errorlevel 1 (
    echo.
    echo ❌ Deployment failed!
    echo.
    echo Troubleshooting:
    echo 1. Check if you have billing enabled: https://console.cloud.google.com/billing
    echo 2. Verify your API key is valid
    echo 3. Check logs: gcloud run services logs read %SERVICE_NAME% --region=%REGION%
    pause
    exit /b 1
)

echo.
echo ✅ Service deployed successfully

REM Enable public access
echo.
echo 🌐 Step 4/5: Configuring public access...
gcloud run services add-iam-policy-binding %SERVICE_NAME% ^
  --region=%REGION% ^
  --member="allUsers" ^
  --role="roles/run.invoker" ^
  --quiet

echo ✅ Public access enabled

REM Get service URL
echo.
echo 🔍 Step 5/5: Verifying deployment...
for /f "delims=" %%i in ('gcloud run services describe %SERVICE_NAME% --region=%REGION% --format="value(status.url)"') do set SERVICE_URL=%%i

REM Test the deployment
echo Testing health endpoint...
curl -f -s "%SERVICE_URL%/health" >nul 2>&1
if errorlevel 1 (
    echo ⚠️  Warning: Health check failed (service might still be starting^)
) else (
    echo ✅ Health check passed
)

echo.
echo ============================================
echo ✅ DEPLOYMENT COMPLETE!
echo ============================================
echo.
echo 🎉 Your VADG backend is live at:
echo    %SERVICE_URL%
echo.
echo 📊 Service Information:
echo    Project:  %PROJECT_ID%
echo    Service:  %SERVICE_NAME%
echo    Region:   %REGION%
echo    URL:      %SERVICE_URL%
echo.
echo 📝 Important Next Steps:
echo.
echo 1. 🧪 Test Your Backend:
echo    Health check:    curl %SERVICE_URL%/health
echo    API docs:        Open %SERVICE_URL%/docs in browser
echo.
echo 2. 🔧 Update Your Frontend:
echo    Add to Frontend/.env or Netlify environment:
echo    VITE_API_BASE_URL=%SERVICE_URL%
echo    VITE_WS_BASE_URL=%SERVICE_URL:https=wss%
echo.
echo 3. 🔐 Security Status:
if "%SKIP_SECRETS%"=="true" (
    echo    ⚠️  Using --skip-secrets (less secure^)
) else (
    echo    ✅ Secrets stored in Secret Manager
)
if not "%MONGO_URI%"=="" (
    echo    ✅ MongoDB configured
) else (
    echo    ⚠️  No MongoDB (in-memory storage^)
)
if not "%SENDER_EMAIL%"=="" (
    echo    ✅ Email notifications configured
) else (
    echo    ℹ️  Email not configured
)
echo.
echo 4. 📊 Monitor Your Service:
echo    Logs:    gcloud run services logs read %SERVICE_NAME% --region=%REGION%
echo    Console: https://console.cloud.google.com/run?project=%PROJECT_ID%
echo.
echo 💰 Estimated Cost:
echo    First 2 million requests/month: FREE
echo.
echo 🎊 Happy deploying!
echo ============================================
echo.
pause
