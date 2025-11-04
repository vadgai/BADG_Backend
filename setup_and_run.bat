@echo off
echo Medical Diagnosis Application Setup
echo ==================================

echo Installing required packages...
C:\Users\ashut\AppData\Local\Programs\Python\Python310\python.exe -m pip install -r requirements.txt

echo Installing spaCy and scispacy...
C:\Users\ashut\AppData\Local\Programs\Python\Python310\python.exe -m pip install spacy scispacy
C:\Users\ashut\AppData\Local\Programs\Python\Python310\python.exe -m spacy download en_core_web_sm

echo Installing sciSpacy model...
C:\Users\ashut\AppData\Local\Programs\Python\Python310\python.exe -m pip install .\en_core_sci_sm-0.5.4.tar.gz

echo Starting FastAPI server...
C:\Users\ashut\AppData\Local\Programs\Python\Python310\python.exe -m uvicorn main:app --reload

echo If the server starts successfully, you can access it at: http://127.0.0.1:8000
pause 