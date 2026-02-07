# Fixing Hindi Generation in Production

## Problem
Hindi report generation works locally but not in production on Google Cloud Run.

## Root Cause
The Docker image needs to be rebuilt with the latest code changes that include:
1. Language parameter support for disease info
2. Enhanced Hindi prompt instructions
3. Better error logging

## Solution: Rebuild and Redeploy

### Step 1: Verify Local Changes
Make sure you have all the latest changes:
```bash
cd Backend
# Verify prompt files exist
ls -la prompts/report/hi.txt
ls -la prompts/followup/hi.txt
```

### Step 2: Build Docker Image
```bash
# From the Backend directory
docker build -t gcr.io/positive-shell-475102-t5/vadg-backend:latest .
```

### Step 3: Test the Image Locally (Optional but Recommended)
```bash
# Run the container locally to verify prompt files are included
docker run --rm -it gcr.io/positive-shell-475102-t5/vadg-backend:latest ls -la /app/prompts/report/

# Should show hi.txt, ta.txt, etc.
```

### Step 4: Push to Google Container Registry
```bash
# Authenticate (if not already done)
gcloud auth configure-docker

# Push the image
docker push gcr.io/positive-shell-475102-t5/vadg-backend:latest
```

### Step 5: Deploy to Cloud Run
```bash
gcloud run deploy vadg-backend \
  --image gcr.io/positive-shell-475102-t5/vadg-backend:latest \
  --platform managed \
  --region asia-south1 \
  --allow-unauthenticated
```

### Step 6: Verify Deployment
After deployment, check the logs:
```bash
# View recent logs
gcloud run services logs read vadg-backend --region asia-south1 --limit 50

# Look for these messages:
# ✅ Loaded hi report prompt from file
# ✅ Verified prompt files are present
```

### Step 7: Test Hindi Generation
1. Open your production frontend
2. Select Hindi language
3. Submit symptoms
4. Generate report
5. Check that all content is in Hindi

## Troubleshooting

### If Hindi still doesn't work:

1. **Check Cloud Run Logs:**
   ```bash
   gcloud run services logs read vadg-backend --region asia-south1 --follow
   ```
   Look for:
   - `⚠️ Prompt file not found` - means prompt files aren't in the image
   - `✅ Loaded hi report prompt` - means files are found

2. **Verify Files in Container:**
   ```bash
   # Get the service URL
   SERVICE_URL=$(gcloud run services describe vadg-backend --region asia-south1 --format 'value(status.url)')
   
   # Check health endpoint (if you add a prompt verification endpoint)
   curl $SERVICE_URL/health
   ```

3. **Rebuild from Scratch:**
   ```bash
   # Clean build
   docker build --no-cache -t gcr.io/positive-shell-475102-t5/vadg-backend:latest .
   docker push gcr.io/positive-shell-475102-t5/vadg-backend:latest
   gcloud run deploy vadg-backend \
     --image gcr.io/positive-shell-475102-t5/vadg-backend:latest \
     --platform managed \
     --region asia-south1 \
     --allow-unauthenticated
   ```

## What Changed

1. **Backend/app.py**: Added language parameter support for `/api/disease-info`
2. **Backend/prompts/prompt_loader.py**: Enhanced logging to debug missing files
3. **Backend/Dockerfile**: Added verification step to ensure prompt files are included
4. **Frontend/src/components/DiseaseInsightsCard.tsx**: Passes language parameter to backend

## Quick Deploy Script

Save this as `redeploy.sh`:
```bash
#!/bin/bash
set -e

echo "🔨 Building Docker image..."
docker build -t gcr.io/positive-shell-475102-t5/vadg-backend:latest .

echo "📤 Pushing to GCR..."
docker push gcr.io/positive-shell-475102-t5/vadg-backend:latest

echo "🚀 Deploying to Cloud Run..."
gcloud run deploy vadg-backend \
  --image gcr.io/positive-shell-475102-t5/vadg-backend:latest \
  --platform managed \
  --region asia-south1 \
  --allow-unauthenticated

echo "✅ Deployment complete!"
```

Make it executable and run:
```bash
chmod +x redeploy.sh
./redeploy.sh
```







