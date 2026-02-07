@echo off
echo ========================================
echo  Setting up your Gemini API Keys
echo ========================================
echo.

REM Create the .env file with your API keys
(
echo # VADG Backend Environment Variables - CONFIGURED
echo # Generated: %date% %time%
echo.
echo # ===== GEMINI API KEYS - 15 Keys Configured =====
echo GEMINI_API_KEY_1=AIzaSyBI8OxvukZj9FlNZvJpjUB869-bedbIO0w
echo GEMINI_API_KEY_2=AIzaSyAyLydaTsx_F8-DzjQ0Ksa2Ug642DAecE4
echo GEMINI_API_KEY_3=AIzaSyBbgmTnWLl4jcCyLZY5rD6ARZoX77qTGY4
echo GEMINI_API_KEY_4=AIzaSyDk1mPhxrBFHuA_ukayhowsmtfRq1Qi8lE
echo GEMINI_API_KEY_5=AIzaSyBP1YeBx5H1Vi8SqXhJu6Z5IrCDbVcmouE
echo GEMINI_API_KEY_6=AIzaSyBak7x7dLBD5QwUpQRDFvAF9ZWn6NAqVqM
echo GEMINI_API_KEY_7=AIzaSyCFk6v7n2TjOKcj1ActiSOp-t5XRr7t7m8
echo GEMINI_API_KEY_8=AIzaSyCZcV1R2JeNpnnaSvgAm2KpDrpTT6KvdO0
echo GEMINI_API_KEY_9=AIzaSyD2lszXd7hOv7resRTaUL3W5JSQpT07fJo
echo GEMINI_API_KEY_10=AIzaSyB-quNiHwDxBrgjOCIMqmKvHR2Quev_u9g
echo GEMINI_API_KEY_11=AIzaSyByI0ySNuyAG6XV8f5aXXdfrYZWApXvSk4
echo GEMINI_API_KEY_12=AIzaSyDlcY-nlc1ty4m_eqSaaAd1_in5FtK7vrw
echo GEMINI_API_KEY_13=AIzaSyClHFghAoCz0I_LLeyQtjzvJdQ-Wfg6wYw
echo GEMINI_API_KEY_14=AIzaSyBWHhKPBDcvQTB90O5bAJKgTqVlPo2Iq3w
echo GEMINI_API_KEY_15=AIzaSyDiS5uhYqplV_aTmi9SRhcpfetMHF7FNHc
echo.
echo # ===== DATABASE CONFIGURATION =====
echo MONGODB_URL=mongodb://localhost:27017/
echo MONGODB_DATABASE=vadg_db
echo.
echo # ===== APPLICATION SETTINGS =====
echo VADG_DEBUG=0
echo HOST=0.0.0.0
echo PORT=8000
echo.
echo # ===== SECURITY =====
echo SECRET_KEY=your-secret-key-change-in-production
echo JWT_SECRET_KEY=your-jwt-secret-key-change-in-production
echo.
echo # ===== CORS CONFIGURATION =====
echo ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173,https://vadg.in,https://www.vadg.in
) > .env

echo.
echo ========================================
echo  SUCCESS! Configuration Complete
echo ========================================
echo.
echo Created: Backend\.env
echo API Keys: 15 keys configured
echo.
echo Next steps:
echo 1. Test your keys:    python test_api_keys.py
echo 2. Start backend:     python app.py
echo.
echo ========================================
pause

