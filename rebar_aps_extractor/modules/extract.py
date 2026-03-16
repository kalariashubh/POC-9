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


def is_actual_rebar_bar(obj):
    """
    Only accept actual placed rebar instances.
    These always have:
      - 'rebar' in their name (case-insensitive)
      - A bracket instance ID like [435914] in their name
    Family type rows like 'H12' or '25 mm vertical' have no brackets.
    """
    name = obj.get("name", "")
    return "rebar" in name.lower() and "[" in name and "]" in name


def extract_field(props, group_name, key_name):
    """
    Extract a value using exact group name + key name.
    Returns None if group or key not found.
    """
    group = props.get(group_name)
    if not isinstance(group, dict):
        return None
    return group.get(key_name, None)


def format_mm_value(val):
    """
    Format a millimetre value string cleanly.

    Removes trailing zeros after decimal point:
      '200.000 mm'  → '200 mm'
      '150.000 mm'  → '150 mm'
      '289.882 mm'  → '289.882 mm'  (keeps meaningful decimals)
      '12.000 mm'   → '12 mm'
      '4665.500 mm' → '4665.5 mm'

    Steps:
      1. Strip whitespace
      2. Split number and unit
      3. Parse as float
      4. Format — remove trailing zeros but keep meaningful decimals
      5. Re-attach unit
    """
    if val is None:
        return None

    s = str(val).strip()

    parts = s.split()
    if len(parts) == 2:
        number_str = parts[0]
        unit       = parts[1]
    elif len(parts) == 1:
        number_str = parts[0]
        unit       = "mm"
    else:
        return s

    try:
        number = float(number_str)
        formatted = f"{number:g}"
        return f"{formatted} {unit}"
    except (ValueError, TypeError):
        return s


def clean_value(val):
    """
    Convert empty/invalid values to None.
    Spacing of 0.000 mm means no spacing (Single bar layout).
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
    """
    Round a length value UP to the nearest increment.
    Matches Revit's scheduled bar length rounding behaviour.

    Examples (increment=25):
      3940.000 → 3950
      2672.000 → 2675
      4665.500 → 4675
      6098.000 → 6100
    """
    return math.ceil(value_mm / increment) * increment


def apply_rounding_to_records(records):
    """
    Apply Revit-style rounding to bar_length values in all records.
    Converts raw centerline geometry length → scheduled bar length.
    Example: '3940.000 mm' → '3950 mm'
    """
    for r in records:
        val = r.get("bar_length")
        if val is None:
            continue
        try:
            numeric_str = str(val).replace("mm", "").strip()
            numeric     = float(numeric_str)
            rounded     = round_to_nearest(numeric, ROUNDING_INCREMENT_MM)
            r["bar_length"] = f"{rounded} mm"
        except (ValueError, TypeError):
            pass
    return records


def format_all_mm_fields(records):
    """
    Apply clean mm formatting to bar_diameter and spacing fields.
    Removes unnecessary .000 decimals from all measurement strings.

    bar_length is already handled by apply_rounding_to_records.
    spacing is rounded to nearest whole mm to match Revit schedule display.
    quantity is a count so no formatting needed.
    type is a string so no formatting needed.
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

def extract_rebar_records(all_objects):
    """
    Filter actual rebar bar instances and extract
    5 fields using exact group + key lookup.
    """
    rebar_records    = []
    skipped          = 0
    type_rows_skipped = 0

    for obj in all_objects:
        name = obj.get("name", "")

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

        rebar_records.append(record)

    print(f"   Rebar bar instances found:  {len(rebar_records)}")
    print(f"   Family type rows skipped:   {type_rows_skipped}")
    print(f"   Other elements skipped:     {skipped}")
    return rebar_records


def group_records(records):
    """
    Deduplicate bars that share the same property combination.
    Uses Revit's own Quantity value from the Rebar Set group.
    Key = type + bar_length + bar_diameter + spacing
    First occurrence of each unique key is kept with its Quantity.
    """
    seen         = {}
    ordered_keys = []

    for r in records:
        key = (
            r.get("type")         or "",
            r.get("bar_length")   or "",
            r.get("bar_diameter") or "",
            r.get("spacing")      or "",
        )
        if key not in seen:
            seen[key] = {
                "type":         r.get("type"),
                "bar_length":   r.get("bar_length"),
                "bar_diameter": r.get("bar_diameter"),
                "spacing":      r.get("spacing"),
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

    # Step 3 — Filter actual rebar instances, extract exact fields
    raw_records = extract_rebar_records(all_objects)

    if not raw_records:
        print("\n   ⚠️  No rebar elements found!")
        return []

    # Step 4 — Apply Revit-style rounding to bar_length
    #           3940.000 mm → 3950 mm  (nearest 25mm increment)
    rounded_records = apply_rounding_to_records(raw_records)

    # Step 5 — Remove .000 from bar_diameter and spacing
    #           '12.000 mm' → '12 mm'
    #           '289.882 mm' → '289.882 mm' (meaningful decimals kept)
    formatted_records = format_all_mm_fields(rounded_records)

    # Step 6 — Deduplicate by unique property combination
    final_records = group_records(formatted_records)

    print(f"\n   Raw bar instances:    {len(raw_records)}")
    print(f"   Unique schedule rows: {len(final_records)}")

    # Step 7 — Save JSON
    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(final_records, f, indent=2, ensure_ascii=False)

    print(f"\n   ✅ Saved {len(final_records)} rebar records to:")
    print(f"   {OUTPUT_JSON}")
    print_preview(final_records, count=3)

    return final_records
