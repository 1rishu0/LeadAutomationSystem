import json
import re

# Read the problematic file
with open('./credentials/sheets_credentials.json', 'r', encoding='utf-8') as f:
    content = f.read()

# Try to fix common issues
try:
    # Remove any BOM characters
    content = content.replace('\ufeff', '')
    
    # Parse it
    data = json.loads(content)
    
    # Re-save properly
    with open('./credentials/sheets_credentials.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    
    print("✅ JSON fixed and saved!")
    
except Exception as e:
    print(f"❌ Could not auto-fix: {e}")
    print("\nPlease download a fresh JSON key from Google Cloud Console")