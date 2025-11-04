# 🚀 Deploy VADG Backend to Google Cloud NOW

## Step 1: Prerequisites Check

### ✅ Check if gcloud is installed and authenticated

Open a **new Command Prompt** and run:

```cmd
gcloud auth list
```

**If you see your email** → You're authenticated ✅  
**If you see "No credentialed accounts"** → Run:
```cmd
gcloud auth login
```

---

## Step 2: Set Your Project

```cmd
gcloud config set project positive-shell-475102-t5
```

Or if you have a different project:
```cmd
gcloud config set project YOUR_PROJECT_ID
```

---

## Step 3: Get Your Google Gemini API Key

1. Visit: https://makersuite.google.com/app/apikey
2. Click "Create API Key"
3. Copy the key (starts with `AIza...`)

---

## Step 4: Deploy!

### **Option A: Basic Deployment (No MongoDB, No Email)**

```cmd
cd C:\Users\krish\OneDrive\Desktop\vadg\Backend
deploy.bat YOUR_GOOGLE_API_KEY
```

Replace `YOUR_GOOGLE_API_KEY` with your actual API key.

---

### **Option B: Full Deployment (With MongoDB and Email)**

If you have MongoDB Atlas and Gmail configured:

```cmd
cd C:\Users\krish\OneDrive\Desktop\vadg\Backend

deploy.bat YOUR_API_KEY ^
  --mongo-uri "mongodb+srv://vadg_db_user:Yh96u81FmZucN6p8@cluster0.zyu50c9.mongodb.net/" ^
  --email "your@gmail.com" ^
  --email-pass "your_gmail_app_password"
```

---

## Step 5: Wait for Deployment

The deployment will take **3-5 minutes**. You'll see:

```
🚀 VADG Backend Deployment to Google Cloud Run
================================================
🔧 Setting project...
🔌 Step 1/5: Enabling required APIs...
🔐 Step 2/5: Setting up Secret Manager...
📦 Step 3/5: Deploying to Cloud Run...
🌐 Step 4/5: Configuring public access...
🔍 Step 5/5: Verifying deployment...
✅ DEPLOYMENT COMPLETE!
```

---

## Step 6: Get Your Backend URL

After deployment, you'll see:

```
🎉 Your VADG backend is live at:
   https://vadg-backend-XXXXX.asia-south1.run.app
```

**Copy this URL!**

---

## Step 7: Update Your Frontend

Add to `Frontend\.env` or Netlify environment variables:

```env
VITE_API_BASE_URL=https://vadg-backend-XXXXX.asia-south1.run.app
VITE_WS_BASE_URL=wss://vadg-backend-XXXXX.asia-south1.run.app
```

---

## 🧪 Test Your Deployment

```cmd
curl https://vadg-backend-XXXXX.asia-south1.run.app/health
```

Should return:
```json
{
  "status": "healthy",
  "timestamp": "...",
  "version": "2.0.0",
  "service": "VADG API"
}
```

---

## 🆘 Troubleshooting

### Problem: "gcloud is not recognized"
**Solution:** Install gcloud CLI from https://cloud.google.com/sdk/docs/install

### Problem: "Permission denied" or "Billing not enabled"
**Solution:** 
1. Go to https://console.cloud.google.com/billing
2. Enable billing for your project

### Problem: "API key invalid"
**Solution:**
1. Check your API key is correct (starts with `AIza`)
2. Make sure you copied the entire key
3. Get a new key from https://makersuite.google.com/app/apikey

### Problem: "Project not found"
**Solution:**
```cmd
gcloud config set project positive-shell-475102-t5
```

### Problem: Deployment fails
**Solution:**
1. Check logs:
```cmd
gcloud run services logs read vadg-backend --region=asia-south1 --limit=50
```
2. Try redeploying:
```cmd
cd Backend
deploy.bat YOUR_API_KEY
```

---

## 📞 Quick Commands Reference

```cmd
# Check authentication
gcloud auth list

# Login
gcloud auth login

# Set project
gcloud config set project positive-shell-475102-t5

# Deploy
cd C:\Users\krish\OneDrive\Desktop\vadg\Backend
deploy.bat YOUR_GOOGLE_API_KEY

# Check logs
gcloud run services logs read vadg-backend --region=asia-south1

# Get service URL
gcloud run services describe vadg-backend --region=asia-south1 --format="value(status.url)"

# View in browser
gcloud run services describe vadg-backend --region=asia-south1 --format="value(status.url)" & start chrome %output%
```

---

## ✅ Ready to Deploy?

**Run these commands in order:**

```cmd
:: 1. Navigate to backend
cd C:\Users\krish\OneDrive\Desktop\vadg\Backend

:: 2. Check authentication
gcloud auth list

:: 3. Set project
gcloud config set project positive-shell-475102-t5

:: 4. Deploy (replace YOUR_API_KEY)
deploy.bat YOUR_GOOGLE_API_KEY
```

---

## 💡 What You Need

| Item | Where to Get | Required? |
|------|--------------|-----------|
| **gcloud CLI** | https://cloud.google.com/sdk/docs/install | ✅ Yes |
| **Google Cloud Project** | https://console.cloud.google.com | ✅ Yes |
| **Billing Enabled** | https://console.cloud.google.com/billing | ✅ Yes |
| **Gemini API Key** | https://makersuite.google.com/app/apikey | ✅ Yes |
| **MongoDB URI** | https://www.mongodb.com/cloud/atlas | 🟡 Optional |
| **Gmail App Password** | https://myaccount.google.com/apppasswords | 🟡 Optional |

---

## 🎉 That's It!

Once deployed, your backend will be live at a URL like:
```
https://vadg-backend-258229345811.asia-south1.run.app
```

Use this URL in your frontend configuration!

**Need help?** Check `DEPLOYMENT_GUIDE.md` for detailed troubleshooting.

