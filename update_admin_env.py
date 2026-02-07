#!/usr/bin/env python3
"""
Script to update admin credentials in Backend/.env file
"""
import os
import re
from pathlib import Path

# Admin credentials
ADMIN_EMAIL = "m87.krishna@gmail.com"
ADMIN_PASSWORD = "Vadg@44"
ADMIN_JWT_SECRET = "9348e6fbdeafb8c7d7f963701123d609c1b7ae1d704010b98b878f943094d664"

# Get the directory where this script is located
SCRIPT_DIR = Path(__file__).parent
ENV_FILE = SCRIPT_DIR / ".env"

def update_env_file():
    """Update or create .env file with admin credentials."""
    
    # Read existing .env file if it exists
    lines = []
    if ENV_FILE.exists():
        print(f"📖 Reading existing .env file...")
        with open(ENV_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Backup
        backup_file = SCRIPT_DIR / ".env.backup"
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print(f"💾 Backup saved to .env.backup")
    else:
        print(f"📝 Creating new .env file...")
    
    # Remove old admin credentials
    updated_lines = []
    for line in lines:
        if not re.match(r'^\s*ADMIN_EMAIL\s*=', line, re.IGNORECASE) and \
           not re.match(r'^\s*ADMIN_PASSWORD\s*=', line, re.IGNORECASE) and \
           not re.match(r'^\s*ADMIN_JWT_SECRET\s*=', line, re.IGNORECASE):
            updated_lines.append(line)
    
    # Add new admin credentials at the end
    updated_lines.append(f"\n# Admin Authentication - Updated by update_admin_env.py\n")
    updated_lines.append(f"ADMIN_EMAIL={ADMIN_EMAIL}\n")
    updated_lines.append(f"ADMIN_PASSWORD={ADMIN_PASSWORD}\n")
    updated_lines.append(f"ADMIN_JWT_SECRET={ADMIN_JWT_SECRET}\n")
    
    # Write updated content
    with open(ENV_FILE, 'w', encoding='utf-8') as f:
        f.writelines(updated_lines)
    
    print(f"✅ Admin credentials updated in .env file!")
    print(f"\n📋 Updated values:")
    print(f"   ADMIN_EMAIL={ADMIN_EMAIL}")
    print(f"   ADMIN_PASSWORD={ADMIN_PASSWORD}")
    print(f"   ADMIN_JWT_SECRET={ADMIN_JWT_SECRET[:20]}...")
    print(f"\n⚠️  IMPORTANT: Restart your backend server for changes to take effect!")
    print(f"   Run: python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000")

if __name__ == "__main__":
    try:
        update_env_file()
    except Exception as e:
        print(f"❌ Error: {e}")
        exit(1)

