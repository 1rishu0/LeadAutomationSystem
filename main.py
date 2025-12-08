import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum
import re
import hashlib

# Third-party imports
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from google.oauth2 import service_account
from groq import Groq
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class NotificationChannel(Enum):
    """Notification delivery channels - all FREE"""
    EMAIL = "email"
    DISCORD = "discord"


@dataclass
class Lead:
    """Lead data structure"""
    name: str
    email: str
    phone: str
    car_model: str
    appointment_datetime: str
    intent_score: Optional[float] = None
    timestamp: Optional[str] = None
    lead_id: Optional[str] = None
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if not self.lead_id:
            # Generate unique lead ID from email + phone
            unique_string = f"{self.email}{self.phone}".lower()
            self.lead_id = hashlib.md5(unique_string.encode()).hexdigest()[:12]


@dataclass
class ProcessedLead:
    """Processed lead with LLM analysis"""
    name: str
    phone: str
    model: str
    datetime: str
    intent_score: float


class LeadValidator:
    """Validates lead data"""
    
    @staticmethod
    def validate_email(email: str) -> bool:
        if not email:
            return False
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validate_phone(phone: str) -> bool:
        if not phone:
            return False
        # Remove common separators
        clean_phone = phone.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
        pattern = r'^\+?1?\d{9,15}$'
        return bool(re.match(pattern, clean_phone))
    
    @staticmethod
    def validate_datetime(dt_string: str) -> bool:
        if not dt_string:
            return False
        try:
            dt = datetime.fromisoformat(dt_string.replace('Z', '+00:00'))
            # Make comparison timezone-aware
            now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
            # Ensure appointment is in the future (with small buffer for testing)
            if dt < now - timedelta(minutes=5):
                logger.warning(f"Appointment time is in the past: {dt_string}")
            return True
        except ValueError as e:
            logger.error(f"Invalid datetime format: {dt_string}, Error: {e}")
            return False
    
    @staticmethod
    def validate_lead_data(data: Dict[str, str]) -> tuple[bool, List[str]]:
        """Validate all required fields"""
        errors = []
        required_fields = ['name', 'email', 'phone', 'car_model', 'appointment_datetime']
        
        for field in required_fields:
            if field not in data or not data[field]:
                errors.append(f"Missing required field: {field}")
        
        if not errors:
            if not LeadValidator.validate_email(data.get('email', '')):
                errors.append("Invalid email format")
            if not LeadValidator.validate_phone(data.get('phone', '')):
                errors.append("Invalid phone format")
            if not LeadValidator.validate_datetime(data.get('appointment_datetime', '')):
                errors.append("Invalid datetime format (use ISO 8601)")
        
        return len(errors) == 0, errors


