# save as debug_object_tree.py
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

def print_tree(node, indent=0, lines=[], max_lines=200):
    if len(lines) >= max_lines:
        return
    obj_id   = node.get("objectid", "?")
    obj_name = node.get("name", "")
    line     = "  " * indent + f"[{obj_id}] {obj_name}"
    lines.append(line)
    print(line)
    for child in node.get("objects", []):
        print_tree(child, indent + 1, lines, max_lines)

def main():
    print("Fetching token...")
    token = get_token()
    urn   = get_urn(token)
    guid  = get_guid(token, urn)

    print("Fetching object tree...")
    url = f"{BASE_URL}/modelderivative/v2/designdata/{urn}/metadata/{guid}"
    res = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    res.raise_for_status()

    data    = res.json()
    objects = data.get("data", {}).get("objects", [])

    print("\n" + "="*65)
    print("FULL OBJECT TREE (parent → child hierarchy)")
    print("="*65 + "\n")

    lines = []
    if objects:
        print_tree(objects[0], indent=0, lines=lines)

    # Save full tree
    os.makedirs("output", exist_ok=True)
    with open("output/debug_object_tree.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # Also save raw JSON
    with open("output/debug_object_tree.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Saved to output/debug_object_tree.txt")
    print(f"✅ Saved to output/debug_object_tree.json")

if __name__ == "__main__":
    main()