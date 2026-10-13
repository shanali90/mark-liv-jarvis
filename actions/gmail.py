import os
import pickle
import base64
from email.message import EmailMessage
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import google.auth.exceptions

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
CREDENTIALS_FILE = 'config/gmail_credentials.json'
TOKEN_FILE = 'config/gmail_token.pickle'

def _get_gmail_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)
            
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except google.auth.exceptions.RefreshError:
                creds = None
        
        if not creds:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(f"Missing {CREDENTIALS_FILE}. Please download OAuth client credentials from Google Cloud Console and save as {CREDENTIALS_FILE}")
            
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)
            
    return build('gmail', 'v1', credentials=creds)

def _triage_emails(service, max_results=10):
    results = service.users().messages().list(userId='me', labelIds=['INBOX', 'UNREAD'], maxResults=max_results).execute()
    messages = results.get('messages', [])
    
    if not messages:
        return "No unread emails in inbox."
        
    triage_results = []
    for msg in messages:
        msg_id = msg['id']
        txt = service.users().messages().get(userId='me', id=msg_id, format='metadata').execute()
        headers = txt['payload']['headers']
        
        subject = next((header['value'] for header in headers if header['name'] == 'Subject'), 'No Subject')
        sender = next((header['value'] for header in headers if header['name'] == 'From'), 'Unknown Sender')
        date = next((header['value'] for header in headers if header['name'] == 'Date'), '')
        
        triage_results.append(f"ID: {msg_id}\nFrom: {sender}\nSubject: {subject}\nDate: {date}\n---")
        
    return "\n".join(triage_results)

def _read_email(service, msg_id):
    txt = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
    payload = txt.get('payload', {})
    headers = payload.get('headers', [])
    
    subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
    sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown Sender')
    
    parts = payload.get('parts', [])
    body = ""
    if not parts:
        body_data = payload.get('body', {}).get('data', '')
        if body_data:
            import base64
            body = base64.urlsafe_b64decode(body_data).decode('utf-8')
    else:
        for part in parts:
            if part.get('mimeType') == 'text/plain':
                body_data = part.get('body', {}).get('data', '')
                if body_data:
                    import base64
                    body = base64.urlsafe_b64decode(body_data).decode('utf-8')
                break
                
    return f"From: {sender}\nSubject: {subject}\n\nBody:\n{body[:2000]}..." # Limit body length

def _send_reply(service, msg_id, reply_text):
    # Fetch original email to get Thread ID and headers
    original_msg = service.users().messages().get(userId='me', id=msg_id, format='metadata').execute()
    thread_id = original_msg.get('threadId')
    headers = original_msg['payload']['headers']
    
    subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
    sender = next((h['value'] for h in headers if h['name'] == 'From'), '')
    message_id = next((h['value'] for h in headers if h['name'] == 'Message-ID'), '')
    
    if not subject.startswith('Re:'):
        subject = 'Re: ' + subject

    message = EmailMessage()
    message.set_content(reply_text)
    message['To'] = sender
    message['Subject'] = subject
    if message_id:
        message['In-Reply-To'] = message_id
        message['References'] = message_id

    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    create_message = {
        'message': {
            'raw': encoded_message,
            'threadId': thread_id
        }
    }

    send_message = (service.users().drafts().create(userId="me", body=create_message).execute())
    
    return f"Draft created successfully. Draft ID: {send_message['id']}"

def gmail_action(parameters: dict, player=None, session_memory=None) -> str:
    action = parameters.get("action")
    
    try:
        service = _get_gmail_service()
        
        if action == "triage":
            max_results = parameters.get("max_results", 10)
            return _triage_emails(service, max_results)
            
        elif action == "read":
            msg_id = parameters.get("msg_id")
            if not msg_id:
                return "Error: msg_id is required to read an email."
            return _read_email(service, msg_id)
            
        elif action == "draft_reply":
            msg_id = parameters.get("msg_id")
            reply_text = parameters.get("reply_text")
            if not msg_id or not reply_text:
                return "Error: msg_id and reply_text are required to draft a reply."
            return _send_reply(service, msg_id, reply_text)
            
        else:
            return f"Unknown action: {action}"
            
    except Exception as e:
        msg = f"Gmail API Error: {str(e)}"
        print(f"[Gmail] {msg}")
        return msg

_TOOL = {
    "name": "gmail_triage",
    "description": "Manage Gmail inbox: triage unread emails, read specific emails, and draft replies.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "The action to perform: 'triage' (list unread emails), 'read' (read a specific email), 'draft_reply' (draft a reply to an email)."
            },
            "msg_id": {
                "type": "STRING",
                "description": "The ID of the email message (required for 'read' and 'draft_reply')."
            },
            "reply_text": {
                "type": "STRING",
                "description": "The text of the reply to draft (required for 'draft_reply')."
            },
            "max_results": {
                "type": "INTEGER",
                "description": "Maximum number of unread emails to retrieve for 'triage' (default 10)."
            }
        },
        "required": ["action"]
    },
    "handler": gmail_action,
}
