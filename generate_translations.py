"""
Generate static translations for all i18n files using Google Translation API
This script uses the existing /api/translate endpoint to populate translation JSON files.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, Any

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent))

# Configuration
FRONTEND_I18N_DIR = Path(__file__).parent.parent / "Frontend" / "src" / "i18n"
ENGLISH_FILE = FRONTEND_I18N_DIR / "en.json"

# Language codes mapping
LANGUAGE_CODES = {
    "hi": "Hindi",
    "ta": "Tamil", 
    "te": "Telugu",
    "bn": "Bengali",
    "kn": "Kannada"
}

# Import translate endpoint (or use API directly)
try:
    import requests
    # Try to get API URL from environment or use default
    import os
    BASE_API_URL = os.getenv("BASE_API_URL", "http://localhost:8000")
    USE_API = True
    API_URL = f"{BASE_API_URL}/api/translate"
    print(f"🌐 Using API endpoint: {API_URL}")
except Exception as e:
    USE_API = False
    print(f"⚠️  API mode failed ({e}), trying direct import...")
    try:
        from routes.translate import translate_text_smart
        print("✅ Using direct translation function")
    except ImportError as ie:
        print(f"❌ Cannot import translation function: {ie}")
        print("💡 Please ensure backend is running or install dependencies:")
        print("   pip install requests")
        sys.exit(1)


def flatten_dict(d: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, str]:
    """Flatten nested dictionary to dot-notation keys"""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def unflatten_dict(flat: Dict[str, str], sep: str = ".") -> Dict[str, Any]:
    """Convert dot-notation keys back to nested dictionary"""
    result: Dict[str, Any] = {}
    for key, value in flat.items():
        parts = key.split(sep)
        d = result
        for part in parts[:-1]:
            if part not in d:
                d[part] = {}
            d = d[part]
        d[parts[-1]] = value
    return result


def translate_via_api(text: str, target_lang: str) -> str:
    """Translate text using the /api/translate endpoint"""
    try:
        response = requests.post(
            API_URL,
            json={"text": text, "targetLang": target_lang},
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("translated", text)
        else:
            print(f"⚠️  API error {response.status_code}: {response.text}")
            return text
    except Exception as e:
        print(f"⚠️  API call failed: {e}")
        return text


def translate_via_function(text: str, target_lang: str) -> str:
    """Translate text using direct function call"""
    try:
        return translate_text_smart(text, target_lang)
    except Exception as e:
        print(f"⚠️  Translation function error: {e}")
        return text


def translate_text(text: str, target_lang: str) -> str:
    """Translate text using available method"""
    if USE_API:
        return translate_via_api(text, target_lang)
    else:
        return translate_via_function(text, target_lang)


def update_translation_file(lang_code: str, english_flat: Dict[str, str], translations: Dict[str, str]):
    """Update translation file with new translations"""
    lang_file = FRONTEND_I18N_DIR / f"{lang_code}.json"
    
    # Load existing file if it exists
    existing = {}
    if lang_file.exists():
        try:
            with open(lang_file, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        except:
            existing = {}
    
    # Flatten existing translations
    existing_flat = flatten_dict(existing)
    
    # Update with new translations
    existing_flat.update(translations)
    
    # Convert back to nested structure
    updated = unflatten_dict(existing_flat)
    
    # Save file
    with open(lang_file, 'w', encoding='utf-8') as f:
        json.dump(updated, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Updated {lang_file}")


def generate_translations():
    """Generate translations for all languages"""
    print("=" * 60)
    print("🌐 Generating Static Translations using Google Translation API")
    print("=" * 60)
    
    # Load English source file
    if not ENGLISH_FILE.exists():
        print(f"❌ English file not found: {ENGLISH_FILE}")
        return
    
    with open(ENGLISH_FILE, 'r', encoding='utf-8') as f:
        english_data = json.load(f)
    
    # Flatten English translations
    english_flat = flatten_dict(english_data)
    
    print(f"\n📝 Found {len(english_flat)} translation keys in English file")
    print(f"🌍 Generating translations for {len(LANGUAGE_CODES)} languages\n")
    
    # Process each target language
    for lang_code, lang_name in LANGUAGE_CODES.items():
        print(f"\n{'='*60}")
        print(f"Translating to {lang_name} ({lang_code})...")
        print(f"{'='*60}")
        
        translations = {}
        total = len(english_flat)
        
        # Translate each key
        for idx, (key, english_text) in enumerate(english_flat.items(), 1):
            # Skip if empty or already translated
            if not english_text or not isinstance(english_text, str):
                translations[key] = english_text
                continue
            
            print(f"[{idx}/{total}] Translating: {key[:50]}...", end=" ", flush=True)
            
            # Translate using Google Translation API
            translated = translate_text(english_text, lang_code)
            translations[key] = translated
            
            print(f"✅")
        
        # Update translation file
        update_translation_file(lang_code, english_flat, translations)
        
        print(f"✅ Completed {lang_name} translations")
    
    print(f"\n{'='*60}")
    print("✅ All translations generated successfully!")
    print(f"{'='*60}")


if __name__ == "__main__":
    try:
        generate_translations()
    except KeyboardInterrupt:
        print("\n\n⚠️  Translation generation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

