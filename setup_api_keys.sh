#!/bin/bash

echo "========================================"
echo " Setting up your Gemini API Keys"
echo "========================================"
echo ""

# Create the .env file with your API keys
cat > .env << 'EOF'
# VADG Backend Environment Variables - CONFIGURED
# Generated: $(date)

# ===== GEMINI API KEYS - 15 Keys Configured =====
GEMINI_API_KEY_1=AIzaSyBI8OxvukZj9FlNZvJpjUB869-bedbIO0w
GEMINI_API_KEY_2=AIzaSyAyLydaTsx_F8-DzjQ0Ksa2Ug642DAecE4
GEMINI_API_KEY_3=AIzaSyBbgmTnWLl4jcCyLZY5rD6ARZoX77qTGY4
GEMINI_API_KEY_4=AIzaSyDk1mPhxrBFHuA_ukayhowsmtfRq1Qi8lE
GEMINI_API_KEY_5=AIzaSyBP1YeBx5H1Vi8SqXhJu6Z5IrCDbVcmouE
GEMINI_API_KEY_6=AIzaSyBak7x7dLBD5QwUpQRDFvAF9ZWn6NAqVqM
GEMINI_API_KEY_7=AIzaSyCFk6v7n2TjOKcj1ActiSOp-t5XRr7t7m8
GEMINI_API_KEY_8=AIzaSyCZcV1R2JeNpnnaSvgAm2KpDrpTT6KvdO0
GEMINI_API_KEY_9=AIzaSyD2lszXd7hOv7resRTaUL3W5JSQpT07fJo
GEMINI_API_KEY_10=AIzaSyB-quNiHwDxBrgjOCIMqmKvHR2Quev_u9g
GEMINI_API_KEY_11=AIzaSyByI0ySNuyAG6XV8f5aXXdfrYZWApXvSk4
GEMINI_API_KEY_12=AIzaSyDlcY-nlc1ty4m_eqSaaAd1_in5FtK7vrw
GEMINI_API_KEY_13=AIzaSyClHFghAoCz0I_LLeyQtjzvJdQ-Wfg6wYw
GEMINI_API_KEY_14=AIzaSyBWHhKPBDcvQTB90O5bAJKgTqVlPo2Iq3w
GEMINI_API_KEY_15=AIzaSyDiS5uhYqplV_aTmi9SRhcpfetMHF7FNHc

# ===== DATABASE CONFIGURATION =====
MONGODB_URL=mongodb://localhost:27017/
MONGODB_DATABASE=vadg_db

# ===== APPLICATION SETTINGS =====
VADG_DEBUG=0
HOST=0.0.0.0
PORT=8000

# ===== SECURITY =====
SECRET_KEY=your-secret-key-change-in-production
JWT_SECRET_KEY=your-jwt-secret-key-change-in-production

# ===== CORS CONFIGURATION =====
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173,https://vadg.in,https://www.vadg.in
EOF

chmod 600 .env

echo ""
echo "========================================"
echo " SUCCESS! Configuration Complete"
echo "========================================"
echo ""
echo "Created: Backend/.env"
echo "API Keys: 15 keys configured"
echo "Permissions: 600 (secure)"
echo ""
echo "Next steps:"
echo "1. Test your keys:    python test_api_keys.py"
echo "2. Start backend:     python app.py"
echo ""
echo "========================================"

