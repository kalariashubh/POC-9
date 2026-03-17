import requests
import json
import os
import time
import math
from collections import defaultdict
from config import BASE_URL, OUTPUT_JSON

EXACT_FIELD_MAP = {
    "type":         ("Identity Data", "Type Name"),
    "bar_length":   ("Dimensions",    "Length of each bar"),
    "bar_diameter": ("Dimensions",    "Bar Diameter"),
    "spacing":      ("Rebar Set",     "Spacing"),
    "quantity":     ("Rebar Set",     "Quantity"),
}

# ─────────────────────────────────────────────────────────────
# EXACT Host Category strings Revit uses (from debug file)
# mapped to our internal host type names
# ─────────────────────────────────────────────────────────────
HOST_CATEGORY_MAP = {
    "Structural Column":     "column",
    "Structural Framing":    "beam",
    "Structural Foundation": "foundation",
}

# ─────────────────────────────────────────────────────────────
# EXACT dimension keys per host element type
# Sourced directly from debug files
#
# Column:           'b' = width,   'h' = depth
# Beam:             'b' = width,   'h' = depth
# Footing:          'Width' = width, 'Foundation Thickness' = depth
# Foundation Slab:  'Width' = width, 'Thickness' = depth
# ─────────────────────────────────────────────────────────────
HOST_DIMENSION_KEYS = {
    "column": {
        "width": "b",
        "depth": "h",
    },
    "beam": {
        "width": "b",
        "depth": "h",
    },
    "footing": {
        "width": "Width",
        "depth": "Foundation Thickness",
    },
    "foundation slab": {
        "width": "Width",
        "depth": "Thickness",
    },
}

# ─────────────────────────────────────────────────────────────
# Which object name keywords identify each host type
# Used when building the host lookup table
# ─────────────────────────────────────────────────────────────
HOST_NAME_TYPE_MAP = {
    "column":           "column",
    "beam":             "beam",
    "footing":          "footing",
    "foundation slab":  "foundation slab",
}

ROUNDING_INCREMENT_MM = 25


def get_model_guid(token, urn):
    print(f"   🔎 Getting model view GUID...")
    url = f"{BASE_URL}/modelderivative/v2/designdata/{urn}/metadata"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    views = response.json()["data"]["metadata"]
    if not views:
        raise Exception("No views found in translated model")
    for view in views:
        if view.get("role") == "3d":
            print(f"   Found 3D view: '{view['name']}' (GUID: {view['guid']})")
            return view["guid"]
    print(f"   Using view: '{views[0]['name']}' (GUID: {views[0]['guid']})")
    return views[0]["guid"]


def fetch_all_properties(token, urn, guid):
    print(f"   📥 Fetching all object properties...")
    url = f"{BASE_URL}/modelderivative/v2/designdata/{urn}/metadata/{guid}/properties"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"forceget": "true"}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 202:
        print(f"   ⏳ Properties not ready yet, waiting...")
        for attempt in range(20):
            time.sleep(10)
            response = requests.get(url, headers=headers, params=params)
            print(f"   ... attempt {attempt + 1} — status {response.status_code}")
            if response.status_code == 200:
                break
    response.raise_for_status()
    all_objects = response.json()["data"]["collection"]
    print(f"   Total objects in model: {len(all_objects)}")
    return all_objects


def detect_host_type_from_name(name):
    """
    Detect host element type from its object name.
    Uses exact substring matching in order of specificity.

    'Concrete-Rectangular-Column [435893]' → 'column'
    'Concrete-Rectangular Beam [437725]'   → 'beam'
    'Footing-Rectangular [435905]'         → 'footing'
    'Foundation Slab [441018]'             → 'foundation slab'
    """
    name_lower = name.lower()

    if "foundation slab" in name_lower:
        return "foundation slab"
    elif "column" in name_lower:
        return "column"
    elif "beam" in name_lower:
        return "beam"
    elif "footing" in name_lower:
        return "footing"
    elif "foundation" in name_lower:
        return "foundation slab"
    return None


