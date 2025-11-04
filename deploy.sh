#!/bin/bash

# ============================================
# VADG Backend Deployment Script
# For Google Cloud Run
# ============================================
# Usage: ./deploy.sh YOUR_GOOGLE_API_KEY [OPTIONS]
# 
# Required:
#   - Google API Key (Gemini API)
# Optional:
#   - --mongo-uri: MongoDB connection string
#   - --email: Sender email for contact form
#   - --email-pass: Email password/app password
#   - --region: GCP region (default: asia-south1)
#   - --project: GCP project ID (default: auto-detect)
# ============================================

set -e  # Exit on error

echo "🚀 VADG Backend Deployment to Google Cloud Run"
echo "================================================"
echo ""

# Check if API key is provided
if [ -z "$1" ] || [[ "$1" == --* ]]; then
    echo "❌ Error: Google API Key not provided"
    echo ""
    echo "Usage: ./deploy.sh YOUR_GOOGLE_API_KEY [OPTIONS]"
    echo ""
    echo "Required:"
    echo "  YOUR_GOOGLE_API_KEY    Google Gemini API key"
    echo ""
    echo "Optional flags:"
    echo "  --mongo-uri URI        MongoDB connection string"
    echo "  --email EMAIL          Sender email for contact form"
    echo "  --email-pass PASS      Email password (Gmail app password)"
    echo "  --region REGION        GCP region (default: asia-south1)"
    echo "  --project PROJECT      GCP project ID (auto-detect if not set)"
    echo "  --service-name NAME    Service name (default: vadg-backend)"
    echo "  --skip-secrets         Skip Secret Manager setup"
    echo ""
    echo "Examples:"
    echo "  ./deploy.sh AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
    echo "  ./deploy.sh YOUR_KEY --mongo-uri mongodb+srv://user:pass@cluster.net/"
    echo "  ./deploy.sh YOUR_KEY --email your@gmail.com --email-pass app_password"
    exit 1
fi

# Required parameters
GOOGLE_API_KEY=$1
shift

# Default values
SERVICE_NAME="vadg-backend"
REGION="asia-south1"
PROJECT_ID=$(gcloud config get-value project 2>/dev/null || echo "")
MONGO_URI=""
SENDER_EMAIL=""
SENDER_PASSWORD=""
SKIP_SECRETS=false

# Parse optional arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --mongo-uri)
            MONGO_URI="$2"
            shift 2
            ;;
        --email)
            SENDER_EMAIL="$2"
            shift 2
            ;;
        --email-pass)
            SENDER_PASSWORD="$2"
            shift 2
            ;;
        --region)
            REGION="$2"
            shift 2
            ;;
        --project)
            PROJECT_ID="$2"
            shift 2
            ;;
        --service-name)
            SERVICE_NAME="$2"
            shift 2
            ;;
        --skip-secrets)
            SKIP_SECRETS=true
            shift
            ;;
        *)
            echo "❌ Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate project ID
if [ -z "$PROJECT_ID" ]; then
    echo "❌ Error: Could not detect GCP project ID"
    echo "Please set it with: gcloud config set project YOUR_PROJECT_ID"
    echo "Or use: ./deploy.sh YOUR_KEY --project YOUR_PROJECT_ID"
    exit 1
fi

echo ""
echo "📋 Configuration Summary:"
echo "   Project ID:  $PROJECT_ID"
echo "   Service:     $SERVICE_NAME"
echo "   Region:      $REGION"
echo "   MongoDB:     $([ -n "$MONGO_URI" ] && echo "Configured" || echo "Not configured (in-memory mode)")"
echo "   Email:       $([ -n "$SENDER_EMAIL" ] && echo "Configured ($SENDER_EMAIL)" || echo "Not configured")"
echo ""

# Validate gcloud is authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "❌ Error: Not authenticated with gcloud"
    echo "Please run: gcloud auth login"
    exit 1
fi

# Set project
echo "🔧 Setting project..."
gcloud config set project $PROJECT_ID

# Enable required APIs
echo ""
echo "🔌 Step 1/5: Enabling required APIs..."
gcloud services enable run.googleapis.com --quiet
gcloud services enable containerregistry.googleapis.com --quiet
gcloud services enable cloudbuild.googleapis.com --quiet

