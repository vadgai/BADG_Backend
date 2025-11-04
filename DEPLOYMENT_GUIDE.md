# 🚀 VADG Backend - Production Deployment Guide

Complete guide for deploying the VADG backend to Google Cloud Run with best practices for security, scalability, and monitoring.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Detailed Deployment Steps](#detailed-deployment-steps)
4. [Configuration Options](#configuration-options)
5. [Security Best Practices](#security-best-practices)
6. [Monitoring & Logging](#monitoring--logging)
7. [Troubleshooting](#troubleshooting)
8. [Cost Optimization](#cost-optimization)
9. [Updating & Maintenance](#updating--maintenance)

---

## 🎯 Prerequisites

### Required

- **Google Cloud Account** with billing enabled
- **gcloud CLI** installed and configured
  ```bash
  # Install gcloud CLI
  # Visit: https://cloud.google.com/sdk/docs/install
  
  # Authenticate
  gcloud auth login
  
  # Set project
  gcloud config set project YOUR_PROJECT_ID
  ```

- **Google Gemini API Key**
  - Get one at: https://makersuite.google.com/app/apikey
  - Free tier: 60 requests per minute

### Optional but Recommended

- **MongoDB Atlas Account** (for data persistence)
  - Free tier available: https://www.mongodb.com/cloud/atlas/register
  - Without MongoDB, data is stored in-memory (lost on restart)

- **Gmail Account with App Password** (for contact form)
  - Enable 2FA on your Gmail account
  - Generate app password: https://myaccount.google.com/apppasswords

---

## ⚡ Quick Start

### Option 1: Automated Deployment (Recommended)

```bash
cd Backend

# Basic deployment (minimum required)
./deploy.sh YOUR_GOOGLE_API_KEY

# Full deployment with MongoDB and email
./deploy.sh YOUR_API_KEY \
  --mongo-uri "mongodb+srv://user:pass@cluster.mongodb.net/" \
  --email "your@gmail.com" \
  --email-pass "your_gmail_app_password"
```

**That's it!** The script handles everything automatically.

### Option 2: Manual Deployment

```bash
cd Backend

# 1. Enable APIs
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com

# 2. Deploy
gcloud run deploy vadg-backend \
  --region=asia-south1 \
  --source . \
  --allow-unauthenticated \
  --set-env-vars="GOOGLE_API_KEY=YOUR_KEY,ALLOWED_ORIGINS=https://vadg.netlify.app,https://www.vadg.in"

# 3. Get URL
gcloud run services describe vadg-backend \
  --region=asia-south1 \
  --format='value(status.url)'
```

---

## 📖 Detailed Deployment Steps

### Step 1: Prepare Your Environment

```bash
# Navigate to backend directory
cd Backend

# Verify gcloud is installed
gcloud --version

# Check current project
gcloud config get-value project

# Set project if needed
gcloud config set project positive-shell-475102-t5
```

### Step 2: Choose Your Configuration

#### Minimal Configuration (Testing)
```bash
./deploy.sh YOUR_GOOGLE_API_KEY
```
- Uses in-memory storage (data lost on restart)
- No email notifications
- Suitable for testing and development

#### Production Configuration (Recommended)
```bash
./deploy.sh YOUR_GOOGLE_API_KEY \
  --mongo-uri "mongodb+srv://user:password@cluster.mongodb.net/" \
  --email "your.email@gmail.com" \
  --email-pass "your_gmail_app_password" \
  --region "asia-south1"
```
- Persistent storage with MongoDB
- Email notifications enabled
- Full feature set

### Step 3: Deploy

```bash
# Run deployment script
./deploy.sh YOUR_API_KEY [OPTIONS]

# The script will:
# ✅ Validate your setup
# ✅ Enable required GCP APIs
# ✅ Set up Secret Manager (for sensitive data)
# ✅ Build and deploy Docker container
# ✅ Configure public access
# ✅ Test the deployment
```

### Step 4: Verify Deployment

```bash
# Get your service URL
SERVICE_URL=$(gcloud run services describe vadg-backend \
  --region=asia-south1 \
  --format='value(status.url)')

# Test health endpoint
curl $SERVICE_URL/health

# Expected response:
# {
#   "status": "healthy",
#   "timestamp": "2024-11-04T...",
#   "version": "2.0.0",
#   "service": "VADG API"
# }

# View API documentation
open $SERVICE_URL/docs
```

---

## ⚙️ Configuration Options

### Deployment Script Options

```bash
./deploy.sh YOUR_API_KEY [OPTIONS]

Options:
  --mongo-uri URI       MongoDB connection string
  --email EMAIL         Sender email for notifications
  --email-pass PASS     Email password/app password
  --region REGION       GCP region (default: asia-south1)
  --project PROJECT     GCP project ID (auto-detect if not set)
  --service-name NAME   Service name (default: vadg-backend)
  --skip-secrets        Don't use Secret Manager (less secure)
```

### Environment Variables

See [ENV_VARIABLES.md](./ENV_VARIABLES.md) for complete list.

#### Required
- `GOOGLE_API_KEY` - Google Gemini API key
- `ALLOWED_ORIGINS` - Comma-separated list of allowed frontend URLs

#### Optional but Recommended
- `MONGO_URI` - MongoDB connection string
- `MONGO_DB_NAME` - Database name (default: vadg)
- `SENDER_EMAIL` - Gmail address for notifications
- `SENDER_PASSWORD` - Gmail app password
- `LOG_LEVEL` - Logging level (INFO, WARNING, ERROR)

### Choosing a Region

Recommended regions based on your target audience:

| Region | Location | Best For |
|--------|----------|----------|
| `asia-south1` | Mumbai, India | Indian users (lowest latency) |
| `asia-southeast1` | Singapore | Southeast Asia |
| `us-central1` | Iowa, USA | US users |
| `europe-west1` | Belgium | European users |

```bash
# Deploy to different region
./deploy.sh YOUR_KEY --region us-central1
```

---

## 🔒 Security Best Practices

### 1. Use Secret Manager (Automatic in deploy script)

Secrets are stored securely and never in plain text:
```bash
# Secrets are created automatically by deploy.sh
# View secrets in GCP Console:
# https://console.cloud.google.com/security/secret-manager
```

### 2. Restrict CORS Origins

Only allow your actual frontend domains:
```bash
gcloud run services update vadg-backend \
  --region=asia-south1 \
  --update-env-vars="ALLOWED_ORIGINS=https://vadg.in,https://www.vadg.in"
```

### 3. Enable Cloud Armor (Advanced)

Protect against DDoS and malicious traffic:
```bash
# Create security policy
gcloud compute security-policies create vadg-policy \
  --description "VADG security policy"

# Add rate limiting rule
gcloud compute security-policies rules create 1000 \
  --security-policy vadg-policy \
  --expression "true" \
  --action "rate-based-ban" \
  --rate-limit-threshold-count 100 \
  --rate-limit-threshold-interval-sec 60
```

### 4. Use Service Accounts

Create dedicated service account for your app:
```bash
# Create service account
gcloud iam service-accounts create vadg-backend-sa \
  --display-name="VADG Backend Service Account"

# Grant necessary permissions
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:vadg-backend-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Deploy with service account
gcloud run deploy vadg-backend \
  --region=asia-south1 \
  --service-account=vadg-backend-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --source .
```

### 5. Regular Security Updates

```bash
# Update dependencies
cd Backend
pip install --upgrade -r requirements.txt

# Redeploy
./deploy.sh YOUR_API_KEY
```

---

## 📊 Monitoring & Logging

### View Logs

```bash
# Recent logs
gcloud run services logs read vadg-backend \
  --region=asia-south1 \
  --limit=100

# Live tail
gcloud run services logs tail vadg-backend \
  --region=asia-south1

# Filter by severity
gcloud run services logs read vadg-backend \
  --region=asia-south1 \
  --filter="severity>=ERROR"
```

### View Metrics

```bash
# Get service URL for metrics
echo "https://console.cloud.google.com/run/detail/asia-south1/vadg-backend/metrics"
```

Key metrics to monitor:
- **Request count** - Total requests
- **Request latency** - Response time (aim for <500ms)
- **Error rate** - Should be <1%
- **Instance count** - Auto-scaling behavior
- **Memory utilization** - Should stay <80%
- **CPU utilization** - Should stay <80%

### Set Up Alerts

```bash
# Create alert for high error rate
gcloud alpha monitoring policies create \
  --notification-channels=CHANNEL_ID \
  --display-name="VADG High Error Rate" \
  --condition-display-name="Error rate > 5%" \
  --condition-threshold-value=0.05 \
  --condition-threshold-duration=300s
```

### Structured Logging

The app uses structured JSON logging. View in Cloud Console:
```
https://console.cloud.google.com/logs/query
```

Example query:
```
resource.type="cloud_run_revision"
resource.labels.service_name="vadg-backend"
severity>=ERROR
```

---

## 🐛 Troubleshooting

### Common Issues

#### 1. Deployment Fails with "Permission Denied"

**Cause:** Billing not enabled or insufficient permissions

**Solution:**
```bash
# Enable billing
# Visit: https://console.cloud.google.com/billing

# Check IAM permissions
gcloud projects get-iam-policy YOUR_PROJECT_ID \
  --flatten="bindings[].members" \
  --format="table(bindings.role)" \
  --filter="bindings.members:YOUR_EMAIL"
```

You need at least:
- `roles/run.admin`
- `roles/iam.serviceAccountUser`
- `roles/cloudbuild.builds.editor`

#### 2. Health Check Fails

**Cause:** Service still starting or API key invalid

**Solution:**
```bash
# Wait 1-2 minutes for service to fully start
sleep 120

# Test health endpoint
curl -v https://YOUR_SERVICE_URL/health

# Check logs for errors
gcloud run services logs read vadg-backend \
  --region=asia-south1 \
  --limit=50 \
  | grep ERROR
```

#### 3. CORS Errors in Frontend

**Cause:** Frontend URL not in ALLOWED_ORIGINS

**Solution:**
```bash
# Get current ALLOWED_ORIGINS
gcloud run services describe vadg-backend \
  --region=asia-south1 \
  --format="value(spec.template.spec.containers[0].env[?(@.name=='ALLOWED_ORIGINS')].value)"

# Update with your frontend URL
gcloud run services update vadg-backend \
  --region=asia-south1 \
  --update-env-vars="ALLOWED_ORIGINS=https://your-frontend.netlify.app,https://www.vadg.in"
```

#### 4. MongoDB Connection Fails

**Cause:** Invalid connection string or network access not configured

**Solution:**
```bash
# Test MongoDB connection locally first
python -c "
from pymongo import MongoClient
client = MongoClient('YOUR_MONGO_URI')
client.admin.command('ping')
print('MongoDB connection successful!')
"

# In MongoDB Atlas:
# 1. Go to Network Access
# 2. Add 0.0.0.0/0 to IP whitelist (for Cloud Run)
# 3. Or add Cloud Run service IPs
```

#### 5. Out of Memory Errors

**Cause:** Insufficient memory allocation

**Solution:**
```bash
# Increase memory to 2GB
gcloud run services update vadg-backend \
  --region=asia-south1 \
  --memory=2Gi
```

#### 6. Timeout Errors

**Cause:** Request takes longer than timeout setting

**Solution:**
```bash
# Increase timeout to 5 minutes (max)
gcloud run services update vadg-backend \
  --region=asia-south1 \
  --timeout=300
```

### Debug Commands

```bash
# Get full service description
gcloud run services describe vadg-backend \
  --region=asia-south1

# List all revisions
gcloud run revisions list \
  --service=vadg-backend \
  --region=asia-south1

# Get environment variables
gcloud run services describe vadg-backend \
  --region=asia-south1 \
  --format="value(spec.template.spec.containers[0].env)"

# Test with curl
curl -X POST https://YOUR_URL/symptom \
  -H "Content-Type: application/json" \
  -d '{"name":"Test","age":30,"gender":"male","symptoms":["fever"]}'
```

---

## 💰 Cost Optimization

### Free Tier Limits

Google Cloud Run free tier (monthly):
- **2 million requests**
- **360,000 GB-seconds** of memory
- **180,000 vCPU-seconds** of compute

Your app's usage (estimated):
- ~0.1 seconds per request
- ~0.5 GB memory per instance
- = **Easily stays within free tier** for moderate traffic

### Cost Saving Tips

#### 1. Use Minimum Instances Wisely
```bash
# No minimum instances (cost-effective for low traffic)
gcloud run services update vadg-backend \
  --region=asia-south1 \
  --min-instances=0

# Keep 1 instance warm (better performance, slight cost)
gcloud run services update vadg-backend \
  --region=asia-south1 \
  --min-instances=1 \
  --max-instances=10
```

#### 2. Optimize Memory Allocation
```bash
# Use minimum memory that works (default: 512Mi)
gcloud run services update vadg-backend \
  --region=asia-south1 \
  --memory=512Mi
```

#### 3. Set Concurrent Requests
```bash
# Allow more concurrent requests per instance
gcloud run services update vadg-backend \
  --region=asia-south1 \
  --concurrency=80
```

#### 4. Clean Up Unused Revisions
```bash
# List revisions
gcloud run revisions list --service=vadg-backend --region=asia-south1

# Delete old revisions
gcloud run revisions delete REVISION_NAME --region=asia-south1
```

### Monitor Costs

```bash
# View current month's costs
# Visit: https://console.cloud.google.com/billing/reports

# Set up budget alerts
# Visit: https://console.cloud.google.com/billing/budgets
```

Recommended budget alerts:
- Alert at 50% of budget
- Alert at 90% of budget
- Alert at 100% of budget

---

## 🔄 Updating & Maintenance

### Update Application Code

```bash
# Option 1: Use deploy script (recommended)
cd Backend
./deploy.sh YOUR_API_KEY

# Option 2: Manual deploy
gcloud run deploy vadg-backend \
  --region=asia-south1 \
  --source .
```

### Update Environment Variables

```bash
# Update single variable
gcloud run services update vadg-backend \
  --region=asia-south1 \
  --update-env-vars="LOG_LEVEL=WARNING"

# Update multiple variables
gcloud run services update vadg-backend \
  --region=asia-south1 \
  --update-env-vars="LOG_LEVEL=WARNING,MAX_INSTANCES=30"

# Remove variable
gcloud run services update vadg-backend \
  --region=asia-south1 \
  --remove-env-vars="VARIABLE_NAME"
```

### Update Secrets

```bash
# Update secret value
echo -n "new_api_key" | gcloud secrets versions add google-api-key --data-file=-

# Cloud Run will use the new version on next deployment
gcloud run deploy vadg-backend --region=asia-south1 --source .
```

### Update Dependencies

```bash
# Update requirements.txt
cd Backend
pip install --upgrade google-generativeai fastapi uvicorn

# Freeze new versions
pip freeze > requirements.txt

# Deploy updated version
./deploy.sh YOUR_API_KEY
```

### Rollback to Previous Version

```bash
# List revisions
gcloud run revisions list \
  --service=vadg-backend \
  --region=asia-south1

# Route 100% traffic to previous revision
gcloud run services update-traffic vadg-backend \
  --region=asia-south1 \
  --to-revisions=REVISION_NAME=100
```

### Scale Configuration

```bash
# Handle high traffic
gcloud run services update vadg-backend \
  --region=asia-south1 \
  --max-instances=50 \
  --min-instances=3 \
  --concurrency=100

# Return to normal
gcloud run services update vadg-backend \
  --region=asia-south1 \
  --max-instances=20 \
  --min-instances=0 \
  --concurrency=80
```

---

## ✅ Pre-Deployment Checklist

Before deploying to production:

### Security
- [ ] Secrets stored in Secret Manager (not in code)
- [ ] ALLOWED_ORIGINS restricted to actual domains
- [ ] MongoDB IP whitelist configured
- [ ] Gmail app password created (not regular password)
- [ ] Service account with minimal permissions

### Configuration
- [ ] GOOGLE_API_KEY is valid and has quota
- [ ] MongoDB connection tested
- [ ] Email configuration tested
- [ ] Environment variables documented
- [ ] CORS origins include all frontend URLs

### Testing
- [ ] Health endpoint responds
- [ ] Symptom submission works
- [ ] WebSocket connections work
- [ ] Report generation works
- [ ] Contact form sends emails
- [ ] API documentation accessible

### Monitoring
- [ ] Cloud Logging enabled
- [ ] Budget alerts configured
- [ ] Error alerts configured
- [ ] Uptime checks configured

### Documentation
- [ ] Frontend team has backend URL
- [ ] Environment variables documented
- [ ] Deployment process documented
- [ ] Rollback procedure documented

---

## 📚 Additional Resources

### Official Documentation
- [Cloud Run Docs](https://cloud.google.com/run/docs)
- [Secret Manager](https://cloud.google.com/secret-manager/docs)
- [Cloud Logging](https://cloud.google.com/logging/docs)
- [Cloud Monitoring](https://cloud.google.com/monitoring/docs)

### VADG Specific
- [ENV_VARIABLES.md](./ENV_VARIABLES.md) - All environment variables
- [Dockerfile](./Dockerfile) - Container configuration
- [requirements.txt](./requirements.txt) - Python dependencies
- [app.yaml](./app.yaml) - App Engine configuration

### Useful Commands
```bash
# Quick reference sheet
gcloud cheat-sheet
gcloud run --help

# Interactive tutorial
gcloud beta interactive

# Service status
gcloud run services list
```

---

## 🆘 Getting Help

### Check Service Status
```bash
# Service details
gcloud run services describe vadg-backend \
  --region=asia-south1

# Recent logs
gcloud run services logs read vadg-backend \
  --region=asia-south1 \
  --limit=100
```

### GCP Support
- [GCP Support Console](https://console.cloud.google.com/support)
- [Stack Overflow](https://stackoverflow.com/questions/tagged/google-cloud-run)
- [GCP Community](https://www.googlecloudcommunity.com/)

### VADG Team
- Check project documentation
- Review existing deployment guides
- Test in staging environment first

---

## 🎉 Success!

If you've followed this guide, your VADG backend should be:

✅ Deployed to Google Cloud Run  
✅ Accessible via HTTPS  
✅ Secured with Secret Manager  
✅ Monitored with Cloud Logging  
✅ Auto-scaling based on traffic  
✅ Cost-optimized for your usage  

**Next Steps:**
1. Update your frontend with the backend URL
2. Test the full user flow
3. Set up monitoring and alerts
4. Configure your custom domain (optional)

Happy deploying! 🚀