class GroqProcessor:
    """
    Uses Groq API - 100% FREE with generous limits
    - 14,400 requests per day
    - Faster than OpenAI
    - No credit card required
    
    Get API key: https://console.groq.com
    """
    
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Groq API key is required")
        try:
            # Clear any proxy environment variables that might interfere
            import os
            proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']
            saved_proxies = {}
            
            for var in proxy_vars:
                if var in os.environ:
                    saved_proxies[var] = os.environ[var]
                    del os.environ[var]
            
            # Initialize Groq client without proxy interference
            self.client = Groq(api_key=api_key)
            
            # Restore proxy settings
            for var, value in saved_proxies.items():
                os.environ[var] = value
                
            logger.info("Groq client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Groq client: {e}")
            raise
        self.max_retries = 3
    
    def analyze_lead(self, lead: Lead) -> ProcessedLead:
        """
        Send lead to Groq for analysis and get structured JSON response
        Model: llama-3.3-70b-versatile (FREE)
        """
        prompt = f"""
        Analyze this car dealership lead and return a strict JSON object with intent scoring.
        
        Lead Information:
        - Name: {lead.name}
        - Email: {lead.email}
        - Phone: {lead.phone}
        - Car Model: {lead.car_model}
        - Appointment: {lead.appointment_datetime}
        
        Calculate an intent_score (0.0 to 1.0) based on:
        - Email domain quality (corporate vs free email) - corporate emails get +0.2
        - Car model (luxury vs economy) - luxury models get +0.3
        - Appointment timing (urgency) - appointments within 3 days get +0.2
        - Base score is 0.5
        
        Return ONLY valid JSON in this exact format:
        {{
            "name": "{lead.name}",
            "phone": "{lead.phone}",
            "model": "{lead.car_model}",
            "datetime": "{lead.appointment_datetime}",
            "intent_score": 0.75
        }}
        """
        
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model="llama-3.3-70b-versatile", 
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a lead qualification assistant. Return only valid JSON."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )
                
                result = json.loads(response.choices[0].message.content)
                logger.info(f"Groq analysis complete for {lead.name} (attempt {attempt + 1})")
                
                # Ensure intent_score is within bounds
                result['intent_score'] = max(0.0, min(1.0, float(result['intent_score'])))
                
                return ProcessedLead(**result)
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Groq response (attempt {attempt + 1}): {e}")
                if attempt == self.max_retries - 1:
                    break
            except Exception as e:
                logger.error(f"Groq processing failed (attempt {attempt + 1}): {e}")
                if attempt == self.max_retries - 1:
                    break
        
        # Fallback to basic processing with warning flag
        logger.warning(f"Using fallback processing for {lead.name} - manual review recommended")
        return ProcessedLead(
            name=lead.name,
            phone=lead.phone,
            model=lead.car_model,
            datetime=lead.appointment_datetime,
            intent_score=0.5  # Flag for manual review
        )


class GoogleSheetsLogger:
    """
    Logs data to Google Sheets - 100% FREE
    No limits for personal use
    """
    
    def __init__(self, credentials_json: str, spreadsheet_name: str):
        if not credentials_json:
            raise ValueError("Google Sheets credentials are required")
        if not spreadsheet_name:
            raise ValueError("Spreadsheet name is required")
            
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        
        try:
            creds_dict = json.loads(credentials_json)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            self.client = gspread.authorize(creds)
            self.spreadsheet_name = spreadsheet_name
            self._ensure_sheet_exists()
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse credentials JSON: {e}")
            raise ValueError("Invalid JSON format for Google Sheets credentials")
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets: {e}")
            raise
    
    def _ensure_sheet_exists(self):
        """Ensure the spreadsheet exists and has proper headers"""
        try:
            sheet = self.client.open(self.spreadsheet_name).sheet1
            # Check if headers exist
            headers = sheet.row_values(1)
            if not headers:
                sheet.append_row([
                    "Timestamp", "Name", "Email", "Phone", 
                    "Car Model", "Appointment", "Intent Score"
                ])
                logger.info("Created headers in Google Sheet")
        except gspread.SpreadsheetNotFound:
            logger.error(f"Spreadsheet '{self.spreadsheet_name}' not found. Please create it first.")
            raise
    
    def lead_exists(self, lead_id: str) -> bool:
        """Check if lead already exists to prevent duplicates"""
        try:
            sheet = self.client.open(self.spreadsheet_name).sheet1
            records = sheet.get_all_records()
            # Check by Name, Email, or Phone (since Lead ID column removed)
            return any(
                r.get('Email') == lead_id or 
                r.get('Phone') == lead_id 
                for r in records
            )
        except Exception as e:
            logger.error(f"Failed to check for duplicate lead: {e}")
            return False
    
    def log_lead(self, lead: Lead, processed: ProcessedLead) -> bool:
        """Log lead data to Google Sheets"""
        try:
            # Check for duplicates
            if self.lead_exists(lead.lead_id):
                logger.warning(f"Lead {lead.lead_id} already exists - skipping duplicate")
                return False
            
            sheet = self.client.open(self.spreadsheet_name).sheet1
            
            row = [
                lead.timestamp,
                processed.name,
                lead.email,
                processed.phone,
                processed.model,
                processed.datetime,
                processed.intent_score
            ]
            
            sheet.append_row(row)
            logger.info(f"Logged lead to Google Sheets: {processed.name} (ID: {lead.lead_id})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to log to Google Sheets: {e}")
            return False
    
    def get_all_leads(self) -> list:
        """Get all leads from sheet for dashboard"""
        try:
            sheet = self.client.open(self.spreadsheet_name).sheet1
            return sheet.get_all_records()
        except Exception as e:
            logger.error(f"Failed to get leads: {e}")
            return []
    
    def update_lead_status(self, lead_id: str, status: str, notes: str = "") -> bool:
        """Update lead status and notes"""
        try:
            sheet = self.client.open(self.spreadsheet_name).sheet1
            cell = sheet.find(lead_id, in_column=2)
            if cell:
                sheet.update_cell(cell.row, 9, status)  # Status column
                if notes:
                    sheet.update_cell(cell.row, 10, notes)  # Notes column
                logger.info(f"Updated lead {lead_id} status to {status}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to update lead status: {e}")
            return False


