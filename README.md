# 🚗 Lead Automation System

Automated car dealership lead management system with AI-powered intent scoring.

## Features

- ✅ AI Intent Scoring (Groq)
- ✅ Google Sheets Logging
- ✅ Google Calendar Integration
- ✅ Discord & Email Notifications
- ✅ 100% Free Services
- ✅ Live API & Web Form

## Live Demo

- **Booking Form:** https://YOUR_USERNAME.github.io/lead-automation-system/
- **API Endpoint:** https://lead-automation-system-px7x.onrender.com/webhook/lead
- **Dashboard:** https://lead-automation-system-px7x.onrender.com/dashboard
- **Health Check:** https://lead-automation-system-px7x.onrender.com/health

## Tech Stack

- **Backend:** Python, Flask
- **AI:** Groq (Llama 3.3)
- **Storage:** Google Sheets
- **Calendar:** Google Calendar API
- **Notifications:** Discord, Gmail
- **Hosting:** Render.com (API) + GitHub Pages (Form)

## Setup

### 1. Clone Repository
```bash
git clone https://github.com/YOUR_USERNAME/lead-automation-system.git
cd lead-automation-system
```

### 2. Install Dependencies
```bash
python -m venv venv
venv\Scripts\activate  # Windows
# or
source venv/bin/activate  # Linux/Mac

pip install -r requirements.txt
```

### 3. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:
```bash
GROQ_API_KEY=your_groq_api_key
GOOGLE_SHEETS_CREDS_FILE=./credentials/sheets_creds.json
GOOGLE_CALENDAR_CREDS_FILE=./credentials/calendar_creds.json
SPREADSHEET_NAME=Lead Tracker
CALENDAR_ID=your-service-account@project.iam.gserviceaccount.com
TIMEZONE=Asia/Kolkata
DISCORD_WEBHOOK_URL=your_discord_webhook
GMAIL_USER=your_email@gmail.com
GMAIL_APP_PASSWORD=your_app_password
PORT=5000
```

### 4. Run Locally
```bash
python main.py
```

Visit: http://localhost:5000/health

## API Endpoints

### POST /webhook/lead
Submit a new lead

**Request Body:**
```json
{
  "name": "John Doe",
  "email": "john@example.com",
  "phone": "+91-98765-43210",
  "car_model": "Tata Nexon EV",
  "appointment_datetime": "2025-12-15T14:00:00"
}
```

**Response:**
```json
{
  "success": true,
  "lead_id": "abc123",
  "intent_score": 0.85,
  "meet_link": "https://meet.google.com/xxx",
  "errors": [],
  "warnings": []
}
```

### GET /dashboard
View all leads

### GET /health
System health check

### GET /lead/{lead_id}
Get specific lead details

### PUT /lead/{lead_id}/status
Update lead status

## Deployment

### Deploy API to Render.com

1. Push to GitHub
2. Connect repository to Render.com
3. Add environment variables
4. Deploy!

### Deploy Form to GitHub Pages

1. Enable GitHub Pages in repository settings
2. Choose `docs` folder as source
3. Your form will be live at: `https://YOUR_USERNAME.github.io/lead-automation-system/`

## File Structure
```
lead-automation-system/
├── main.py                 # Main application
├── requirements.txt        # Python dependencies
├── .env.example           # Environment variables template
├── .gitignore             # Git ignore rules
├── README.md              # This file
├── docs/
│   └── index.html         # Booking form (GitHub Pages)
├── credentials/           # Google credentials (not in git)
│   ├── sheets_creds.json
│   └── calendar_creds.json
└── test_lead.py           # Test script
```

## Contributing

Pull requests are welcome! For major changes, please open an issue first.

## License

MIT

## Author

Created with ❤️ by Rishabh Sharma

## Support

For issues or questions, please open a GitHub issue.
