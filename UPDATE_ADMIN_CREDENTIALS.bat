@echo off
REM Script to update admin credentials in Backend/.env file
echo ============================================================
echo   Updating Admin Credentials in .env file
echo ============================================================
echo.

REM Check if .env exists
if not exist .env (
    echo [ERROR] .env file not found!
    echo.
    echo Please create Backend\.env first by copying from env.example:
    echo   copy env.example .env
    echo.
    pause
    exit /b 1
)

echo [INFO] Backing up .env to .env.backup...
copy .env .env.backup >nul 2>&1

echo [INFO] Updating admin credentials...
echo.

REM Remove old admin credentials if they exist
findstr /v /i "^ADMIN_EMAIL=" .env > .env.tmp
findstr /v /i "^ADMIN_PASSWORD=" .env.tmp > .env.tmp2
findstr /v /i "^ADMIN_JWT_SECRET=" .env.tmp2 > .env.tmp3
move /y .env.tmp3 .env.tmp >nul 2>&1
del .env.tmp2 >nul 2>&1
del .env.tmp >nul 2>&1

REM Add new admin credentials
echo ADMIN_EMAIL=m87.krishna@gmail.com >> .env
echo ADMIN_PASSWORD=Vadg@44 >> .env
echo ADMIN_JWT_SECRET=9348e6fbdeafb8c7d7f963701123d609c1b7ae1d704010b98b878f943094d664 >> .env

echo [SUCCESS] Admin credentials updated!
echo.
echo Updated values:
echo   ADMIN_EMAIL=m87.krishna@gmail.com
echo   ADMIN_PASSWORD=Vadg@44
echo   ADMIN_JWT_SECRET=9348e6fbdeafb8c7d7f963701123d609c1b7ae1d704010b98b878f943094d664
echo.
echo [INFO] Backup saved to .env.backup
echo.
echo [INFO] Restart your backend server for changes to take effect!
echo.
pause

