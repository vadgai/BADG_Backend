# 🔑 Gemini API Multi-Key Setup Guide

## Overview

Your VADG system now supports **up to 10 Gemini API keys** with automatic fallback! If one key fails (due to rate limits, quota exhaustion, or errors), the system will automatically try the next key in sequence.

## ✨ Features

- ✅ **Automatic Fallback**: Seamlessly switches to the next API key when one fails
- ✅ **Zero Downtime**: No interruption to user experience when a key fails
- ✅ **Easy Configuration**: Just add keys to your `.env` file
- ✅ **Centralized Management**: All API calls go through a single manager
- ✅ **Detailed Logging**: Know which key is being used at any time
- ✅ **Backward Compatible**: Still works with legacy single-key setup

## 🚀 Quick Start

### Step 1: Get Your API Keys

1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Create up to 10 API keys (you can create multiple keys from the same account)
3. Copy each key

### Step 2: Configure Your `.env` File

1. Copy `Backend/env.example` to `Backend/.env`
2. Add your API keys:

```bash
# Primary key (required)
GEMINI_API_KEY_1=AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

# Add as many backup keys as you want (optional)
GEMINI_API_KEY_2=AIzaSyYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY
GEMINI_API_KEY_3=AIzaSyZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ
# ... up to GEMINI_API_KEY_10
```

### Step 3: Restart Your Backend

```bash
cd Backend
python app.py
```

That's it! The system will automatically use the keys with fallback support.

## 📋 How It Works

### Automatic Fallback Flow

```
Request comes in
    ↓
Try API Key #1
    ↓
    ├─ Success → Return response ✅
    ↓
    └─ Failure → Try API Key #2
        ↓
        ├─ Success → Return response ✅
        ↓
        └─ Failure → Try API Key #3
            ↓
            ... (continues through all keys)
            ↓
            └─ All failed → Return fallback response ⚠️
```

### Where Fallback is Used

The multi-key system is integrated into:

1. **Disease Mapping** (`Backend/symptom_mapping/mapping.py`)
2. **Follow-up Questions** (`Backend/Followup_Generation/followup.py`)
3. **Report Generation** (`Backend/diagnosis_report/report.py`)
4. **Symptom Processing** (`Backend/symptom_processing/symptom.py`)

## 🧪 Testing Your Setup

### Method 1: Check Startup Logs

When you start the backend, you'll see:

```
✅ Loaded 10 Gemini API key(s)
   Key 1: AIzaSyXXXX...
   Key 2: AIzaSyYYYY...
   ...
🎉 GEMINI API INITIALIZED SUCCESSFULLY
   Using API key #1 of 10
   Model: gemini-2.5-flash
```

### Method 2: Test All Keys Programmatically

Create a test script `test_api_keys.py`:

```python
import sys
sys.path.append('Backend')

from utils.gemini_api_manager import test_all_api_keys, get_current_key_info

# Test all configured keys
print("Testing all API keys...")
results = test_all_api_keys()

print(f"\n📊 Results:")
print(f"Total keys configured: {results['total_keys']}")
print(f"Working keys: {results['working_keys']}")
print(f"Failed keys: {results['failed_keys']}")

print("\n🔍 Detailed Results:")
for key_info in results['keys']:
    status_icon = "✅" if key_info['status'] == 'working' else "❌"
    print(f"{status_icon} Key #{key_info['index']}: {key_info['status']}")
    if key_info['error']:
        print(f"   Error: {key_info['error']}")

# Check current active key
print("\n🔑 Current Active Key:")
current = get_current_key_info()
print(f"Using key #{current['current_index']} of {current['total_keys']}")
print(f"Model: {current['model_name']}")
print(f"Available: {current['model_available']}")
```

Run it:

```bash
cd Backend
python test_api_keys.py
```

### Method 3: Manual API Call Test

```python
import sys
sys.path.append('Backend')

from utils.gemini_api_manager import generate_content_with_fallback

# Try generating content
success, response, error = generate_content_with_fallback("Say hello!")

if success:
    print(f"✅ Success! Response: {response}")
else:
    print(f"❌ Failed: {error}")
```

## 🎯 Usage Examples

### Basic Usage (Automatic Fallback)

The system is already integrated into all your modules. Just use them normally:

