import requests
import json
import os
import time
import math
from collections import defaultdict
from config import BASE_URL, RVT_FILE_PATH, OUTPUT_DIR

# ─────────────────────────────────────────────────────────────
# Auto-generate output filename from input .rvt filename
# model.rvt        → output/model_data.json
# building_v2.rvt  → output/building_v2_data.json
# ─────────────────────────────────────────────────────────────
_rvt_stem   = os.path.splitext(os.path.basename(RVT_FILE_PATH))[0]
OUTPUT_JSON = os.path.join(OUTPUT_DIR, f"{_rvt_stem}_data.json")

# ─────────────────────────────────────────────────────────────
# EXACT field mapping — Revit built-in Structural Rebar params
# ─────────────────────────────────────────────────────────────
EXACT_FIELD_MAP = {
    "type":         ("Identity Data", "Type Name"),
    "bar_diameter": ("Dimensions",    "Bar Diameter"),
    "spacing":      ("Rebar Set",     "Spacing"),
}

# ─────────────────────────────────────────────────────────────
# EXACT Host Category strings Revit uses
# ─────────────────────────────────────────────────────────────
HOST_CATEGORY_MAP = {
    "Structural Column":     "column",
    "Structural Framing":    "beam",
    "Structural Foundation": "foundation",
}

# ─────────────────────────────────────────────────────────────
# EXACT dimension keys per host element type
#
# Column:
#   width  = 'b'             (cross-section width  e.g. 700mm)
#   length = 'h'             (cross-section depth  e.g. 700mm) ← swapped
#   depth  = 'System Length' (column height        e.g. 4000mm) ← swapped
#
# Beam:
#   width  = 'b'             (beam width  e.g. 300mm)
#   depth  = 'h'             (beam depth  e.g. 600mm)
#   length = 'Cut Length'    (beam span   e.g. 4000mm)
#
# Footing:
#   width  = 'Width'
#   depth  = 'Foundation Thickness'
#   length = 'Length'
#
# Foundation Slab:
#   width  = 'Width'
#   depth  = 'Thickness'
#   length = 'Length'
# ─────────────────────────────────────────────────────────────
HOST_DIMENSION_KEYS = {
    "column": {
        "width":  "b",
        "depth":  "System Length",  # column height → depth
        "length": "h",              # cross-section depth → length
    },
    "beam": {
        "width":  "b",
        "depth":  "h",
        "length": "Cut Length",
    },
    "footing": {
        "width":  "Width",
        "depth":  "Foundation Thickness",
        "length": "Length",
    },
    "foundation slab": {
        "width":  "Width",
        "depth":  "Thickness",
        "length": "Length",
    },
}

