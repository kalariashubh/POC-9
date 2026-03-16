import requests
import json
import time
import base64
import os
from collections import defaultdict
from config import BASE_URL, CLIENT_ID, CLIENT_SECRET, BUCKET_KEY, RVT_FILE_PATH


def get_token():
    url = f"{BASE_URL}/authentication/v2/token"
    creds = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    headers = {"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"}
    data = {"grant_type": "client_credentials", "scope": "data:read data:write bucket:create bucket:read"}
    return requests.post(url, headers=headers, data=data).json()["access_token"]

def get_urn(token):
    file_name = os.path.basename(RVT_FILE_PATH)
    url = f"{BASE_URL}/oss/v2/buckets/{BUCKET_KEY}/objects/{file_name}/details"
    res = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    object_id = res.json()["objectId"]
    return base64.b64encode(object_id.encode()).decode().rstrip("=")

def get_guid(token, urn):
    url = f"{BASE_URL}/modelderivative/v2/designdata/{urn}/metadata"
    views = requests.get(url, headers={"Authorization": f"Bearer {token}"}).json()["data"]["metadata"]
    for v in views:
        if v.get("role") == "3d":
            return v["guid"]
    return views[0]["guid"]

def get_props(token, urn, guid):
    url = f"{BASE_URL}/modelderivative/v2/designdata/{urn}/metadata/{guid}/properties"
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(url, headers=headers, params={"forceget": "true"})
    if res.status_code == 202:
        for _ in range(20):
            time.sleep(10)
            res = requests.get(url, headers=headers, params={"forceget": "true"})
            if res.status_code == 200:
                break
    return res.json()["data"]["collection"]

def main():
    print("Fetching data...")
    token = get_token()
    urn   = get_urn(token)
    guid  = get_guid(token, urn)
    objs  = get_props(token, urn, guid)

    lines = []
    output = {
        "rebar_host_categories": [],
        "host_elements": [],
        "object_id_map": []
    }

    lines.append("=" * 65)
    lines.append("SECTION 1 — REBAR BARS: Host Category + Object ID")
    lines.append("=" * 65)

    for obj in objs:
        name      = obj.get("name", "")
        object_id = obj.get("objectid")
        if not ("rebar" in name.lower() and "[" in name and "]" in name):
            continue

        props         = obj.get("properties", {})
        identity      = props.get("Identity Data", {})
        host_category = identity.get("Host Category", "NOT FOUND") if isinstance(identity, dict) else "NO IDENTITY GROUP"
        host_mark     = identity.get("Host Mark", "") if isinstance(identity, dict) else ""

        line = f"[{object_id}] {name}"
        line += f"\n    Host Category = '{host_category}'"
        line += f"\n    Host Mark     = '{host_mark}'"
        lines.append(line)

        output["rebar_host_categories"].append({
            "object_id":     object_id,
            "name":          name,
            "host_category": host_category,
            "host_mark":     host_mark
        })

    lines.append("\n" + "=" * 65)
    lines.append("SECTION 2 — HOST ELEMENTS: Name + Object ID + Dimensions")
    lines.append("=" * 65)

    host_keywords = ["column", "beam", "foundation", "slab", "footing"]
    for obj in objs:
        name      = obj.get("name", "")
        object_id = obj.get("objectid")
        if not (any(kw in name.lower() for kw in host_keywords) and "[" in name and "]" in name):
            continue

        props = obj.get("properties", {})
        dims  = props.get("Dimensions", {})

        line = f"[{object_id}] {name}"
        lines.append(line)

        dim_summary = {}
        if isinstance(dims, dict):
            for k, v in dims.items():
                lines.append(f"    '{k}' = '{v}'")
                dim_summary[k] = v

        output["host_elements"].append({
            "object_id":  object_id,
            "name":       name,
            "dimensions": dim_summary
        })

    lines.append("\n" + "=" * 65)
    lines.append("SECTION 3 — ALL OBJECT IDs (every object in model)")
    lines.append("=" * 65)

    for obj in objs:
        line = f"[{obj.get('objectid')}] {obj.get('name', '')}"
        lines.append(line)
        output["object_id_map"].append({
            "object_id": obj.get("objectid"),
            "name":      obj.get("name", "")
        })

    # Save files
    os.makedirs("output", exist_ok=True)

    with open("output/debug_host_matching.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    with open("output/debug_host_matching.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print("✅ Saved to:")
    print("   output/debug_host_matching.txt")
    print("   output/debug_host_matching.json")

if __name__ == "__main__":
    main()