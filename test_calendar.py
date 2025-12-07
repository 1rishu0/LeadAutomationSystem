import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta

# Load credentials
with open('./credentials/calendar_credentials.json', 'r') as f:
    creds_dict = json.loads(f.read())

print(f"Service Account Email: {creds_dict['client_email']}")
print("\n⚠️ IMPORTANT: Have you shared your Google Calendar with this email?")
print("   Go to: calendar.google.com")
print("   Settings → Share with specific people")
print("   Add this email → Give 'Make changes to events' permission\n")

# Try to create a test event
try:
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    creds = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=SCOPES
    )
    service = build('calendar', 'v3', credentials=creds)
    
    # Test: List calendars
    print("Testing calendar access...")
    calendar_list = service.calendarList().list().execute()
    print(f"✅ Found {len(calendar_list.get('items', []))} calendars")
    
    for cal in calendar_list.get('items', []):
        print(f"  - {cal['summary']} (ID: {cal['id']})")
    
    # Try to create a test event
    print("\nCreating test event...")
    start_time = datetime.now() + timedelta(days=1)
    end_time = start_time + timedelta(hours=1)
    
    event = {
        'summary': 'TEST - Lead Automation',
        'start': {
            'dateTime': start_time.isoformat(),
            'timeZone': 'America/New_York',
        },
        'end': {
            'dateTime': end_time.isoformat(),
            'timeZone': 'America/New_York',
        },
    }
    
    created_event = service.events().insert(
        calendarId='primary',
        body=event
    ).execute()
    
    print(f"✅ Test event created successfully!")
    print(f"   Event ID: {created_event['id']}")
    print(f"   Link: {created_event.get('htmlLink')}")
    
except Exception as e:
    print(f"❌ Calendar test failed: {e}")
    print("\nPossible issues:")
    print("1. Calendar not shared with service account")
    print("2. Google Calendar API not enabled")
    print("3. Using wrong calendar ID")