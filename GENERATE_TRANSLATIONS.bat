@echo off
REM ============================================
REM Generate Static Translations using Google Translation API
REM ============================================
REM This script uses the existing /api/translate endpoint to populate all i18n files
REM
REM Requirements:
REM   - Backend should be running (or use direct import)
REM   - Google Translation API configured
REM ============================================

echo.
echo ============================================
echo 🌐 Generating Static Translations
echo ============================================
echo.

cd Backend

echo Step 1: Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python not found! Please install Python first.
    pause
    exit /b 1
)

echo ✅ Python found
echo.

echo Step 2: Installing required packages (if needed)...
python -m pip install requests --quiet
echo ✅ Dependencies ready
echo.

echo Step 3: Starting translation generation...
echo.
echo Note: This will translate all keys from en.json to all supported languages
echo       using the Google Translation API endpoint.
echo.

python generate_translations.py

echo.
echo ============================================
echo ✅ Translation generation complete!
echo ============================================
echo.
pause

