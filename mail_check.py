import os
import smtplib
from dotenv import load_dotenv

load_dotenv()   # Load .env file

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

print("Loaded:", GMAIL_USER, GMAIL_APP_PASSWORD)  # Debug

msg = "Test email via app password"

server = smtplib.SMTP("smtp.gmail.com", 587)
server.starttls()
server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
server.sendmail(GMAIL_USER, "recipient@example.com", msg)
server.quit()
print("Email sent!")