def build_host_lookup(all_objects):
    """
    Build a lookup: object_id → { width, depth, host_type, name }

    Only indexes actual instances (have bracket IDs like [435893]).
    Uses exact dimension key names per host type from debug files.
    """
    host_lookup   = {}
    host_keywords = ["column", "beam", "foundation", "slab", "footing"]

    for obj in all_objects:
        name      = obj.get("name", "")
        object_id = obj.get("objectid")

        if not ("[" in name and "]" in name):
            continue

        if not any(kw in name.lower() for kw in host_keywords):
            continue

        host_type = detect_host_type_from_name(name)
        if host_type is None:
            continue

        dims = obj.get("properties", {}).get("Dimensions", {})
        if not isinstance(dims, dict):
            continue

        key_map   = HOST_DIMENSION_KEYS.get(host_type, {})
        width_key = key_map.get("width")
        depth_key = key_map.get("depth")

        width_raw = dims.get(width_key) if width_key else None
        depth_raw = dims.get(depth_key) if depth_key else None

        width_clean = format_mm_value(clean_value(str(width_raw))) if width_raw else None
        depth_clean = format_mm_value(clean_value(str(depth_raw))) if depth_raw else None

        host_lookup[object_id] = {
            "name":      name,
            "host_type": host_type,
            "width":     width_clean,
            "depth":     depth_clean,
        }

    print(f"\n   Host elements indexed: {len(host_lookup)}")
    for oid, data in host_lookup.items():
        print(f"      [{oid}] {data['name']}")
        print(f"             type={data['host_type']}, width={data['width']}, depth={data['depth']}")

    return host_lookup


def build_rebar_to_host_map(all_objects, host_lookup):
    """
    Map each rebar bar object_id → its host element object_id.

    Uses Revit's EXACT 'Host Category' string from Identity Data:
      'Structural Column'     → match to column host elements
      'Structural Framing'    → match to beam host elements
      'Structural Foundation' → match to footing/foundation host elements

    Matching strategy:
      Extract the Revit instance ID from the bracket in the rebar name
      e.g. 'Rebar Bar [435914]' → instance_id = 435914

      Extract Revit instance IDs from host element names
      e.g. 'Concrete-Rectangular-Column [435893]' → instance_id = 435893

      Match rebar to the host element whose Revit instance ID is
      closest to the rebar's Revit instance ID within the same category.
      (Revit assigns sequential IDs to elements created together)
    """

    hosts_by_category = defaultdict(list)

    for oid, data in host_lookup.items():
        host_type = data["host_type"]

        if host_type == "column":
            category = "Structural Column"
        elif host_type == "beam":
            category = "Structural Framing"
        elif host_type in ["footing", "foundation slab", "foundation"]:
            category = "Structural Foundation"
        else:
            continue

        name = data["name"]
        try:
            revit_id = int(name.split("[")[1].split("]")[0])
        except (IndexError, ValueError):
            revit_id = oid

        hosts_by_category[category].append({
            "object_id":   oid,
            "revit_id":    revit_id,
        })

    print(f"\n   Host category groups:")
    for cat, hosts in hosts_by_category.items():
        print(f"      '{cat}': {[h['revit_id'] for h in hosts]}")

    rebar_host_map = {}

    for obj in all_objects:
        name      = obj.get("name", "")
        object_id = obj.get("objectid")

        if not ("rebar" in name.lower() and "[" in name and "]" in name):
            continue

        props         = obj.get("properties", {})
        identity      = props.get("Identity Data", {})
        host_category = identity.get("Host Category", "") if isinstance(identity, dict) else ""

        try:
            rebar_revit_id = int(name.split("[")[1].split("]")[0])
        except (IndexError, ValueError):
            rebar_revit_id = object_id

        candidates = hosts_by_category.get(host_category, [])

        if not candidates:
            rebar_host_map[object_id] = None
            print(f"      ⚠️  No host found for [{object_id}] {name} (category='{host_category}')")
            continue

        best = min(
            candidates,
            key=lambda h: abs(h["revit_id"] - rebar_revit_id)
        )

        rebar_host_map[object_id] = best["object_id"]

    return rebar_host_map


def is_actual_rebar_bar(obj):
    name = obj.get("name", "")
    return "rebar" in name.lower() and "[" in name and "]" in name


def extract_field(props, group_name, key_name):
    group = props.get(group_name)
    if not isinstance(group, dict):
        return None
    return group.get(key_name, None)


def format_mm_value(val):
    """
    Remove trailing zeros from mm values.
    '200.000 mm' → '200 mm'
    '289.882 mm' → '289.882 mm'
    """
    if val is None:
        return None
    s = str(val).strip()
    parts = s.split()
    if len(parts) == 2:
        number_str, unit = parts[0], parts[1]
    elif len(parts) == 1:
        number_str, unit = parts[0], "mm"
    else:
        return s
    try:
        number    = float(number_str)
        formatted = f"{number:g}"
        return f"{formatted} {unit}"
    except (ValueError, TypeError):
        return s


def clean_value(val):
    """
    Convert empty/invalid values to None.
    Spacing 0.000 mm = Single bar, no distribution → None.
    """
    if val is None:
        return None
    s = str(val).strip()
    if s in ["", "No", "no", "None", "none", "-", "N/A"]:
        return None
    if s == "0.000 mm":
        return None
    return s


def round_to_nearest(value_mm, increment=ROUNDING_INCREMENT_MM):
    return math.ceil(value_mm / increment) * increment


