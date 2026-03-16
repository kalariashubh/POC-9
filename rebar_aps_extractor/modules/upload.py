import requests
import os
from config import BASE_URL, BUCKET_KEY, RVT_FILE_PATH

def upload_rvt_file(token):
    """
    Upload the .rvt file to the APS bucket using signed S3 upload.
    Returns the object_id (URN) needed for translation.
    """
    file_name = os.path.basename(RVT_FILE_PATH)
    file_size = os.path.getsize(RVT_FILE_PATH)

    print(f"📤 [UPLOAD] Uploading: {file_name} ({file_size / (1024*1024):.1f} MB)...")

    if not os.path.exists(RVT_FILE_PATH):
        raise FileNotFoundError(f"RVT file not found at: {RVT_FILE_PATH}")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # ── Phase 1: Request a signed S3 upload URL ──
    sign_url = f"{BASE_URL}/oss/v2/buckets/{BUCKET_KEY}/objects/{file_name}/signeds3upload"
    sign_params = {"minutesExpiration": 60}

    sign_response = requests.get(sign_url, headers=headers, params=sign_params)

    if sign_response.status_code != 200:
        print(f"   ❌ Failed to get upload URL: {sign_response.status_code} — {sign_response.text}")
        raise Exception("Could not get signed upload URL")

    sign_data = sign_response.json()
    upload_url = sign_data["urls"][0]
    upload_key = sign_data["uploadKey"]

    # ── Phase 2: PUT the file bytes to S3 ──
    print(f"   ⬆️  Sending file bytes to cloud storage...")
    with open(RVT_FILE_PATH, "rb") as f:
        put_response = requests.put(upload_url, data=f)

    if put_response.status_code not in [200, 204]:
        print(f"   ❌ Upload failed: {put_response.status_code}")
        raise Exception("File upload to S3 failed")

    print(f"   ✅ File bytes uploaded successfully")

    # ── Phase 3: Complete the upload (tell Autodesk it's done) ──
    complete_url = f"{BASE_URL}/oss/v2/buckets/{BUCKET_KEY}/objects/{file_name}/signeds3upload"
    complete_body = {"uploadKey": upload_key}
    complete_headers = {**headers, "Content-Type": "application/json"}

    complete_response = requests.post(complete_url, headers=complete_headers, json=complete_body)

    if complete_response.status_code not in [200, 201]:
        print(f"   ❌ Completion failed: {complete_response.status_code} — {complete_response.text}")
        raise Exception("Failed to finalize upload")

    object_id = complete_response.json()["objectId"]
    print(f"   ✅ Upload complete. Object ID: {object_id}")
    return object_id
