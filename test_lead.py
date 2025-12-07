import requests
import json
from datetime import datetime, timedelta

# Format: 2025-12-10T14:30:00 (system will apply Asia/Kolkata timezone)
appointment_time = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S")

test_lead = {
    "name": "Rajesh Kumar", 
    "email": "rajesh@example.com",
    "phone": "+91-98765-43210",
    "car_model": "Tata Nexon EV",
    "appointment_datetime": appointment_time
}

url = "http://127.0.0.1:5000/webhook/lead"
print("Sending test lead...")
response = requests.post(url, json=test_lead)

print(f"\nStatus Code: {response.status_code}")
print(f"Response:\n{json.dumps(response.json(), indent=2)}")