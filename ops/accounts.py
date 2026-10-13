import json
import keyring
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError

CLIENT_SECRETS_FILE = Path("memory") / "client_secret.json"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/contacts.readonly"
]

class AccountManager:
    def __init__(self):
        self.accounts = ["personal", "work", "spam"] # default labels

    def get_credentials(self, account_label: str) -> Credentials:
        """Retrieve credentials for an account, refreshing if needed. 
        Returns None if no valid credentials exist."""
        creds = None
        
        token_json = keyring.get_password("JARVIS_Google", account_label)
        if token_json:
            try:
                creds_data = json.loads(token_json)
                creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
            except Exception:
                pass
                
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                self._save_credentials(account_label, creds)
            except RefreshError:
                # Token revoked or expired
                creds = None

        return creds

    def authenticate(self, account_label: str, force: bool = False) -> bool:
        """Starts the OAuth desktop flow. Returns True if successful."""
        if not force:
            existing = self.get_credentials(account_label)
            if existing and existing.valid:
                return True
                
        if not CLIENT_SECRETS_FILE.exists():
            raise FileNotFoundError(f"Missing {CLIENT_SECRETS_FILE}. Please follow docs/GOOGLE_SETUP.md.")

        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS_FILE), SCOPES)
        # Using loopback flow with PKCE automatically provided by google-auth-oauthlib
        creds = flow.run_local_server(port=0, prompt='consent')
        
        self._save_credentials(account_label, creds)
        return True

    def _save_credentials(self, account_label: str, creds: Credentials):
        """Securely saves credentials into Windows Credential Manager."""
        creds_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": creds.scopes
        }
        keyring.set_password("JARVIS_Google", account_label, json.dumps(creds_data))

    def list_accounts(self) -> dict:
        """Returns dict of {account_label: is_authenticated}"""
        status = {}
        for acc in self.accounts:
            creds = self.get_credentials(acc)
            status[acc] = creds.valid if creds else False
        return status