```python
from utils.gemini_api_manager import get_gemini_model, generate_content_with_fallback

# Option 1: Get the model instance
model_available, model = get_gemini_model()
if model_available:
    # Use model as normal
    response = model.generate_content("Your prompt")
```

### Advanced Usage (Manual Control)

```python
from utils.gemini_api_manager import generate_content_with_fallback

# Generate content with custom retry limit
success, response, error = generate_content_with_fallback(
    prompt="Your prompt here",
    max_retries=5  # Try maximum 5 keys instead of all 10
)

if success:
    print(f"Response: {response}")
else:
    print(f"Error: {error}")
```

## 📊 Monitoring & Logs

### Understanding Log Messages

**Initialization:**
```
✅ Loaded 10 Gemini API key(s)        # Keys loaded successfully
🎉 GEMINI API INITIALIZED              # System ready
```

**During Operation:**
```
🔧 Attempting to configure with API key #1...  # Trying a key
✅ Successfully configured with API key #1      # Key works
❌ Failed to configure with API key #1: ...     # Key failed
🔄 Trying fallback API key #2...                # Switching to next key
```

**All Keys Exhausted:**
```
❌ ALL API KEYS FAILED!
   Tried 10 API key(s)
   Please check your API keys and quotas
```

## 🛠️ Troubleshooting

### Issue: "No API keys available"

**Cause**: No keys configured in `.env`

**Solution**: 
1. Check `Backend/.env` exists
2. Ensure at least `GEMINI_API_KEY_1` is set
3. Restart the backend

### Issue: "All API keys failed"

**Possible Causes**:
1. All keys have reached their quota/rate limit
2. Keys are invalid
3. Network connectivity issues
4. Google AI service outage

**Solutions**:
1. Check [Google AI Studio](https://console.cloud.google.com/) for quota status
2. Verify keys are valid
3. Wait for rate limits to reset (usually hourly)
4. Add more API keys

### Issue: Keys working but still getting errors

**Check**:
1. Model name is correct (`gemini-2.0-flash` by default)
2. Your prompt isn't triggering safety filters
3. Response isn't too large

## 💡 Best Practices

### 1. Key Distribution Strategy

**Option A: Multiple Free Tier Keys**
- Create keys from different Google accounts
- Each gets separate free quota
- Good for development/testing

**Option B: Multiple Paid Keys**
- Better rate limits
- More reliable
- Recommended for production

### 2. Key Rotation

Regularly rotate your keys for security:

```bash
# In .env
GEMINI_API_KEY_1=new_key_here  # Replace old key
GEMINI_API_KEY_2=old_key_here  # Move old key to backup
```

### 3. Monitoring Usage

1. Check Google AI Studio dashboard regularly
2. Monitor backend logs for fallback frequency
3. If fallback happens often, add more keys or upgrade quota

### 4. Security

- ✅ Never commit `.env` to git
- ✅ Use environment variables in production
- ✅ Rotate keys monthly
- ✅ Monitor for unauthorized usage
- ❌ Don't share keys
- ❌ Don't hardcode keys in source files

## 🔧 Configuration Options

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY_1` | Yes | Primary API key |
| `GEMINI_API_KEY_2` to `GEMINI_API_KEY_10` | No | Backup keys |
| `GOOGLE_API_KEY` | No | Legacy fallback (if no numbered keys) |
| `GEMINI_API_KEY` | No | Legacy fallback (if no numbered keys) |

### Default Behavior

- **Model**: `gemini-2.0-flash`
- **Max Retries**: All available keys
- **Timeout**: 30 seconds per request
- **Fallback**: Deterministic responses when all keys fail

## 📚 Additional Resources

- [Google AI Studio](https://makersuite.google.com/)
- [Gemini API Documentation](https://ai.google.dev/docs)
- [Pricing & Quotas](https://ai.google.dev/pricing)
- [Rate Limits](https://ai.google.dev/docs/rate_limits)

## 🆘 Support

If you encounter issues:

1. Check the logs: `Backend/logs/` (if logging is configured)
2. Run the test script: `python test_api_keys.py`
3. Verify your `.env` configuration
4. Check Google AI Studio for quota/key status

## 🎉 Success!

Your VADG system now has enterprise-grade API key management with automatic fallback. Enjoy uninterrupted service! 🚀

