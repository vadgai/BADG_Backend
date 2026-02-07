# Generate Static Translations using Google Translation API

This script uses your existing Google Translation API endpoint to generate static translations for all i18n files.

## Quick Start

### Option 1: Backend Running (Recommended)
```bash
# Ensure backend is running on http://localhost:8000
cd Backend
python generate_translations.py
```

### Option 2: Windows Batch Script
```bash
# Double-click or run:
Backend\GENERATE_TRANSLATIONS.bat
```

### Option 3: Direct Import (No API)
```bash
cd Backend
python generate_translations.py
# Script will automatically use direct translation function if API unavailable
```

## How It Works

1. **Loads English source** (`Frontend/src/i18n/en.json`)
2. **Flattens all keys** (handles nested objects like `patient_form.name`)
3. **Translates each key** using `/api/translate` endpoint (Google Translation API)
4. **Updates language files** (`hi.json`, `ta.json`, `te.json`, `bn.json`, `kn.json`)
5. **Preserves existing translations** (only adds missing keys)

## Features

- ✅ Uses existing Google Translation API endpoint
- ✅ Preserves existing translations
- ✅ Handles nested JSON structure
- ✅ Progress tracking for each translation
- ✅ Automatic fallback if API unavailable
- ✅ Updates all language files in one run

## Supported Languages

- Hindi (hi)
- Tamil (ta)
- Telugu (te)
- Bengali (bn)
- Kannada (kn)

## Configuration

The script automatically detects:
- Backend API URL from environment or defaults to `http://localhost:8000`
- Translation endpoint: `/api/translate`
- Uses Google Cloud Translation API (primary) or Gemini (fallback)

## Notes

- Translations are cached by the backend API
- Missing keys will be added to all language files
- Existing translations are preserved
- Script can be run multiple times safely

