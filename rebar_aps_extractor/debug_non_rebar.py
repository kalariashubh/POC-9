import requests, json, time, base64, os
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

def categorize(obj):
    name = obj.get("name", "")
    name_lower = name.lower()
    props = obj.get("properties", {})

    # Check all property groups for category info
    category = ""
    for group, values in props.items():
        if isinstance(values, dict):
            for k, v in values.items():
                if k.lower() in ["category", "host category"]:
                    category = str(v)

    # Classify
    if "rebar" in name_lower and "[" in name and "]" in name:
        return "✅ Rebar Bar Instance"
    elif "rebar" in name_lower and "[" not in name:
        return "🔷 Rebar Family Type Definition"
    elif any(x in name_lower for x in ["column", "beam", "wall", "slab", "foundation", "floor"]):
        return "🏗️  Structural Element"
    elif name == "":
        return "⬜ Unnamed / Root Object"
    else:
        return f"❓ Other — {category}"

def main():
    print("Fetching data...")
    token = get_token()
    urn   = get_urn(token)
    guid  = get_guid(token, urn)
    objs  = get_props(token, urn, guid)

    print(f"\nTotal objects: {len(objs)}")
    print("=" * 65)

    # Group by category
    categories = {}
    for obj in objs:
        cat = categorize(obj)
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(obj.get("name", "(no name)"))

    # Print summary
    print("\n📊 SUMMARY BY CATEGORY:")
    print("=" * 65)
    for cat, names in sorted(categories.items()):
        print(f"\n{cat}  ({len(names)} objects)")
        for n in names:
            print(f"   • {n}")

    # Save to file
    os.makedirs("output", exist_ok=True)
    result = {
        "total_objects": len(objs),
        "breakdown": {
            cat: {"count": len(names), "names": names}
            for cat, names in categories.items()
        }
    }
    with open("output/all_78_objects.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*65}")
    print(f"✅ Full breakdown saved to: output/all_78_objects.json")

if __name__ == "__main__":
    main()