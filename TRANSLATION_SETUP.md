# 🌐 Google Cloud Translation Setup Guide

## ✅ What Changed

Translation service now uses **Google Cloud Translation API** instead of Gemini for better accuracy and reliability.

---

## 📋 Setup Steps

### **1. Install Google Cloud Translation Package**

```bash
cd Backend
pip install google-cloud-translate
```

### **2. Set Up Google Cloud Credentials**

#### **Option A: Using Service Account (Recommended for Production)**

1. Go to: https://console.cloud.google.com
2. Create or select a project
3. Enable **Cloud Translation API**
4. Create a **Service Account** with Translation API access
5. Download the **JSON key file**
6. Set environment variable:

```bash
# Windows (PowerShell):
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\path\to\service-account-key.json"
$env:GCLOUD_PROJECT_ID="your-project-id"

# Mac/Linux:
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"
export GCLOUD_PROJECT_ID="your-project-id"
```

#### **Option B: Using Application Default Credentials (Easier for Development)**

```bash
# Install gcloud CLI if not already installed
# Then authenticate:
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID

# Set project ID in .env:
echo "GCLOUD_PROJECT_ID=your-project-id" >> .env
```

### **3. Update Backend .env File**

Add to `Backend/.env`:

```env
GCLOUD_PROJECT_ID=your-google-cloud-project-id
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
```

### **4. Restart Backend**

```bash
cd Backend
python app.py
```

**✅ Look for this log:**
```
✅ Google Cloud Translation API initialized
```

**❌ If you see:**
```
⚠️  Google Cloud Translation not available
```
→ Run: `pip install google-cloud-translate` and restart

---

## 🧪 Test Translation

### **Quick Test (Browser Console):**

```javascript
fetch('http://localhost:8000/api/translate', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({text: 'Do you have fever?', targetLang: 'hi'})
})
.then(r => r.json())
.then(d => console.log('✅ Translation:', d))
.catch(e => console.error('❌ Error:', e));
```

**Expected:**
```json
{
  "translated": "क्या आपको बुखार है?"
}
```

### **Or Run Test Script:**

```bash
cd Backend
python test_translate_endpoint.py
```

---

## 📊 Features

✅ **Better Translation Quality** - Google Cloud Translation is optimized for natural language  
✅ **Medical Abbreviations Preserved** - CBC, ECG, MRI, CT stay in English  
✅ **24-hour Cache** - Reduces API costs by ~95%  
✅ **Rate Limiting** - 30 requests per IP per 60 seconds  
✅ **Safe Fallbacks** - Returns English on any error  
✅ **Batch Support** - Translate multiple texts in one call  

---

## 💰 Cost Information

Google Cloud Translation API pricing:
- **Free tier:** 500,000 characters per month
- **After free tier:** $20 per 1M characters

**With caching:** Most users hit cache (free), actual API calls are minimal.

---

## 🔧 Troubleshooting

### "GCLOUD_PROJECT_ID not set"
→ Add to `.env`: `GCLOUD_PROJECT_ID=your-project-id`

### "Could not automatically determine credentials"
→ Set `GOOGLE_APPLICATION_CREDENTIALS` or run `gcloud auth application-default login`

### "API not enabled"
→ Enable Cloud Translation API in Google Cloud Console

### "Permission denied"
→ Ensure service account has `Cloud Translation API User` role

---

## ✅ Verification

After setup, test with:

1. Start backend: `python app.py`
2. Check health: `curl http://localhost:8000/api/translate/health`
3. Test translation: See test script above

**Questions should now display in Hindi/Tamil/Telugu/Kannada/Bengali!** 🎉


