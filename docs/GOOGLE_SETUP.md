# Google Cloud OAuth Setup for JARVIS

To enable JARVIS to read, triage, and reply to your emails, and manage your calendar, you need to set up a Google Cloud Project with OAuth credentials. Since this is a personal desktop assistant, we will use a Desktop App OAuth flow.

## 1. Create the Project
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Click the project dropdown at the top left and select **New Project**.
3. Name it `JARVIS Personal Ops` and click **Create**.

## 2. Enable APIs
1. In the left sidebar, go to **APIs & Services > Library**.
2. Search for and enable the following APIs:
   - **Gmail API**
   - **Google Calendar API**
   - **People API** (for fetching contact names to improve triage)

## 3. Configure the OAuth Consent Screen
1. Go to **APIs & Services > OAuth consent screen**.
2. Select **External** user type and click **Create**.
3. Fill in the required fields:
   - **App name**: `JARVIS`
   - **User support email**: Your email address
   - **Developer contact information**: Your email address
4. Click **Save and Continue**.
5. On the **Scopes** screen, you do *not* need to add scopes manually here, as JARVIS will request them incrementally during login. Click **Save and Continue**.
6. On the **Test users** screen, add the 3-5 Google accounts you intend to connect to JARVIS. Click **Save and Continue**.

## 4. Prevent Refresh Token Expiration (CRITICAL)
If your app remains in the "Testing" publishing status, Google will automatically expire your refresh tokens every 7 days, forcing you to constantly re-authenticate.
1. On the OAuth consent screen dashboard, click **Publish App**.
2. Confirm the push to **In production**. 
3. *Note: You do NOT need to submit the app for verification. Because you are the only user and the app runs locally on your desktop, an unverified production app is perfectly fine and means your refresh tokens will never expire.*

## 5. Create Desktop Credentials
1. Go to **APIs & Services > Credentials**.
2. Click **Create Credentials > OAuth client ID**.
3. Select **Desktop app** as the application type.
4. Name it `JARVIS Desktop Client`.
5. Click **Create**.
6. A dialog will appear with your **Client ID** and **Client Secret**.
7. Click **Download JSON** to save the `client_secret_XYZ.json` file.
8. Rename the downloaded file to `client_secret.json` and place it in the `memory/` folder of the JARVIS repository. Do NOT commit this file to git.

## Next Steps
When you ask JARVIS to authenticate an account, it will read `client_secret.json`, pop open your browser, complete the local loopback OAuth flow, and securely store your long-lived refresh tokens inside the Windows Credential Manager (Keyring). No secrets are saved in plain text.
