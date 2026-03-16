import requests
import base64
from config import BASE_URL, CLIENT_ID, CLIENT_SECRET

def get_access_token():
    """
    Get a 2-legged OAuth token from Autodesk.
    This does NOT require any user login — just client ID and secret.
    Token is valid for 1 hour.
    """
    print("🔑 [AUTH] Getting access token from Autodesk...")

    url = f"{BASE_URL}/authentication/v2/token"

    # Encode credentials as Base64
    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")

    headers = {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "grant_type": "client_credentials",
        "scope": "data:read data:write bucket:create bucket:read bucket:delete"
    }

    response = requests.post(url, headers=headers, data=data)

    if response.status_code != 200:
        print(f"   ❌ Auth failed: {response.status_code} — {response.text}")
        raise Exception("Authentication failed. Check your CLIENT_ID and CLIENT_SECRET in config.py")

    token = response.json()["access_token"]
    print(f"   ✅ Token received successfully")
    return token