import requests
import time
from config import BASE_URL

def wait_for_translation(token, urn, max_wait_minutes=15):
    """
    Poll the translation status every 15 seconds.
    Waits until translation is 'success' or 'failed'.
    """
    print(f"\n⏳ [STATUS] Waiting for translation to complete...")
    print(f"   (Checking every 15 seconds, max wait: {max_wait_minutes} min)")

    url = f"{BASE_URL}/modelderivative/v2/designdata/{urn}/manifest"
    headers = {"Authorization": f"Bearer {token}"}

    max_attempts = (max_wait_minutes * 60) // 15
    attempt = 0

    while attempt < max_attempts:
        attempt += 1
        time.sleep(15)

        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            print(f"   ⚠️  Status check failed ({response.status_code}) — retrying...")
            continue

        data = response.json()
        status   = data.get("status", "unknown")
        progress = data.get("progress", "")
        region   = data.get("region", "")

        print(f"   [{attempt:02d}] Status: {status} | Progress: {progress}")

        if status == "success":
            print(f"   ✅ Translation complete!")
            return True, urn

        elif status == "failed":
            print(f"   ❌ Translation FAILED")
            # Print error details if available
            for derivative in data.get("derivatives", []):
                for msg in derivative.get("messages", []):
                    print(f"      Error: {msg.get('message', '')}")
            return False, urn

        elif status in ["inprogress", "pending"]:
            continue

    print(f"   ❌ Timed out after {max_wait_minutes} minutes")
    return False, urn