"""
Quick test to check if Google Cloud Translation API is working
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

print("=" * 60)
print("Testing Google Cloud Translation API")
print("=" * 60)
print()

# Check environment variables
project_id = os.getenv("GCLOUD_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

print("📋 Configuration:")
print(f"   GCLOUD_PROJECT_ID: {project_id or '❌ NOT SET'}")
print(f"   GOOGLE_APPLICATION_CREDENTIALS: {creds_path or '❌ NOT SET'}")
print()

# Try to import and use Google Cloud Translation
try:
    from google.cloud import translate_v3 as translate
    print("✅ google-cloud-translate package is installed")
    
    # Try to create client
    client = translate.TranslationServiceClient()
    print("✅ TranslationServiceClient created successfully")
    
    if not project_id:
        print()
        print("❌ ERROR: GCLOUD_PROJECT_ID not set!")
        print("   Add to Backend/.env:")
        print("   GCLOUD_PROJECT_ID=your-project-id")
        exit(1)
    
    # Try actual translation
    print()
    print("🧪 Testing translation...")
    
    parent = f"projects/{project_id}/locations/global"
    request = translate.TranslateTextRequest(
        parent=parent,
        contents=["Do you have fever?"],
        mime_type="text/plain",
        target_language_code="hi",
    )
    
    response = client.translate_text(request=request)
    
    if response and response.translations:
        translated = response.translations[0].translated_text
        print(f"✅ Translation successful!")
        print(f"   English: Do you have fever?")
        print(f"   Hindi: {translated}")
        print()
        print("=" * 60)
        print("✅ Google Cloud Translation is WORKING!")
        print("=" * 60)
    else:
        print("❌ No translation received")
        
except ImportError as e:
    print()
    print("❌ google-cloud-translate not installed!")
    print("   Run: pip install google-cloud-translate")
    print()
    
except Exception as e:
    print()
    print(f"❌ Error: {str(e)}")
    print()
    
    if "Could not automatically determine credentials" in str(e):
        print("💡 FIX:")
        print("   Option 1: Run: gcloud auth application-default login")
        print("   Option 2: Set GOOGLE_APPLICATION_CREDENTIALS in .env")
        print()
    
    elif "API has not been used in project" in str(e):
        print("💡 FIX:")
        print(f"   Run: gcloud services enable translate.googleapis.com --project={project_id}")
        print()
    
    elif "Permission denied" in str(e):
        print("💡 FIX:")
        print("   Your service account needs 'Cloud Translation API User' role")
        print()
    
    print("=" * 60)
    print("⚠️  Google Cloud Translation NOT working")
    print("   Translation will use Gemini fallback")
    print("=" * 60)