class CalendarManager:
    """
    Manages Google Calendar events using Service Account
    """
    
    def __init__(self, credentials_json: str, calendar_id: str = 'primary'):
        if not credentials_json:
            raise ValueError("Google Calendar credentials are required")
        
        try:
            creds_dict = json.loads(credentials_json)
            # Use service account credentials
            SCOPES = ['https://www.googleapis.com/auth/calendar']
            creds = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=SCOPES
            )
            self.service = build('calendar', 'v3', credentials=creds)
            self.calendar_id = calendar_id
            logger.info("Calendar manager initialized successfully")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse calendar credentials JSON: {e}")
            raise ValueError("Invalid JSON format for Google Calendar credentials")
        except Exception as e:
            logger.error(f"Failed to initialize CalendarManager: {e}")
            raise
    
    def create_event(self, lead: Lead, processed: ProcessedLead, timezone: str = 'America/New_York') -> Optional[str]:
        """Create a Google Calendar event"""
        try:
            start_time = datetime.fromisoformat(processed.datetime.replace('Z', '+00:00'))
            end_time = start_time + timedelta(hours=1)
            
            # Create a simple meeting link (you can use Zoom, Google Meet web link, or any other)
            meet_link = f"https://meet.google.com/new"  # Generic Meet link - user can create their own
            
            event = {
                'summary': f'Car Consultation - {processed.model}',
                'description': f"""Lead consultation with {processed.name}

Email: {lead.email}
Phone: {processed.phone}
Intent Score: {processed.intent_score:.2f}
Lead ID: {lead.lead_id}

Meeting Link: {meet_link}

Please review lead details before the meeting.
Send calendar invite manually to: {lead.email}""",
                'start': {
                    'dateTime': start_time.isoformat(),
                    'timeZone': timezone,
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': timezone,
                },
                # Service accounts can't create Google Meet conferences without Workspace
                # You can add a manual meeting link in the description instead
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'popup', 'minutes': 30},
                        {'method': 'popup', 'minutes': 60},
                    ],
                },
            }
            
            logger.info(f"Attempting to create calendar event for {lead.name}")
            event_result = self.service.events().insert(
                calendarId=self.calendar_id,
                body=event
            ).execute()
            
            event_link = event_result.get('htmlLink', '')
            event_id = event_result.get('id', '')
            logger.info(f"Calendar event created successfully: {event_link}")
            
            # Return the generic meet link
            return meet_link
            
        except Exception as e:
            logger.error(f"Failed to create calendar event: {type(e).__name__}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None


class NotificationService:
    """
    Sends notifications via FREE channels only
    - Discord (Free Slack alternative)
    - Gmail (Free email)
    """
    
    def __init__(self):
        self.discord_webhook = os.getenv('DISCORD_WEBHOOK_URL')
        self.gmail_user = os.getenv('GMAIL_USER')
        self.gmail_password = os.getenv('GMAIL_APP_PASSWORD')
        
        # Validate configuration
        if not self.gmail_user or not self.gmail_password:
            logger.warning("Gmail credentials not configured - email notifications disabled")
        if not self.discord_webhook:
            logger.warning("Discord webhook not configured - Discord notifications disabled")
    
    def send_notification(
        self,
        lead: Lead,
        processed: ProcessedLead,
        meet_link: Optional[str],
        channel: NotificationChannel
    ) -> bool:
        """Send notification through specified FREE channel"""
        
        if channel == NotificationChannel.DISCORD and self.discord_webhook:
            return self._send_discord(lead, processed, meet_link)
        elif channel == NotificationChannel.EMAIL and self.gmail_user:
            return self._send_gmail(lead, processed, meet_link)
        else:
            logger.warning(f"Notification channel {channel.value} not configured")
            return False
    
    def _send_discord(self, lead: Lead, processed: ProcessedLead, meet_link: Optional[str]) -> bool:
        """Send Discord notification"""
        try:
            # Determine urgency color based on intent score
            color = 15158332 if processed.intent_score >= 0.8 else 5814783  # Red for high intent, purple for normal
            
            embed = {
                "title": f"🚗 New Lead: {processed.name}",
                "color": color,
                "fields": [
                    {"name": "📧 Email", "value": lead.email, "inline": True},
                    {"name": "📱 Phone", "value": processed.phone, "inline": True},
                    {"name": "🚙 Model", "value": processed.model, "inline": True},
                    {"name": "📊 Intent Score", "value": f"{processed.intent_score:.2f}/1.0", "inline": True},
                    {"name": "🆔 Lead ID", "value": lead.lead_id, "inline": True},
                    {"name": "📅 Appointment", "value": processed.datetime, "inline": False}
                ],
                "timestamp": datetime.utcnow().isoformat(),
                "footer": {"text": "Lead Automation System"}
            }
            
            if meet_link:
                embed["fields"].append({
                    "name": "🎥 Google Meet",
                    "value": f"[Join Meeting]({meet_link})",
                    "inline": False
                })
            
            content = "@here New lead received!" if processed.intent_score >= 0.8 else "New lead received"
            
            message = {
                "content": content,
                "embeds": [embed]
            }
            
            response = requests.post(self.discord_webhook, json=message, timeout=10)
            response.raise_for_status()
            logger.info("Discord notification sent successfully")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Discord notification: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending Discord notification: {e}")
            return False
    
    def _send_gmail(self, lead: Lead, processed: ProcessedLead, meet_link: Optional[str]) -> bool:
        """Send email via Gmail - 100% FREE"""
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.gmail_user
            msg['To'] = lead.email
            msg['Subject'] = f"✅ Appointment Confirmed - {processed.model}"
            
            # HTML email template
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; background: #f4f4f4; }}
                    .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ background: white; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                    .button {{ display: inline-block; padding: 12px 30px; background: #667eea; color: white !important; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
                    .info-box {{ background: #f9f9f9; padding: 20px; border-left: 4px solid #667eea; margin: 20px 0; border-radius: 4px; }}
                    .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🚗 Appointment Confirmed!</h1>
                    </div>
                    <div class="content">
                        <p>Dear {processed.name},</p>
                        <p>Thank you for your interest! Your consultation appointment has been successfully scheduled.</p>
                        
                        <div class="info-box">
                            <h3>📋 Appointment Details:</h3>
                            <p><strong>🚙 Car Model:</strong> {processed.model}</p>
                            <p><strong>📅 Date & Time:</strong> {processed.datetime}</p>
                            <p><strong>📱 Phone:</strong> {processed.phone}</p>
                            <p><strong>🆔 Reference ID:</strong> {lead.lead_id}</p>
                        </div>
                        
                        {f'<div style="text-align: center;"><a href="{meet_link}" class="button">Join Google Meet</a></div>' if meet_link else ''}
                        
                        <p><strong>What to expect:</strong></p>
                        <ul>
                            <li>Test drive availability</li>
                            <li>Financing options discussion</li>
                            <li>Trade-in evaluation (if applicable)</li>
                            <li>Special offers and promotions</li>
                        </ul>
                        
                        <p>We look forward to helping you find your perfect vehicle!</p>
                        <p><em>If you need to reschedule, please contact us at least 24 hours in advance.</em></p>
                        
                        <p>Best regards,<br><strong>Your Dealership Team</strong></p>
                    </div>
                    <div class="footer">
                        <p>This is an automated confirmation. Please do not reply to this email.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Plain text fallback
            text = f"""
Dear {processed.name},

Your appointment has been confirmed!

Appointment Details:
- Car Model: {processed.model}
- Date & Time: {processed.datetime}
- Phone: {processed.phone}
- Reference ID: {lead.lead_id}

{f'Join Meeting: {meet_link}' if meet_link else ''}

We look forward to seeing you!

If you need to reschedule, please contact us at least 24 hours in advance.

Best regards,
Your Dealership Team
            """
            
            msg.attach(MIMEText(text, 'plain'))
            msg.attach(MIMEText(html, 'html'))
            
            # Send via Gmail SMTP
            with smtplib.SMTP('smtp.gmail.com', 587, timeout=10) as server:
                server.starttls()
                server.login(self.gmail_user, self.gmail_password)
                server.send_message(msg)
            
            logger.info(f"Gmail sent successfully to {lead.email}")
            return True
            
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error sending Gmail: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to send Gmail: {e}")
            return False


class LeadWorkflow:
    """Main workflow orchestrator - 100% FREE services"""
    
    def __init__(self, config: Dict[str, Any]):
        self.validator = LeadValidator()
        
        # Initialize Groq processor
        try:
            self.groq_processor = GroqProcessor(config['groq_api_key'])
        except Exception as e:
            logger.error(f"Failed to initialize Groq: {e}")
            raise
        
        # Initialize Google Sheets logger
        try:
            self.sheets_logger = GoogleSheetsLogger(
                config['google_sheets_credentials'],
                config['spreadsheet_name']
            )
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets: {e}")
            raise
        
        # Initialize Calendar manager
        try:
            self.calendar_manager = CalendarManager(
                config['google_calendar_credentials'],
                config.get('calendar_id', 'primary')
            )
        except Exception as e:
            logger.error(f"Failed to initialize Calendar: {e}")
            raise
        
        self.notification_service = NotificationService()
        self.notification_channels = config.get(
            'notification_channels',
            [NotificationChannel.DISCORD, NotificationChannel.EMAIL]
        )
        self.timezone = config.get('timezone', 'America/New_York')
    
    def process_lead(self, lead_data: Dict[str, str]) -> Dict[str, Any]:
        """
        Process a lead through the complete workflow
        
        Args:
            lead_data: Dictionary with keys: name, email, phone, car_model, appointment_datetime
            
        Returns:
            Dictionary with processing results and status
        """
        result = {
            'success': False,
            'lead_id': None,
            'errors': [],
            'warnings': [],
            'meet_link': None,
            'intent_score': None
        }
        
        try:
            # Step 1: Validate input
            is_valid, errors = self.validator.validate_lead_data(lead_data)
            if not is_valid:
                result['errors'].extend(errors)
                logger.warning(f"Lead validation failed: {errors}")
                return result
            
            # Step 2: Create Lead object
            lead = Lead(**lead_data)
            logger.info(f"Processing lead: {lead.name} (ID: {lead.lead_id})")
            result['lead_id'] = lead.lead_id
            
            # Step 3: Check for duplicates
            if self.sheets_logger.lead_exists(lead.lead_id):
                result['errors'].append("Duplicate lead - already processed")
                logger.warning(f"Duplicate lead detected: {lead.lead_id}")
                return result
            
            # Step 4: Groq Analysis (FREE)
            processed_lead = self.groq_processor.analyze_lead(lead)
            result['intent_score'] = processed_lead.intent_score
            logger.info(f"Intent score calculated: {processed_lead.intent_score}")
            
            # Flag low-confidence scores
            if processed_lead.intent_score == 0.5:
                result['warnings'].append("AI analysis failed - using default score - manual review recommended")
            
            # Step 5: Log to Google Sheets (FREE)
            sheets_success = self.sheets_logger.log_lead(lead, processed_lead)
            if not sheets_success:
                result['errors'].append("Failed to log to Google Sheets")
                # Don't return - continue with other steps
            
            # Step 6: Create Calendar Event (FREE with Meet link)
            meet_link = self.calendar_manager.create_event(lead, processed_lead, self.timezone)
            result['meet_link'] = meet_link
            if not meet_link:
                result['warnings'].append("Failed to create calendar event")
            
            # Step 7: Send Notifications (All FREE)
            for channel in self.notification_channels:
                notification_success = self.notification_service.send_notification(
                    lead, processed_lead, meet_link, channel
                )
                if not notification_success:
                    result['warnings'].append(f"Failed to send {channel.value} notification")
            
            result['success'] = True
            logger.info(f"Lead processing complete: {lead.name} (ID: {lead.lead_id})")
            
        except Exception as e:
            logger.error(f"Workflow error: {e}", exc_info=True)
            result['errors'].append(f"Unexpected error: {str(e)}")
        
        return result


# Flask API for webhook integration
app = Flask(__name__)
CORS(app)

# Rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per hour"],
    storage_uri="memory://"
)

# Configuration - all FREE services
config = {
    'groq_api_key': os.getenv('GROQ_API_KEY'),
    'google_sheets_credentials': None,
    'google_calendar_credentials': None,
    'spreadsheet_name': os.getenv('SPREADSHEET_NAME', 'Lead Tracker'),
    'calendar_id': os.getenv('CALENDAR_ID', 'primary'),
    'timezone': os.getenv('TIMEZONE', 'America/New_York'),
    'notification_channels': [NotificationChannel.DISCORD, NotificationChannel.EMAIL]
}

# Load Google Sheets credentials
def load_credentials(env_var, file_var, default_file):
    """Load credentials from env var or file"""
    # First try base64 encoded environment variable (for deployment)
    base64_var = env_var + '_BASE64'
    encoded = os.getenv(base64_var)
    if encoded:
        logger.info(f"Loading {env_var} from base64 environment variable")
        try:
            import base64
            decoded = base64.b64decode(encoded).decode('utf-8')
            # Validate it's valid JSON
            json.loads(decoded)
            return decoded
        except Exception as e:
            logger.error(f"Failed to decode base64 credentials: {e}")
    
    # Try regular environment variable
    creds = os.getenv(env_var)
    if creds:
        logger.info(f"Loading {env_var} from environment variable")
        return creds
    
    # Then try file path from env
    file_path = os.getenv(file_var, default_file)
    if os.path.exists(file_path):
        logger.info(f"Loading credentials from file: {file_path}")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                # Validate it's valid JSON
                json.loads(content)
                return content
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {file_path}: {e}")
            raise ValueError(f"Invalid JSON in {file_path}: {e}")
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
            raise
    
    logger.warning(f"No credentials found for {env_var}")
    return None

try:
    config['google_sheets_credentials'] = load_credentials(
        'GOOGLE_SHEETS_CREDS',
        'GOOGLE_SHEETS_CREDS_FILE', 
        './credentials/sheets_creds.json'
    )
    
    config['google_calendar_credentials'] = load_credentials(
        'GOOGLE_CALENDAR_CREDS',
        'GOOGLE_CALENDAR_CREDS_FILE',
        './credentials/calendar_creds.json'
    )
except Exception as e:
    logger.critical(f"Failed to load credentials: {e}")
    config['google_sheets_credentials'] = None
    config['google_calendar_credentials'] = None

# Initialize workflow (with error handling)
workflow = None
try:
    workflow = LeadWorkflow(config)
    logger.info("Lead workflow initialized successfully")
except Exception as e:
    logger.critical(f"Failed to initialize workflow: {e}")

@app.route("/", methods=["GET"])
def home():
    return "Lead Automation API is running", 200

@app.route('/webhook/lead', methods=['POST'])
@limiter.limit("10 per minute")
def capture_lead():
    """
    Webhook endpoint for lead capture
    FREE to host on: Render.com, Railway.app, or Fly.io
    """
    if not workflow:
        return jsonify({
            'success': False,
            'error': 'System not initialized - check configuration'
        }), 503
    
    try:
        lead_data = request.json
        
        if not lead_data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        result = workflow.process_lead(lead_data)
        
        status_code = 200 if result['success'] else 400
        return jsonify(result), status_code
        
    except Exception as e:
        logger.error(f"API error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    health_status = {
        'status': 'healthy' if workflow else 'degraded',
        'timestamp': datetime.now().isoformat(),
        'components': {
            'workflow': workflow is not None,
            'groq': workflow.groq_processor is not None if workflow else False,
            'sheets': workflow.sheets_logger is not None if workflow else False,
            'calendar': workflow.calendar_manager is not None if workflow else False,
        }
    }
    
    status_code = 200 if health_status['status'] == 'healthy' else 503
    return jsonify(health_status), status_code


@app.route('/dashboard', methods=['GET'])
def dashboard_data():
    """Get all leads for dashboard"""
    if not workflow:
        return jsonify({'error': 'System not initialized'}), 503
    
    try:
        leads = workflow.sheets_logger.get_all_leads()
        return jsonify({
            'success': True,
            'count': len(leads),
            'leads': leads
        }), 200
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/lead/<lead_id>', methods=['GET'])
def get_lead(lead_id):
    """Get specific lead by ID"""
    if not workflow:
        return jsonify({'error': 'System not initialized'}), 503
    
    try:
        leads = workflow.sheets_logger.get_all_leads()
        lead = next((l for l in leads if l.get('Lead ID') == lead_id), None)
        
        if lead:
            return jsonify({
                'success': True,
                'lead': lead
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Lead not found'
            }), 404
    except Exception as e:
        logger.error(f"Error fetching lead: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/lead/<lead_id>/status', methods=['PUT'])
def update_lead_status(lead_id):
    """Update lead status"""
    if not workflow:
        return jsonify({'error': 'System not initialized'}), 503
    
    try:
        data = request.json
        status = data.get('status', 'UPDATED')
        notes = data.get('notes', '')
        
        success = workflow.sheets_logger.update_lead_status(lead_id, status, notes)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Lead {lead_id} updated successfully'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to update lead'
            }), 400
    except Exception as e:
        logger.error(f"Error updating lead: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.errorhandler(429)
def ratelimit_handler(e):
    """Handle rate limit errors"""
    return jsonify({
        'success': False,
        'error': 'Rate limit exceeded. Please try again later.'
    }), 429


@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors"""
    return jsonify({
        'success': False,
        'error': 'Endpoint not found'
    }), 404


@app.errorhandler(500)
def internal_error(e):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {e}")
    return jsonify({
        'success': False,
        'error': 'Internal server error'
    }), 500


if __name__ == "__main__":
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'
    
    logger.info(f"Starting Lead Automation System on port {port}")
    logger.info(f"Debug mode: {debug}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)


