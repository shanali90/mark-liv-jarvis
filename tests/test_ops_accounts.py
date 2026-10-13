from ops.accounts import AccountManager

class MockCredentials:
    def __init__(self, valid=True, expired=False, refresh_token="mock_rt"):
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token
        self.token = "mock_token"
        self.token_uri = "mock_uri"
        self.client_id = "mock_id"
        self.client_secret = "mock_secret"
        self.scopes = ["mock_scope"]

    def refresh(self, request):
        if self.refresh_token == "bad_rt":
            from google.auth.exceptions import RefreshError
            raise RefreshError("Revoked")
        self.expired = False
        self.valid = True

def test_account_manager_auth_flow(monkeypatch):
    am = AccountManager()
    
    # Mock keyring
    storage = {}
    monkeypatch.setattr("keyring.get_password", lambda svc, acc: storage.get(acc))
    monkeypatch.setattr("keyring.set_password", lambda svc, acc, pw: storage.update({acc: pw}))
    
    # Mock Credentials loading
    def mock_from_auth(info, scopes):
        if info.get("refresh_token") == "bad_rt":
            return MockCredentials(valid=False, expired=True, refresh_token="bad_rt")
        return MockCredentials()
        
    monkeypatch.setattr("google.oauth2.credentials.Credentials.from_authorized_user_info", mock_from_auth)
    
    # Empty state
    assert not am.get_credentials("personal")
    assert am.list_accounts()["personal"] == False

    # Mock full auth flow
    monkeypatch.setattr("pathlib.Path.exists", lambda self: True)
    class MockFlow:
        def run_local_server(self, **kwargs):
            return MockCredentials()
    monkeypatch.setattr("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file", lambda f, s: MockFlow())
    
    assert am.authenticate("personal") == True
    assert "personal" in storage
    
    # Now it should be loaded
    assert am.get_credentials("personal") is not None
    assert am.list_accounts()["personal"] == True

    # Test expired token refresh
    storage["work"] = '{"refresh_token": "mock_rt"}'
    monkeypatch.setattr("google.oauth2.credentials.Credentials.from_authorized_user_info", lambda i, s: MockCredentials(valid=False, expired=True))
    creds = am.get_credentials("work")
    assert creds is not None
    assert not creds.expired

    # Test revoked token
    storage["spam"] = '{"refresh_token": "bad_rt"}'
    monkeypatch.setattr("google.oauth2.credentials.Credentials.from_authorized_user_info", mock_from_auth)
    assert am.get_credentials("spam") is None
    assert am.list_accounts()["spam"] == False
