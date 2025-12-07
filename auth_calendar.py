from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/calendar']
flow = InstalledAppFlow.from_client_secrets_file(
    'credentials/client_secret.json', SCOPES)
creds = flow.run_local_server(port=0)

# Save credentials
with open('credentials/calendar_credentials.json', 'w') as token:
    token.write(creds.to_json())

print("✅ Calendar authenticated!")