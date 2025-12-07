import json

# Paste your entire Google Sheets JSON here (with line breaks, it's ok)
raw_json = """
{
  "type": "service_account",
  "project_id": "your-project",
  "private_key_id": "your-key-id",
  "private_key": "-----BEGIN PRIVATE KEY-----\nYOUR_KEY_HERE\n-----END PRIVATE KEY-----\n",
  "client_email": "your-service-account@project.iam.gserviceaccount.com",
  "client_id": "123456789",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/your-account.iam.gserviceaccount.com"
}
"""

# Parse and minify to single line
json_obj = json.loads(raw_json)
minified = json.dumps(json_obj)
print("Copy this into your .env file:")
print(minified)