if [ "$SKIP_SECRETS" = false ] && ([ -n "$MONGO_URI" ] || [ -n "$SENDER_EMAIL" ]); then
    gcloud services enable secretmanager.googleapis.com --quiet
fi

echo "✅ APIs enabled"

# Create secrets if needed
if [ "$SKIP_SECRETS" = false ]; then
    echo ""
    echo "🔐 Step 2/5: Setting up Secret Manager..."
    
    # Create Google API Key secret
    if echo -n "$GOOGLE_API_KEY" | gcloud secrets create google-api-key --data-file=- 2>/dev/null; then
        echo "✅ Created secret: google-api-key"
    else
        echo "📝 Updating existing secret: google-api-key"
        echo -n "$GOOGLE_API_KEY" | gcloud secrets versions add google-api-key --data-file=-
    fi
    
    # Create MongoDB URI secret if provided
    if [ -n "$MONGO_URI" ]; then
        if echo -n "$MONGO_URI" | gcloud secrets create mongo-uri --data-file=- 2>/dev/null; then
            echo "✅ Created secret: mongo-uri"
        else
            echo "📝 Updating existing secret: mongo-uri"
            echo -n "$MONGO_URI" | gcloud secrets versions add mongo-uri --data-file=-
        fi
    fi
    
    # Create email password secret if provided
    if [ -n "$SENDER_PASSWORD" ]; then
        if echo -n "$SENDER_PASSWORD" | gcloud secrets create email-password --data-file=- 2>/dev/null; then
            echo "✅ Created secret: email-password"
        else
            echo "📝 Updating existing secret: email-password"
            echo -n "$SENDER_PASSWORD" | gcloud secrets versions add email-password --data-file=-
        fi
    fi
    
    echo "✅ Secrets configured"
fi

# Build environment variables
ENV_VARS="ALLOWED_ORIGINS=https://vadg.netlify.app,https://www.vadg.in,https://vadg.in,http://localhost:5173,http://localhost:5174"
ENV_VARS="$ENV_VARS,LOG_LEVEL=INFO"
ENV_VARS="$ENV_VARS,ENVIRONMENT=production"
ENV_VARS="$ENV_VARS,PORT=8080"

# Add non-secret env vars
if [ -n "$SENDER_EMAIL" ]; then
    ENV_VARS="$ENV_VARS,SENDER_EMAIL=$SENDER_EMAIL"
    ENV_VARS="$ENV_VARS,SMTP_SERVER=smtp.gmail.com"
    ENV_VARS="$ENV_VARS,SMTP_PORT=587"
    ENV_VARS="$ENV_VARS,RECIPIENT_EMAILS=vadg.office@gmail.com"
fi

# Build secrets mapping
SECRET_ARGS=""
if [ "$SKIP_SECRETS" = false ]; then
    SECRET_ARGS="--set-secrets=GOOGLE_API_KEY=google-api-key:latest"
    
    if [ -n "$MONGO_URI" ]; then
        SECRET_ARGS="$SECRET_ARGS,MONGO_URI=mongo-uri:latest"
    fi
    
    if [ -n "$SENDER_PASSWORD" ]; then
        SECRET_ARGS="$SECRET_ARGS,SENDER_PASSWORD=email-password:latest"
    fi
else
    # Use env vars directly if skipping secrets
    ENV_VARS="$ENV_VARS,GOOGLE_API_KEY=$GOOGLE_API_KEY"
    if [ -n "$MONGO_URI" ]; then
        ENV_VARS="$ENV_VARS,MONGO_URI=$MONGO_URI"
    fi
    if [ -n "$SENDER_PASSWORD" ]; then
        ENV_VARS="$ENV_VARS,SENDER_PASSWORD=$SENDER_PASSWORD"
    fi
fi

# Deploy the service
echo ""
echo "📦 Step 3/5: Deploying to Cloud Run..."
echo "This may take 3-5 minutes..."

