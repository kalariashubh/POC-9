import requests
from config import BASE_URL, BUCKET_KEY

def create_bucket(token):
    """
    Create an OSS (Object Storage Service) bucket on Autodesk cloud.
    'transient' policy = files auto-deleted after 24 hours (free tier friendly).
    If bucket already exists, that's fine — we continue.
    """
    print(f"🪣 [BUCKET] Creating bucket: '{BUCKET_KEY}'...")

    url = f"{BASE_URL}/oss/v2/buckets"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    body = {
        "bucketKey": BUCKET_KEY,
        "policyKey": "transient"
    }

    response = requests.post(url, headers=headers, json=body)

    if response.status_code == 200:
        print(f"   ✅ Bucket created: '{BUCKET_KEY}'")
    elif response.status_code == 409:
        print(f"   ℹ️  Bucket already exists — reusing it")
    else:
        print(f"   ❌ Bucket error: {response.status_code} — {response.text}")
        raise Exception("Failed to create bucket")