# ─────────────────────────────────────────────────────────────
# Human-readable display names for host element types
# ─────────────────────────────────────────────────────────────
HOST_TYPE_DISPLAY = {
    "column":          "Column",
    "beam":            "Beam",
    "footing":         "Footing",
    "foundation slab": "Foundation Slab",
    "foundation":      "Foundation",
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
    Checks 'foundation slab' BEFORE 'foundation' to avoid partial match.
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
    Build a lookup: object_id → { width, depth, length, host_type, host_element, name }

    Column swap applied here:
      'depth'  = System Length (column height e.g. 4000mm)
      'length' = h             (cross-section e.g. 700mm)

    Beam uses Cut Length for the span value.
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

        key_map    = HOST_DIMENSION_KEYS.get(host_type, {})
        width_key  = key_map.get("width")
        depth_key  = key_map.get("depth")
        length_key = key_map.get("length")

        width_raw  = dims.get(width_key)  if width_key  else None
        depth_raw  = dims.get(depth_key)  if depth_key  else None
        length_raw = dims.get(length_key) if length_key else None

        width_clean  = format_mm_value(clean_value(str(width_raw)))  if width_raw  else None
        depth_clean  = format_mm_value(clean_value(str(depth_raw)))  if depth_raw  else None
        length_clean = format_mm_value(clean_value(str(length_raw))) if length_raw else None

        host_element = HOST_TYPE_DISPLAY.get(host_type, host_type.title())

        host_lookup[object_id] = {
            "name":         name,
            "host_type":    host_type,
            "host_element": host_element,
            "width":        width_clean,
            "depth":        depth_clean,
            "length":       length_clean,
        }

    print(f"\n   Host elements indexed: {len(host_lookup)}")
    for oid, data in host_lookup.items():
        print(f"      [{oid}] {data['name']}")
        print(f"             type={data['host_type']}, width={data['width']}, depth={data['depth']}, length={data['length']}")

    return host_lookup


def build_rebar_to_host_map(all_objects, host_lookup):
    """
    Map each rebar bar object_id → LIST of all host element object_ids
    in the same category.

    For beams: rebar is mapped to ALL beams in the model so that
    every unique beam length appears in the output — not just the
    closest one. This ensures 3000mm and 4000mm both appear.

    For columns and foundations: standard closest-ID matching is used
    since columns all have the same dimensions in this model.
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
            "object_id": oid,
            "revit_id":  revit_id,
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
            rebar_host_map[object_id] = {
                "type":     "single",
                "host_ids": []
            }
            print(f"      ⚠️  No host found for [{object_id}] {name} (category='{host_category}')")
            continue

        # ── Beam: map to ALL beam hosts so every unique length appears ──
        if host_category == "Structural Framing":
            rebar_host_map[object_id] = {
                "type":     "all",
                "host_ids": [h["object_id"] for h in candidates]
            }

        # ── Column/Foundation: closest ID matching ──
        else:
            best = min(
                candidates,
                key=lambda h: abs(h["revit_id"] - rebar_revit_id)
            )
            rebar_host_map[object_id] = {
                "type":     "single",
                "host_ids": [best["object_id"]]
            }

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
    if val is None:
        return None
    s = str(val).strip()
    if s in ["", "No", "no", "None", "none", "-", "N/A"]:
        return None
    if s == "0.000 mm":
        return None
    return s


def format_all_mm_fields(records):
    """
    bar_diameter → remove trailing zeros  '12.000 mm' → '12 mm'
    spacing      → round to nearest whole mm  '280.571 mm' → '281 mm'
    """
    for r in records:
        if r.get("bar_diameter") is not None:
            r["bar_diameter"] = format_mm_value(r["bar_diameter"])

        if r.get("spacing") is not None:
            raw = r["spacing"]
            try:
                numeric_str = str(raw).replace("mm", "").strip()
                numeric     = float(numeric_str)
                rounded     = round(numeric)
                r["spacing"] = f"{rounded} mm"
            except (ValueError, TypeError):
                r["spacing"] = format_mm_value(raw)

    return records


def extract_rebar_records(all_objects, host_lookup, rebar_host_map):
    """
    Filter actual rebar bar instances, extract 3 rebar fields,
    attach host dimensions.

    Beam logic:
    - Beam rebar with null spacing → skip entirely
    - Beam rebar with spacing → expand into one record per unique
      beam length so that ALL beam lengths appear in output
      (e.g. both 3000mm and 4000mm beams get a record)

    Column/Foundation logic:
    - Standard single host match
    """
    rebar_records     = []
    skipped           = 0
    type_rows_skipped = 0
    beam_null_skipped = 0

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

        # Extract 3 rebar fields
        record_base = {}
        for json_key, (group_name, key_name) in EXACT_FIELD_MAP.items():
            raw = extract_field(props, group_name, key_name)
            record_base[json_key] = clean_value(raw)

        # Get host mapping info
        host_info = rebar_host_map.get(object_id, {"type": "single", "host_ids": []})
        host_ids  = host_info.get("host_ids", [])
        map_type  = host_info.get("type", "single")

        # ── Beam logic ───────────────────────────────────────────
        if map_type == "all":
            # Skip beam bars with no spacing
            if record_base.get("spacing") is None:
                beam_null_skipped += 1
                continue

            # Expand into one record per unique beam length
            seen_lengths = set()
            for host_id in host_ids:
                host_data = host_lookup.get(host_id, {})
                beam_len  = host_data.get("length")

                # Only add each unique beam length once
                if beam_len in seen_lengths:
                    continue
                seen_lengths.add(beam_len)

                record = dict(record_base)
                record["host_element"] = host_data.get("host_element")
                record["width"]        = host_data.get("width")
                record["depth"]        = host_data.get("depth")
                record["length"]       = beam_len
                rebar_records.append(record)

        # ── Column / Foundation logic ─────────────────────────────
        else:
            host_id   = host_ids[0] if host_ids else None
            host_data = host_lookup.get(host_id, {}) if host_id else {}

            record = dict(record_base)
            record["host_element"] = host_data.get("host_element")
            record["width"]        = host_data.get("width")
            record["depth"]        = host_data.get("depth")
            record["length"]       = host_data.get("length")
            rebar_records.append(record)

    print(f"\n   Rebar records generated:        {len(rebar_records)}")
    print(f"   Beam bars (no spacing) skipped: {beam_null_skipped}")
    print(f"   Family type rows skipped:       {type_rows_skipped}")
    print(f"   Other elements skipped:         {skipped}")
    return rebar_records


def group_records(records):
    """
    Deduplicate records sharing same property combination.
    Key = type + bar_diameter + spacing + host_element + width + depth + length
    Preserves original order (first occurrence kept).
    """
    seen         = {}
    ordered_keys = []

    for r in records:
        key = (
            r.get("type")         or "",
            r.get("bar_diameter") or "",
            r.get("spacing")      or "",
            r.get("host_element") or "",
            r.get("width")        or "",
            r.get("depth")        or "",
            r.get("length")       or "",
        )
        if key not in seen:
            seen[key] = {
                "type":         r.get("type"),
                "bar_diameter": r.get("bar_diameter"),
                "spacing":      r.get("spacing"),
                "host_element": r.get("host_element"),
                "width":        r.get("width"),
                "depth":        r.get("depth"),
                "length":       r.get("length"),
            }
            ordered_keys.append(key)

    return [seen[k] for k in ordered_keys]


def print_preview(records, count=3):
    print(f"\n   📋 Preview (first {min(count, len(records))} records):")
    for record in records[:count]:
        print(json.dumps(record, indent=6))


def extract_and_save(token, urn):
    print(f"\n🔍 [EXTRACT] Extracting rebar schedule data...")
    print(f"   Output will be saved as: {os.path.basename(OUTPUT_JSON)}")

    # Step 1 — Get model view GUID
    guid = get_model_guid(token, urn)

    # Step 2 — Fetch all object properties
    all_objects = fetch_all_properties(token, urn, guid)

    # Step 3 — Build host element lookup
    print(f"\n   🏗️  Building host element lookup...")
    host_lookup    = build_host_lookup(all_objects)
    rebar_host_map = build_rebar_to_host_map(all_objects, host_lookup)

    # Step 4 — Extract rebar records
    #           Beams: expanded per unique length, null-spacing skipped
    #           Columns/Foundations: single closest match
    raw_records = extract_rebar_records(all_objects, host_lookup, rebar_host_map)

    if not raw_records:
        print("\n   ⚠️  No rebar elements found!")
        return []

    # Step 5 — Format bar_diameter and spacing
    formatted_records = format_all_mm_fields(raw_records)

    # Step 6 — Deduplicate by unique property combination
    final_records = group_records(formatted_records)

    print(f"\n   Raw records:          {len(raw_records)}")
    print(f"   Unique final records: {len(final_records)}")

    # Step 7 — Save JSON
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(final_records, f, indent=2, ensure_ascii=False)

    print(f"\n   ✅ Saved {len(final_records)} rebar records to:")
    print(f"   {OUTPUT_JSON}")
    print_preview(final_records, count=3)

    return final_records