def apply_rounding_to_records(records):
    """Round bar_length up to nearest 25mm — matches Revit schedule."""
    for r in records:
        val = r.get("bar_length")
        if val is None:
            continue
        try:
            numeric = float(str(val).replace("mm", "").strip())
            rounded = round_to_nearest(numeric, ROUNDING_INCREMENT_MM)
            r["bar_length"] = f"{rounded} mm"
        except (ValueError, TypeError):
            pass
    return records


def format_all_mm_fields(records):
    """Remove .000 from bar_diameter and spacing."""
    for r in records:
        if r.get("bar_diameter") is not None:
            r["bar_diameter"] = format_mm_value(r["bar_diameter"])
        if r.get("spacing") is not None:
            r["spacing"] = format_mm_value(r["spacing"])
    return records


def extract_rebar_records(all_objects, host_lookup, rebar_host_map):
    """
    Filter actual rebar bar instances, extract 5 rebar fields,
    and attach width + depth from the matched host element.
    """
    rebar_records     = []
    skipped           = 0
    type_rows_skipped = 0

    for obj in all_objects:
        name      = obj.get("name", "")
        object_id = obj.get("objectid")

        if not is_actual_rebar_bar(obj):
            if "[" not in name:
                type_rows_skipped += 1
            else:
                skipped += 1
            continue

        props = obj.get("properties", {})

        record = {}
        for json_key, (group_name, key_name) in EXACT_FIELD_MAP.items():
            raw = extract_field(props, group_name, key_name)
            record[json_key] = clean_value(raw)

        host_id   = rebar_host_map.get(object_id)
        host_data = host_lookup.get(host_id, {}) if host_id else {}

        record["width"] = host_data.get("width")
        record["depth"] = host_data.get("depth")

        rebar_records.append(record)

    print(f"\n   Rebar bar instances found:  {len(rebar_records)}")
    print(f"   Family type rows skipped:   {type_rows_skipped}")
    print(f"   Other elements skipped:     {skipped}")
    return rebar_records


def group_records(records):
    """
    Deduplicate bars sharing same property combination.
    Key = type + bar_length + bar_diameter + spacing + width + depth
    Uses Revit's own Quantity value for each unique group.
    """
    seen         = {}
    ordered_keys = []

    for r in records:
        key = (
            r.get("type")         or "",
            r.get("bar_length")   or "",
            r.get("bar_diameter") or "",
            r.get("spacing")      or "",
            r.get("width")        or "",
            r.get("depth")        or "",
        )
        if key not in seen:
            seen[key] = {
                "type":         r.get("type"),
                "bar_length":   r.get("bar_length"),
                "bar_diameter": r.get("bar_diameter"),
                "spacing":      r.get("spacing"),
                "width":        r.get("width"),
                "depth":        r.get("depth"),
                "quantity":     r.get("quantity"),
            }
            ordered_keys.append(key)

    return [seen[k] for k in ordered_keys]


def print_preview(records, count=3):
    print(f"\n   📋 Preview (first {min(count, len(records))} records):")
    for record in records[:count]:
        print(json.dumps(record, indent=6))


def extract_and_save(token, urn):
    print(f"\n🔍 [EXTRACT] Extracting rebar schedule data...")

    # Step 1 — Get model view GUID
    guid = get_model_guid(token, urn)

    # Step 2 — Fetch all object properties
    all_objects = fetch_all_properties(token, urn, guid)

    # Step 3 — Build host element lookup with exact dimension keys
    print(f"\n   🏗️  Building host element lookup...")
    host_lookup    = build_host_lookup(all_objects)
    rebar_host_map = build_rebar_to_host_map(all_objects, host_lookup)

    # Step 4 — Filter rebar instances, extract fields + host dimensions
    raw_records = extract_rebar_records(all_objects, host_lookup, rebar_host_map)

    if not raw_records:
        print("\n   ⚠️  No rebar elements found!")
        return []

    # Step 5 — Round bar_length to nearest 25mm
    rounded_records = apply_rounding_to_records(raw_records)

    # Step 6 — Remove .000 from bar_diameter and spacing
    formatted_records = format_all_mm_fields(rounded_records)

    # Step 7 — Deduplicate by unique property combination
    final_records = group_records(formatted_records)

    print(f"\n   Raw bar instances:    {len(raw_records)}")
    print(f"   Unique schedule rows: {len(final_records)}")

    # Step 8 — Save JSON
    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(final_records, f, indent=2, ensure_ascii=False)

    print(f"\n   ✅ Saved {len(final_records)} rebar records to:")
    print(f"   {OUTPUT_JSON}")
    print_preview(final_records, count=3)

    return final_records
