import requests
import base64
from config import BASE_URL

def start_translation(token, object_id):
    """
    Tell APS to translate the .rvt file into SVF2 format.
    This is what triggers Autodesk's Revit engine on the cloud.
    Returns the URN (base64 encoded object_id) used for all further calls.
    """
    print(f"⚙️  [TRANSLATE] Starting translation job (Revit engine processing)...")

    urn = base64.b64encode(object_id.encode("utf-8")).decode("utf-8").rstrip("=")

    url = f"{BASE_URL}/modelderivative/v2/designdata/job"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "x-ads-force": "true"
    }

    body = {
        "input": {
            "urn": urn
        },
        "output": {
            "formats": [
                {
                    "type": "svf2",
                    "views": ["3d", "2d"]
                }
            ]
        }
    }

    response = requests.post(url, headers=headers, json=body)

    if response.status_code not in [200, 201]:
        print(f"   ❌ Translation start failed: {response.status_code} — {response.text}")
        raise Exception("Failed to start translation job")

    print(f"   ✅ Translation job started. URN: {urn[:30]}...")
    print(f"   ⏳ This takes 2-10 minutes depending on model size")
    return urn
