import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
key = os.getenv('GOOGLE_API_KEY')
genai.configure(api_key=key)

print('='*60)
print('AVAILABLE GEMINI MODELS')
print('='*60)

for model in genai.list_models():
    if 'generateContent' in model.supported_generation_methods:
        print(f'✅ {model.name}')
        print(f'   Display name: {model.display_name}')
        print(f'   Description: {model.description[:80]}...' if len(model.description) > 80 else f'   Description: {model.description}')
        print()

