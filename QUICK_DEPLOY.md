# ⚡ VADG Backend - Quick Deploy Reference

## 🚀 Fastest Way to Deploy

### Prerequisites (One-time setup)
```bash
# 1. Install gcloud CLI
# Visit: https://cloud.google.com/sdk/docs/install

# 2. Login and set project
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# 3. Get Google Gemini API Key
# Visit: https://makersuite.google.com/app/apikey
```

---

## 💨 Deploy Commands

### **Linux / Mac / Git Bash**
```bash
cd Backend
./deploy.sh YOUR_GOOGLE_API_KEY
```

### **Windows CMD / PowerShell**
```cmd
cd Backend
deploy.bat YOUR_GOOGLE_API_KEY
```

### **With MongoDB**
```bash
./deploy.sh YOUR_API_KEY --mongo-uri "mongodb+srv://user:pass@cluster.net/"
```

### **With Email Notifications**
```bash
./deploy.sh YOUR_API_KEY --email your@gmail.com --email-pass your_app_password
```

### **Full Production Setup**
```bash
./deploy.sh YOUR_API_KEY \
  --mongo-uri "mongodb+srv://user:pass@cluster.net/" \
  --email "your@gmail.com" \
  --email-pass "your_app_password" \
  --region "asia-south1"
```

---

## 🧪 Test After Deploy

```bash
# Get your service URL (shown after deployment)
SERVICE_URL="https://vadg-backend-XXXXX.run.app"

# Test health
curl $SERVICE_URL/health

# View API docs
open $SERVICE_URL/docs
```

---

## 🔧 Update Frontend

Add to your `Frontend/.env` or Netlify environment variables:

```env
VITE_API_BASE_URL=https://vadg-backend-XXXXX.run.app
VITE_WS_BASE_URL=wss://vadg-backend-XXXXX.run.app
```

---

## 📊 Monitor

```bash
# View logs
gcloud run services logs read vadg-backend --region=asia-south1 --limit=50

# View metrics
open https://console.cloud.google.com/run
```

---

## 🔄 Redeploy (Update Code)

```bash
cd Backend
./deploy.sh YOUR_API_KEY
```

---

## 🆘 Troubleshooting

### Permission Denied
```bash
# Enable billing: https://console.cloud.google.com/billing
```

### Health Check Failed
```bash
# Wait 2 minutes, then test again
sleep 120
curl https://YOUR_URL/health
```

### CORS Errors
```bash
# Add your frontend URL
gcloud run services update vadg-backend \
  --region=asia-south1 \
  --update-env-vars="ALLOWED_ORIGINS=https://your-frontend.netlify.app,https://www.vadg.in"
```

---

## 💰 Cost

**Free Tier:** 2 million requests/month  
**Your Usage:** ~15,000/month  
**Cost:** $0 (within free tier) ✅

---

## 📚 Full Documentation

- **DEPLOYMENT_GUIDE.md** - Complete guide (5000+ words)
- **ENV_VARIABLES.md** - All configuration options
- **DEPLOYMENT_READY.md** - What's been prepared for you

---

## ✅ That's It!

Deploy → Test → Update Frontend → Done! 🎉

