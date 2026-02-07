# Environment Variables Configuration

This document lists all environment variables required for the VADG Backend.

## 🔴 REQUIRED Variables

### Google AI API Key
```bash
GOOGLE_API_KEY=your_google_gemini_api_key_here
```
**How to get:** Visit https://makersuite.google.com/app/apikey

### CORS Configuration
```bash
ALLOWED_ORIGINS=https://vadg.netlify.app,https://www.vadg.in,http://localhost:5173
```
**Note:** Comma-separated list of allowed frontend origins. Update with your actual frontend URLs.

---

## 🟡 OPTIONAL Variables (Recommended for Production)

### MongoDB Configuration
```bash
MONGO_URI=mongodb+srv://user:password@cluster.mongodb.net/
MONGO_DB_NAME=vadg
MONGO_MAX_POOL_SIZE=50
MONGO_MIN_POOL_SIZE=10
```
**Note:** If not set, the app will use in-memory storage. Data will be lost on restart.

### Security Keys
```bash
SECRET_KEY=change_this_to_a_random_secret_key_in_production
JWT_SECRET_KEY=change_this_to_another_random_secret_key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```
**Note:** Generate random secure keys for production!

### Email Configuration (Contact Form)
```bash
SENDER_EMAIL=your.email@gmail.com
SENDER_PASSWORD=your_gmail_app_password
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
RECIPIENT_EMAILS=vadg.office@gmail.com,admin@vadg.in
```
**Note:** For Gmail, enable "App Passwords" in your Google Account settings.

### Google Cloud Translation API
```bash
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
```
**Note:** Required only if using translation features.

---

## 🟢 OPTIONAL Variables (Has Defaults)

### Application Settings
```bash
ENVIRONMENT=production          # development, staging, or production
LOG_LEVEL=INFO                  # DEBUG, INFO, WARNING, ERROR, CRITICAL
PORT=8080                       # Server port (Cloud Run uses 8080)
```

### AI Model Configuration
```bash
AI_MODEL=gemini-2.5-flash       # AI model to use
AI_TIMEOUT=30                   # Timeout in seconds
MAX_RETRIES=3                   # Max retry attempts
```

### Rate Limiting
```bash
RATE_LIMIT_REQUESTS=100         # Requests per window
RATE_LIMIT_WINDOW=60            # Window in seconds
```

### Session Management
```bash
SESSION_TIMEOUT=3600            # Session timeout in seconds
MAX_SESSIONS=1000               # Max concurrent sessions
```

---

## 📋 Quick Setup for Google Cloud Run

```bash
# Deploy with environment variables
gcloud run deploy vadg-backend \
  --region=asia-south1 \
  --source . \
  --allow-unauthenticated \
  --set-env-vars="GOOGLE_API_KEY=YOUR_KEY,ALLOWED_ORIGINS=https://vadg.netlify.app,https://www.vadg.in,LOG_LEVEL=INFO,ENVIRONMENT=production"
```

### Optional: Add MongoDB
```bash
gcloud run services update vadg-backend \
  --region=asia-south1 \
  --update-env-vars="MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/"
```

### Optional: Add Email Configuration
```bash
gcloud run services update vadg-backend \
  --region=asia-south1 \
  --update-env-vars="SENDER_EMAIL=your@gmail.com,SENDER_PASSWORD=your_app_password,RECIPIENT_EMAILS=vadg.office@gmail.com"
```

---

## 🔒 Using Google Cloud Secret Manager (Recommended)

For sensitive values like API keys and database passwords:

```bash
# Create secrets
echo -n "your_api_key" | gcloud secrets create google-api-key --data-file=-
echo -n "your_mongo_uri" | gcloud secrets create mongo-uri --data-file=-

# Grant Cloud Run access to secrets
gcloud secrets add-iam-policy-binding google-api-key \
  --member="serviceAccount:YOUR_SERVICE_ACCOUNT" \
  --role="roles/secretmanager.secretAccessor"

# Deploy with secrets
gcloud run deploy vadg-backend \
  --region=asia-south1 \
  --source . \
  --set-secrets="GOOGLE_API_KEY=google-api-key:latest,MONGO_URI=mongo-uri:latest"
```

---

## ⚠️ Security Best Practices

1. **NEVER** commit `.env` file to version control
2. **NEVER** hardcode credentials in source code
3. **ALWAYS** use environment variables or Secret Manager for sensitive data
4. **ALWAYS** use different keys for development and production
5. **ROTATE** secrets regularly
6. **LIMIT** CORS origins to only trusted domains
7. **ENABLE** HTTPS only (Cloud Run does this automatically)
8. **MONITOR** logs for security issues

---

## 🧪 Local Development

Create a `.env` file in the `Backend/` directory:

```bash
# Backend/.env
GOOGLE_API_KEY=your_dev_api_key
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
ENVIRONMENT=development
LOG_LEVEL=DEBUG
DEBUG=True
```

Then run:
```bash
cd Backend
python -m uvicorn app:app --reload --port 8000
```

---

## 📝 Environment Variable Priority

The application loads environment variables in this order (last one wins):

1. System environment variables
2. `.env` file (if exists)
3. Command-line arguments
4. Cloud Run / App Engine environment configuration

---

## ✅ Validation Checklist

Before deploying to production:

- [ ] `GOOGLE_API_KEY` is set and valid
- [ ] `ALLOWED_ORIGINS` includes your actual frontend URL(s)
- [ ] `ENVIRONMENT` is set to "production"
- [ ] `LOG_LEVEL` is set to "INFO" or "WARNING"
- [ ] `SECRET_KEY` and `JWT_SECRET_KEY` are unique and secure
- [ ] Sensitive variables are using Secret Manager
- [ ] `.env` file is in `.gitignore`
- [ ] No hardcoded credentials in source code
- [ ] MongoDB URI is set (if using database features)
- [ ] Email configuration is set (if using contact form)
- [ ] Rate limiting is configured appropriately
- [ ] CORS origins are restrictive (not using wildcards)

---

## 📚 Additional Resources

- [Google Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Secret Manager Guide](https://cloud.google.com/secret-manager/docs)
- [FastAPI Environment Variables](https://fastapi.tiangolo.com/advanced/settings/)
- [Security Best Practices](https://cloud.google.com/run/docs/securing/managing-access)

