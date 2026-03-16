import requests
import json
import time
import base64
import os
from config import BASE_URL, CLIENT_ID, CLIENT_SECRET, BUCKET_KEY, RVT_FILE_PATH


def get_token():
    url = f"{BASE_URL}/authentication/v2/token"
    creds = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    headers = {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "grant_type": "client_credentials",
        "scope": "data:read data:write bucket:create bucket:read"
    }
    return requests.post(url, headers=headers, data=data).json()["access_token"]


def get_urn(token):
    file_name = os.path.basename(RVT_FILE_PATH)
    url = f"{BASE_URL}/oss/v2/buckets/{BUCKET_KEY}/objects/{file_name}/details"
    res = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    object_id = res.json()["objectId"]
    return base64.b64encode(object_id.encode()).decode().rstrip("=")


def get_guid(token, urn):
    url = f"{BASE_URL}/modelderivative/v2/designdata/{urn}/metadata"
    views = requests.get(
        url, headers={"Authorization": f"Bearer {token}"}
    ).json()["data"]["metadata"]
    for v in views:
        if v.get("role") == "3d":
            return v["guid"]
    return views[0]["guid"]


def get_props(token, urn, guid):
    url = f"{BASE_URL}/modelderivative/v2/designdata/{urn}/metadata/{guid}/properties"
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(url, headers=headers, params={"forceget": "true"})
    if res.status_code == 202:
        print("Waiting for properties...")
        for _ in range(20):
            time.sleep(10)
            res = requests.get(url, headers=headers, params={"forceget": "true"})
            if res.status_code == 200:
                break
    return res.json()["data"]["collection"]


def main():
    print("=" * 65)
    print("  Revit Model — Full Property Debug")
    print("=" * 65)

    print("\n🔑 Getting token...")
    token = get_token()
    print("✅ Token received")

    print("🔗 Getting URN...")
    urn = get_urn(token)
    print(f"✅ URN: {urn[:40]}...")

    print("🔍 Getting GUID...")
    guid = get_guid(token, urn)
    print(f"✅ GUID: {guid}")

    print("📥 Fetching all properties...")
    objs = get_props(token, urn, guid)
    print(f"✅ Total objects: {len(objs)}")

    os.makedirs("output", exist_ok=True)

    # ── Section 1: Rebar bar instances ──────────────────────────
    rebar_lines = []
    rebar_json  = []

    for obj in objs:
        name = obj.get("name", "")
        if not ("rebar" in name.lower() and "[" in name and "]" in name):
            continue

        rebar_lines.append("=" * 65)
        rebar_lines.append(f"REBAR OBJECT: {name}")

        obj_data = {"name": name, "properties": {}}
        props = obj.get("properties", {})

        for group, values in props.items():
            if not isinstance(values, dict):
                continue
            rebar_lines.append(f"  GROUP: {group}")
            obj_data["properties"][group] = {}
            for key, val in values.items():
                rebar_lines.append(f"      '{key}'  =  '{val}'")
                obj_data["properties"][group][key] = val

        rebar_json.append(obj_data)

    with open("output/debug_rebar_bars.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(rebar_lines))
    with open("output/debug_rebar_bars.json", "w", encoding="utf-8") as f:
        json.dump(rebar_json, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Rebar bars ({len(rebar_json)}) saved to:")
    print(f"   output/debug_rebar_bars.txt")
    print(f"   output/debug_rebar_bars.json")

    # ── Section 2: Structural host elements ─────────────────────
    host_lines = []
    host_json  = []
    host_keywords = ["column", "beam", "foundation", "slab", "footing", "wall"]

    for obj in objs:
        name = obj.get("name", "")
        name_lower = name.lower()
        if not (any(kw in name_lower for kw in host_keywords) and "[" in name and "]" in name):
            continue

        host_lines.append("=" * 65)
        host_lines.append(f"HOST OBJECT: {name}")

        obj_data = {"name": name, "properties": {}}
        props = obj.get("properties", {})

        for group, values in props.items():
            if not isinstance(values, dict):
                continue
            host_lines.append(f"  GROUP: {group}")
            obj_data["properties"][group] = {}
            for key, val in values.items():
                host_lines.append(f"      '{key}'  =  '{val}'")
                obj_data["properties"][group][key] = val

        host_json.append(obj_data)

    with open("output/debug_host_elements.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(host_lines))
    with open("output/debug_host_elements.json", "w", encoding="utf-8") as f:
        json.dump(host_json, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Host elements ({len(host_json)}) saved to:")
    print(f"   output/debug_host_elements.txt")
    print(f"   output/debug_host_elements.json")

    # ── Section 3: Beam dimensions specifically ──────────────────
    beam_lines = []
    print(f"\n📐 BEAM DIMENSION KEYS (printed to terminal):")
    print("-" * 65)

    for obj in objs:
        name = obj.get("name", "")
        if not ("beam" in name.lower() and "[" in name and "]" in name):
            continue

        beam_lines.append(f"\nBEAM: {name}")
        print(f"\nBEAM: {name}")
        props = obj.get("properties", {})
        dims  = props.get("Dimensions", {})

        if isinstance(dims, dict):
            beam_lines.append("  Dimensions group:")
            print("  Dimensions group:")
            for key, val in dims.items():
                line = f"      '{key}'  =  '{val}'"
                beam_lines.append(line)
                print(line)

    with open("output/debug_beam_dimensions.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(beam_lines))

    print(f"\n✅ Beam dimensions saved to: output/debug_beam_dimensions.txt")

    # ── Section 4: Foundation/Slab dimensions specifically ───────
    slab_lines = []
    slab_keywords = ["foundation", "slab", "footing"]

    print(f"\n📐 FOUNDATION/SLAB DIMENSION KEYS (printed to terminal):")
    print("-" * 65)

    for obj in objs:
        name = obj.get("name", "")
        name_lower = name.lower()
        if not (any(kw in name_lower for kw in slab_keywords) and "[" in name and "]" in name):
            continue

        slab_lines.append(f"\nSLAB/FOOTING: {name}")
        print(f"\nSLAB/FOOTING: {name}")
        props = obj.get("properties", {})
        dims  = props.get("Dimensions", {})

        if isinstance(dims, dict):
            slab_lines.append("  Dimensions group:")
            print("  Dimensions group:")
            for key, val in dims.items():
                line = f"      '{key}'  =  '{val}'"
                slab_lines.append(line)
                print(line)

    with open("output/debug_slab_dimensions.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(slab_lines))

    print(f"\n✅ Slab/Footing dimensions saved to: output/debug_slab_dimensions.txt")

    # ── Section 5: All objects summary ───────────────────────────
    summary = []
    for obj in objs:
        summary.append({
            "object_id": obj.get("objectid"),
            "name":      obj.get("name"),
            "groups":    list(obj.get("properties", {}).keys())
        })

    with open("output/debug_all_objects_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n✅ All objects summary saved to: output/debug_all_objects_summary.json")

    # ── Final summary ─────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  All debug files saved in output/ folder:")
    print(f"  • debug_rebar_bars.txt         — rebar instance properties")
    print(f"  • debug_rebar_bars.json        — rebar instance properties")
    print(f"  • debug_host_elements.txt      — column/beam/slab properties")
    print(f"  • debug_host_elements.json     — column/beam/slab properties")
    print(f"  • debug_beam_dimensions.txt    — beam dimension keys only")
    print(f"  • debug_slab_dimensions.txt    — slab/footing dimension keys only")
    print(f"  • debug_all_objects_summary.json — all 78 objects overview")
    print(f"{'='*65}")


if __name__ == "__main__":
    main()