DEPLOY_CMD="gcloud run deploy $SERVICE_NAME \
  --region=$REGION \
  --source . \
  --platform=managed \
  --allow-unauthenticated \
  --set-env-vars=\"$ENV_VARS\" \
  $SECRET_ARGS \
  --max-instances=20 \
  --min-instances=0 \
  --memory=1Gi \
  --cpu=1 \
  --timeout=300 \
  --port=8080 \
  --quiet"

eval $DEPLOY_CMD

if [ $? -ne 0 ]; then
    echo "❌ Deployment failed!"
    echo ""
    echo "Troubleshooting:"
    echo "1. Check if you have billing enabled: https://console.cloud.google.com/billing"
    echo "2. Verify your API key is valid"
    echo "3. Check logs: gcloud run services logs read $SERVICE_NAME --region=$REGION"
    exit 1
fi

echo ""
echo "✅ Service deployed successfully"

# Enable public access
echo ""
echo "🌐 Step 4/5: Configuring public access..."
gcloud run services add-iam-policy-binding $SERVICE_NAME \
  --region=$REGION \
  --member="allUsers" \
  --role="roles/run.invoker" \
  --quiet

echo "✅ Public access enabled"

# Get service URL
echo ""
echo "🔍 Step 5/5: Verifying deployment..."
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)')

# Test the deployment
echo "Testing health endpoint..."
if curl -f -s "${SERVICE_URL}/health" > /dev/null 2>&1; then
    echo "✅ Health check passed"
else
    echo "⚠️  Warning: Health check failed (service might still be starting)"
fi

echo ""
echo "============================================"
echo "✅ DEPLOYMENT COMPLETE!"
echo "============================================"
echo ""
echo "🎉 Your VADG backend is live at:"
echo "   $SERVICE_URL"
echo ""
echo "📊 Service Information:"
echo "   Project:  $PROJECT_ID"
echo "   Service:  $SERVICE_NAME"
echo "   Region:   $REGION"
echo "   URL:      $SERVICE_URL"
echo ""
echo "📝 Important Next Steps:"
echo ""
echo "1. 🧪 Test Your Backend:"
echo "   Health check:    curl $SERVICE_URL/health"
echo "   API docs:        Open $SERVICE_URL/docs in browser"
echo "   Root endpoint:   curl $SERVICE_URL/"
echo ""
echo "2. 🔧 Update Your Frontend:"
echo "   Add to Frontend/.env or Netlify environment:"
echo "   VITE_API_BASE_URL=$SERVICE_URL"
echo "   VITE_WS_BASE_URL=$(echo $SERVICE_URL | sed 's/https/wss/g')"
echo ""
echo "3. 🔐 Security Checklist:"
if [ "$SKIP_SECRETS" = true ]; then
    echo "   ⚠️  You used --skip-secrets (less secure)"
    echo "   Consider using Secret Manager for production"
else
    echo "   ✅ Secrets stored in Secret Manager"
fi
if [ -n "$MONGO_URI" ]; then
    echo "   ✅ MongoDB configured"
else
    echo "   ⚠️  No MongoDB (using in-memory storage)"
    echo "   Data will be lost on service restart"
fi
if [ -n "$SENDER_EMAIL" ]; then
    echo "   ✅ Email notifications configured"
else
    echo "   ℹ️  Email not configured (contact form won't send emails)"
fi
echo ""
echo "4. 📊 Monitor Your Service:"
echo "   Logs:     gcloud run services logs read $SERVICE_NAME --region=$REGION --limit=50"
echo "   Metrics:  https://console.cloud.google.com/run/detail/$REGION/$SERVICE_NAME/metrics?project=$PROJECT_ID"
echo "   Console:  https://console.cloud.google.com/run?project=$PROJECT_ID"
echo ""
echo "5. 🔄 To Update/Redeploy:"
echo "   Run this script again with the same parameters"
echo "   Or use: gcloud run deploy $SERVICE_NAME --region=$REGION --source ."
echo ""
echo "6. 🗑️  To Delete Service:"
echo "   gcloud run services delete $SERVICE_NAME --region=$REGION"
echo ""
echo "💰 Estimated Cost:"
echo "   First 2 million requests/month: FREE"
echo "   Additional requests: ~\$0.40 per million"
echo ""
echo "🎊 Happy deploying!"
echo "============================================"

