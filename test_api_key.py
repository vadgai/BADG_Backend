import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
key = os.getenv('GOOGLE_API_KEY')

print(f'API Key loaded: {key[:20]}...' if key else 'NO API KEY!')
print(f'API Key length: {len(key)}' if key else 'N/A')

try:
    genai.configure(api_key=key)
    print('✅ API key configured')
    
    print('\nTrying to list models...')
    models = list(genai.list_models())
    print(f'Found {len(models)} models total')
    
    content_models = [m for m in models if 'generateContent' in m.supported_generation_methods]
    print(f'Found {len(content_models)} models that support generateContent')
    
    if content_models:
        print('\nAvailable models:')
        for model in content_models:
            print(f'  ✅ {model.name}')
    else:
        print('\n❌ NO MODELS AVAILABLE FOR CONTENT GENERATION!')
        print('This might mean:')
        print('  - API key is invalid or expired')
        print('  - API is not enabled')
        print('  - Account has no access')
        
except Exception as e:
    print(f'\n❌ ERROR: {type(e).__name__}: {e}')
    print('\nThis usually means:')
    print('  - Invalid API key')
    print('  - API key expired')
    print('  - Network issue')
    print('  - API not enabled in Google Cloud Console')

