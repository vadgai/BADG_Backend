@echo off
echo ============================================================
echo   Upgrading Google Generative AI SDK
echo ============================================================
echo.

cd C:\Users\krish\OneDrive\Desktop\vadg\Backend

echo [1/3] Upgrading google-generativeai...
pip install --upgrade google-generativeai

echo.
echo [2/3] Verifying installation...
python -c "import google.generativeai as genai; print(f'✅ SDK Version: {genai.__version__}')"

echo.
echo [3/3] Testing API with new SDK...
python -c "import os; from dotenv import load_dotenv; load_dotenv(); import google.generativeai as genai; genai.configure(api_key=os.getenv('GOOGLE_API_KEY')); print('Testing gemini-1.5-flash...'); model = genai.GenerativeModel('gemini-1.5-flash'); response = model.generate_content('Say hello'); print('✅ API Works!'); print('Response:', response.text[:50])"

echo.
echo ============================================================
echo   Upgrade complete! Restart backend to use new SDK.
echo ============================================================
pause

