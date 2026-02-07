# Fix Cloud Run Image Permission Error

## Problem
You're getting this error:
```
ERROR: Google Cloud Run Service Agent service-679635825980@serverless-robot-prod.iam.gserviceaccount.com 
must have permission to read the image, gcr.io/positive-shell-475102-t5/vadg-backend.
```

This happens because:
- Your Docker image is in project: `positive-shell-475102-t5`
- Your Cloud Run service is in project: `linkchat-480712`
- The Cloud Run Service Agent from `linkchat-480712` can't access images from `positive-shell-475102-t5`

## Solution Options

### ✅ Option 1: Use --source (Recommended - Easiest)

The deployment scripts already use `--source .` which builds the image automatically in the correct project. Make sure you're using the deployment script:

**Windows:**
```cmd
cd Backend
deploy.bat YOUR_API_KEY --project linkchat-480712
```

**Linux/Mac:**
```bash
cd Backend
./deploy.sh YOUR_API_KEY --project linkchat-480712
```

This will automatically build the image in the `linkchat-480712` project where Cloud Run is deployed.

---

### Option 2: Grant Cross-Project Permissions

If you need to use the existing image from `positive-shell-475102-t5`, grant permissions:

1. **Grant permission to the Cloud Run Service Agent:**
```bash
# Set the source project (where image is stored)
gcloud config set project positive-shell-475102-t5

# Grant permission to the Cloud Run Service Agent from linkchat-480712
gcloud projects add-iam-policy-binding positive-shell-475102-t5 \
  --member="serviceAccount:service-679635825980@serverless-robot-prod.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"
```

2. **Then deploy using the image:**
```bash
# Switch back to your Cloud Run project
gcloud config set project linkchat-480712

# Deploy using the image from the other project
gcloud run deploy vadg-backend \
  --image gcr.io/positive-shell-475102-t5/vadg-backend \
  --platform managed \
  --region asia-south1 \
  --allow-unauthenticated
```

---

### Option 3: Build and Push Image to Correct Project

If you want to manually build and push:

1. **Build the image:**
```bash
# Make sure you're in the Backend directory
cd Backend

# Set the correct project
gcloud config set project linkchat-480712

# Build and push the image
gcloud builds submit --tag gcr.io/linkchat-480712/vadg-backend
```

2. **Deploy using the new image:**
```bash
gcloud run deploy vadg-backend \
  --image gcr.io/linkchat-480712/vadg-backend \
  --platform managed \
  --region asia-south1 \
  --allow-unauthenticated
```

---

## Quick Fix (Recommended)

Just use the deployment script with the correct project:

```cmd
cd Backend
deploy.bat YOUR_GOOGLE_API_KEY --project linkchat-480712
```

The script will automatically:
- ✅ Build the image in the correct project
- ✅ Push it to the correct registry
- ✅ Deploy to Cloud Run
- ✅ Set up all permissions

No manual permission setup needed!

