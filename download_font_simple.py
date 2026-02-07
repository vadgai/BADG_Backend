import requests

# Use direct jsdelivr CDN which serves raw files properly
url = 'https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/notosansdevanagari/NotoSansDevanagari-Regular.ttf'

print(f"Downloading from: {url}")

r = requests.get(url)
print(f"Status: {r.status_code}")
print(f"Content-Type: {r.headers.get('content-type')}")
print(f"Size: {len(r.content)} bytes")
print(f"First 4 bytes (hex): {r.content[:4].hex()}")

# Check if it's a valid TTF
valid_headers = [b'\x00\x01\x00\x00', b'OTTO', b'true', b'typ1']
if any(r.content[:4] == h for h in valid_headers):
    print("✅ Valid TTF header detected")
else:
    print(f"⚠️ Unexpected header - may not be TTF")

with open('fonts/NotoSansDevanagari-Regular.ttf', 'wb') as f:
    f.write(r.content)
    
print(f"✅ Saved to: fonts/NotoSansDevanagari-Regular.ttf")













