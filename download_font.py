import requests
import os

# Download directly from fonts.gstatic.com (Google's CDN)
# This URL serves the actual Noto Sans Devanagari Regular font
url = "https://github.com/notofonts/devanagari/raw/main/fonts/ttf/hinted/NotoSansDevanagari-Regular.ttf"

font_path = os.path.join(os.path.dirname(__file__), 'fonts', 'NotoSansDevanagari-Regular.ttf')

print(f"Downloading font from: {url}")
print(f"Saving to: {font_path}")

try:
    response = requests.get(url, timeout=30)
    if response.status_code == 200:
        with open(font_path, 'wb') as f:
            f.write(response.content)
        print(f"✅ Font downloaded: {len(response.content)} bytes")
        
        # Verify it's a real TTF
        with open(font_path, 'rb') as f:
            header = f.read(4)
            if header in [b'\x00\x01\x00\x00', b'OTTO', b'true', b'typ1']:
                print("✅ Valid TTF file confirmed")
            else:
                print(f"⚠️ Warning: Header is {header.hex()}, may not be valid TTF")
    else:
        print(f"❌ Download failed: HTTP {response.status_code}")
except Exception as e:
    print(f"❌ Error: {e}")













