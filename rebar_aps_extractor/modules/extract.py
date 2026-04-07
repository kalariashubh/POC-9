# import requests
# import json
# import os
# import time
# import math
# from collections import defaultdict
# from config import BASE_URL, RVT_FILE_PATH, OUTPUT_DIR

# # ─────────────────────────────────────────────────────────────
# # Auto-generate output filename from input .rvt filename
# # model.rvt        → output/model_data.json
# # building_v2.rvt  → output/building_v2_data.json
# # ─────────────────────────────────────────────────────────────
# _rvt_stem   = os.path.splitext(os.path.basename(RVT_FILE_PATH))[0]
# OUTPUT_JSON = os.path.join(OUTPUT_DIR, f"{_rvt_stem}_data.json")

# # ─────────────────────────────────────────────────────────────
# # EXACT field mapping — Revit built-in Structural Rebar params
# # ─────────────────────────────────────────────────────────────
# EXACT_FIELD_MAP = {
#     "type":         ("Identity Data", "Type Name"),
#     "bar_diameter": ("Dimensions",    "Bar Diameter"),
#     "spacing":      ("Rebar Set",     "Spacing"),
# }

# # ─────────────────────────────────────────────────────────────
# # EXACT Host Category strings Revit uses
# # ─────────────────────────────────────────────────────────────
# HOST_CATEGORY_MAP = {
#     "Structural Column":     "column",
#     "Structural Framing":    "beam",
#     "Structural Foundation": "foundation",
# }

# # ─────────────────────────────────────────────────────────────
# # EXACT dimension keys per host element type
# #
# # Column:
# #   width  = 'b'             (cross-section width  e.g. 700mm)
# #   length = 'h'             (cross-section depth  e.g. 700mm) ← swapped
# #   depth  = 'System Length' (column height        e.g. 4000mm) ← swapped
# #
# # Beam:
# #   width  = 'b'             (beam width  e.g. 300mm)
# #   depth  = 'h'             (beam depth  e.g. 600mm)
# #   length = 'Cut Length'    (beam span   e.g. 4000mm)
# #
# # Footing:
# #   width  = 'Width'
# #   depth  = 'Foundation Thickness'
# #   length = 'Length'
# #
# # Foundation Slab:
# #   width  = 'Width'
# #   depth  = 'Thickness'
# #   length = 'Length'
# # ─────────────────────────────────────────────────────────────
# HOST_DIMENSION_KEYS = {
#     "column": {
#         "width":  "b",
#         "depth":  "System Length",  # column height → depth
#         "length": "h",              # cross-section depth → length
#     },
#     "beam": {
#         "width":  "b",
#         "depth":  "h",
#         "length": "Cut Length",
#     },
#     "footing": {
#         "width":  "Width",
#         "depth":  "Foundation Thickness",
#         "length": "Length",
#     },
#     "foundation slab": {
#         "width":  "Width",
#         "depth":  "Thickness",
#         "length": "Length",
#     },
# }

# # ─────────────────────────────────────────────────────────────
# # Human-readable display names for host element types
# # ─────────────────────────────────────────────────────────────
# HOST_TYPE_DISPLAY = {
#     "column":          "Column",
#     "beam":            "Beam",
#     "footing":         "Footing",
#     "foundation slab": "Foundation Slab",
#     "foundation":      "Foundation",
# }

# ROUNDING_INCREMENT_MM = 25


# def get_model_guid(token, urn):
#     print(f"   🔎 Getting model view GUID...")
#     url = f"{BASE_URL}/modelderivative/v2/designdata/{urn}/metadata"
#     headers = {"Authorization": f"Bearer {token}"}
#     response = requests.get(url, headers=headers)
#     response.raise_for_status()
#     views = response.json()["data"]["metadata"]
#     if not views:
#         raise Exception("No views found in translated model")
#     for view in views:
#         if view.get("role") == "3d":
#             print(f"   Found 3D view: '{view['name']}' (GUID: {view['guid']})")
#             return view["guid"]
#     print(f"   Using view: '{views[0]['name']}' (GUID: {views[0]['guid']})")
#     return views[0]["guid"]


# def fetch_all_properties(token, urn, guid):
#     print(f"   📥 Fetching all object properties...")
#     url = f"{BASE_URL}/modelderivative/v2/designdata/{urn}/metadata/{guid}/properties"
#     headers = {"Authorization": f"Bearer {token}"}
#     params = {"forceget": "true"}
#     response = requests.get(url, headers=headers, params=params)
#     if response.status_code == 202:
#         print(f"   ⏳ Properties not ready yet, waiting...")
#         for attempt in range(20):
#             time.sleep(10)
#             response = requests.get(url, headers=headers, params=params)
#             print(f"   ... attempt {attempt + 1} — status {response.status_code}")
#             if response.status_code == 200:
#                 break
#     response.raise_for_status()
#     all_objects = response.json()["data"]["collection"]
#     print(f"   Total objects in model: {len(all_objects)}")
#     return all_objects


# def detect_host_type_from_name(name):
#     """
#     Detect host element type from its object name.
#     Checks 'foundation slab' BEFORE 'foundation' to avoid partial match.
#     """
#     name_lower = name.lower()
#     if "foundation slab" in name_lower:
#         return "foundation slab"
#     elif "column" in name_lower:
#         return "column"
#     elif "beam" in name_lower:
#         return "beam"
#     elif "footing" in name_lower:
#         return "footing"
#     elif "foundation" in name_lower:
#         return "foundation slab"
#     return None


# def build_host_lookup(all_objects):
#     """
#     Build a lookup: object_id → { width, depth, length, host_type, host_element, name }

#     Column swap applied here:
#       'depth'  = System Length (column height e.g. 4000mm)
#       'length' = h             (cross-section e.g. 700mm)

#     Beam uses Cut Length for the span value.
#     """
#     host_lookup   = {}
#     host_keywords = ["column", "beam", "foundation", "slab", "footing"]

#     for obj in all_objects:
#         name      = obj.get("name", "")
#         object_id = obj.get("objectid")

#         if not ("[" in name and "]" in name):
#             continue
#         if not any(kw in name.lower() for kw in host_keywords):
#             continue

#         host_type = detect_host_type_from_name(name)
#         if host_type is None:
#             continue

#         dims = obj.get("properties", {}).get("Dimensions", {})
#         if not isinstance(dims, dict):
#             continue

#         key_map    = HOST_DIMENSION_KEYS.get(host_type, {})
#         width_key  = key_map.get("width")
#         depth_key  = key_map.get("depth")
#         length_key = key_map.get("length")

#         width_raw  = dims.get(width_key)  if width_key  else None
#         depth_raw  = dims.get(depth_key)  if depth_key  else None
#         length_raw = dims.get(length_key) if length_key else None

#         width_clean  = format_mm_value(clean_value(str(width_raw)))  if width_raw  else None
#         depth_clean  = format_mm_value(clean_value(str(depth_raw)))  if depth_raw  else None
#         length_clean = format_mm_value(clean_value(str(length_raw))) if length_raw else None

#         host_element = HOST_TYPE_DISPLAY.get(host_type, host_type.title())

#         host_lookup[object_id] = {
#             "name":         name,
#             "host_type":    host_type,
#             "host_element": host_element,
#             "width":        width_clean,
#             "depth":        depth_clean,
#             "length":       length_clean,
#         }

#     print(f"\n   Host elements indexed: {len(host_lookup)}")
#     for oid, data in host_lookup.items():
#         print(f"      [{oid}] {data['name']}")
#         print(f"             type={data['host_type']}, width={data['width']}, depth={data['depth']}, length={data['length']}")

#     return host_lookup


# def build_rebar_to_host_map(all_objects, host_lookup):
#     """
#     Map each rebar bar object_id → LIST of all host element object_ids
#     in the same category.

#     For beams: rebar is mapped to ALL beams in the model so that
#     every unique beam length appears in the output — not just the
#     closest one. This ensures 3000mm and 4000mm both appear.

#     For columns and foundations: standard closest-ID matching is used
#     since columns all have the same dimensions in this model.
#     """
#     hosts_by_category = defaultdict(list)

#     for oid, data in host_lookup.items():
#         host_type = data["host_type"]

#         if host_type == "column":
#             category = "Structural Column"
#         elif host_type == "beam":
#             category = "Structural Framing"
#         elif host_type in ["footing", "foundation slab", "foundation"]:
#             category = "Structural Foundation"
#         else:
#             continue

#         name = data["name"]
#         try:
#             revit_id = int(name.split("[")[1].split("]")[0])
#         except (IndexError, ValueError):
#             revit_id = oid

#         hosts_by_category[category].append({
#             "object_id": oid,
#             "revit_id":  revit_id,
#         })

#     print(f"\n   Host category groups:")
#     for cat, hosts in hosts_by_category.items():
#         print(f"      '{cat}': {[h['revit_id'] for h in hosts]}")

#     rebar_host_map = {}

#     for obj in all_objects:
#         name      = obj.get("name", "")
#         object_id = obj.get("objectid")

#         if not ("rebar" in name.lower() and "[" in name and "]" in name):
#             continue

#         props         = obj.get("properties", {})
#         identity      = props.get("Identity Data", {})
#         host_category = identity.get("Host Category", "") if isinstance(identity, dict) else ""

#         try:
#             rebar_revit_id = int(name.split("[")[1].split("]")[0])
#         except (IndexError, ValueError):
#             rebar_revit_id = object_id

#         candidates = hosts_by_category.get(host_category, [])

#         if not candidates:
#             rebar_host_map[object_id] = {
#                 "type":     "single",
#                 "host_ids": []
#             }
#             print(f"      ⚠️  No host found for [{object_id}] {name} (category='{host_category}')")
#             continue

#         # ── Beam: map to ALL beam hosts so every unique length appears ──
#         if host_category == "Structural Framing":
#             rebar_host_map[object_id] = {
#                 "type":     "all",
#                 "host_ids": [h["object_id"] for h in candidates]
#             }

#         # ── Column/Foundation: closest ID matching ──
#         else:
#             best = min(
#                 candidates,
#                 key=lambda h: abs(h["revit_id"] - rebar_revit_id)
#             )
#             rebar_host_map[object_id] = {
#                 "type":     "single",
#                 "host_ids": [best["object_id"]]
#             }

#     return rebar_host_map


# def is_actual_rebar_bar(obj):
#     name = obj.get("name", "")
#     return "rebar" in name.lower() and "[" in name and "]" in name


# def extract_field(props, group_name, key_name):
#     group = props.get(group_name)
#     if not isinstance(group, dict):
#         return None
#     return group.get(key_name, None)


# def format_mm_value(val):
#     """
#     Remove trailing zeros from mm values.
#     '200.000 mm' → '200 mm'
#     '289.882 mm' → '289.882 mm'
#     """
#     if val is None:
#         return None
#     s = str(val).strip()
#     parts = s.split()
#     if len(parts) == 2:
#         number_str, unit = parts[0], parts[1]
#     elif len(parts) == 1:
#         number_str, unit = parts[0], "mm"
#     else:
#         return s
#     try:
#         number    = float(number_str)
#         formatted = f"{number:g}"
#         return f"{formatted} {unit}"
#     except (ValueError, TypeError):
#         return s


# def clean_value(val):
#     if val is None:
#         return None
#     s = str(val).strip()
#     if s in ["", "No", "no", "None", "none", "-", "N/A"]:
#         return None
#     if s == "0.000 mm":
#         return None
#     return s


# def format_all_mm_fields(records):
#     """
#     bar_diameter → remove trailing zeros  '12.000 mm' → '12 mm'
#     spacing      → round to nearest whole mm  '280.571 mm' → '281 mm'
#     """
#     for r in records:
#         if r.get("bar_diameter") is not None:
#             r["bar_diameter"] = format_mm_value(r["bar_diameter"])

#         if r.get("spacing") is not None:
#             raw = r["spacing"]
#             try:
#                 numeric_str = str(raw).replace("mm", "").strip()
#                 numeric     = float(numeric_str)
#                 rounded     = round(numeric)
#                 r["spacing"] = f"{rounded} mm"
#             except (ValueError, TypeError):
#                 r["spacing"] = format_mm_value(raw)

#     return records


# def extract_rebar_records(all_objects, host_lookup, rebar_host_map):
#     """
#     Filter actual rebar bar instances, extract 3 rebar fields,
#     attach host dimensions.

#     Beam logic:
#     - Beam rebar with null spacing → skip entirely
#     - Beam rebar with spacing → expand into one record per unique
#       beam length so that ALL beam lengths appear in output
#       (e.g. both 3000mm and 4000mm beams get a record)

#     Column/Foundation logic:
#     - Standard single host match
#     """
#     rebar_records     = []
#     skipped           = 0
#     type_rows_skipped = 0
#     beam_null_skipped = 0

#     for obj in all_objects:
#         name      = obj.get("name", "")
#         object_id = obj.get("objectid")

#         if not is_actual_rebar_bar(obj):
#             if "[" not in name:
#                 type_rows_skipped += 1
#             else:
#                 skipped += 1
#             continue

#         props = obj.get("properties", {})

#         # Extract 3 rebar fields
#         record_base = {}
#         for json_key, (group_name, key_name) in EXACT_FIELD_MAP.items():
#             raw = extract_field(props, group_name, key_name)
#             record_base[json_key] = clean_value(raw)

#         # Get host mapping info
#         host_info = rebar_host_map.get(object_id, {"type": "single", "host_ids": []})
#         host_ids  = host_info.get("host_ids", [])
#         map_type  = host_info.get("type", "single")

#         # ── Beam logic ───────────────────────────────────────────
#         if map_type == "all":
#             # Skip beam bars with no spacing
#             if record_base.get("spacing") is None:
#                 beam_null_skipped += 1
#                 continue

#             # Expand into one record per unique beam length
#             seen_lengths = set()
#             for host_id in host_ids:
#                 host_data = host_lookup.get(host_id, {})
#                 beam_len  = host_data.get("length")

#                 # Only add each unique beam length once
#                 if beam_len in seen_lengths:
#                     continue
#                 seen_lengths.add(beam_len)

#                 record = dict(record_base)
#                 record["host_element"] = host_data.get("host_element")
#                 record["width"]        = host_data.get("width")
#                 record["depth"]        = host_data.get("depth")
#                 record["length"]       = beam_len
#                 rebar_records.append(record)

#         # ── Column / Foundation logic ─────────────────────────────
#         else:
#             host_id   = host_ids[0] if host_ids else None
#             host_data = host_lookup.get(host_id, {}) if host_id else {}

#             record = dict(record_base)
#             record["host_element"] = host_data.get("host_element")
#             record["width"]        = host_data.get("width")
#             record["depth"]        = host_data.get("depth")
#             record["length"]       = host_data.get("length")
#             rebar_records.append(record)

#     print(f"\n   Rebar records generated:        {len(rebar_records)}")
#     print(f"   Beam bars (no spacing) skipped: {beam_null_skipped}")
#     print(f"   Family type rows skipped:       {type_rows_skipped}")
#     print(f"   Other elements skipped:         {skipped}")
#     return rebar_records


# def group_records(records):
#     """
#     Deduplicate records sharing same property combination.
#     Key = type + bar_diameter + spacing + host_element + width + depth + length
#     Preserves original order (first occurrence kept).
#     """
#     seen         = {}
#     ordered_keys = []

#     for r in records:
#         key = (
#             r.get("type")         or "",
#             r.get("bar_diameter") or "",
#             r.get("spacing")      or "",
#             r.get("host_element") or "",
#             r.get("width")        or "",
#             r.get("depth")        or "",
#             r.get("length")       or "",
#         )
#         if key not in seen:
#             seen[key] = {
#                 "type":         r.get("type"),
#                 "bar_diameter": r.get("bar_diameter"),
#                 "spacing":      r.get("spacing"),
#                 "host_element": r.get("host_element"),
#                 "width":        r.get("width"),
#                 "depth":        r.get("depth"),
#                 "length":       r.get("length"),
#             }
#             ordered_keys.append(key)

#     return [seen[k] for k in ordered_keys]


# def print_preview(records, count=3):
#     print(f"\n   📋 Preview (first {min(count, len(records))} records):")
#     for record in records[:count]:
#         print(json.dumps(record, indent=6))


# def extract_and_save(token, urn):
#     print(f"\n🔍 [EXTRACT] Extracting rebar schedule data...")
#     print(f"   Output will be saved as: {os.path.basename(OUTPUT_JSON)}")

#     # Step 1 — Get model view GUID
#     guid = get_model_guid(token, urn)

#     # Step 2 — Fetch all object properties
#     all_objects = fetch_all_properties(token, urn, guid)

#     # Step 3 — Build host element lookup
#     print(f"\n   🏗️  Building host element lookup...")
#     host_lookup    = build_host_lookup(all_objects)
#     rebar_host_map = build_rebar_to_host_map(all_objects, host_lookup)

#     # Step 4 — Extract rebar records
#     #           Beams: expanded per unique length, null-spacing skipped
#     #           Columns/Foundations: single closest match
#     raw_records = extract_rebar_records(all_objects, host_lookup, rebar_host_map)

#     if not raw_records:
#         print("\n   ⚠️  No rebar elements found!")
#         return []

#     # Step 5 — Format bar_diameter and spacing
#     formatted_records = format_all_mm_fields(raw_records)

#     # Step 6 — Deduplicate by unique property combination
#     final_records = group_records(formatted_records)

#     print(f"\n   Raw records:          {len(raw_records)}")
#     print(f"   Unique final records: {len(final_records)}")

#     # Step 7 — Save JSON
#     os.makedirs(OUTPUT_DIR, exist_ok=True)
#     with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
#         json.dump(final_records, f, indent=2, ensure_ascii=False)

#     print(f"\n   ✅ Saved {len(final_records)} rebar records to:")
#     print(f"   {OUTPUT_JSON}")
#     print_preview(final_records, count=3)

#     return final_records






import requests
import json
import os
import time
import math
import re
from collections import defaultdict
from config import BASE_URL, RVT_FILE_PATH, OUTPUT_DIR

# ─────────────────────────────────────────────────────────────
# Auto-generate output filenames from input .rvt filename
# ─────────────────────────────────────────────────────────────
_rvt_stem   = os.path.splitext(os.path.basename(RVT_FILE_PATH))[0]
OUTPUT_JSON = os.path.join(OUTPUT_DIR, f"{_rvt_stem}_data.json")
REPORT_TXT  = os.path.join(OUTPUT_DIR, f"{_rvt_stem}_host_report.txt")
REPORT_JSON = os.path.join(OUTPUT_DIR, f"{_rvt_stem}_host_report.json")

# ─────────────────────────────────────────────────────────────
# EXACT field mapping — Revit built-in Structural Rebar params
# These never change across any Revit model
# ─────────────────────────────────────────────────────────────
EXACT_FIELD_MAP = {
    "type":         ("Identity Data", "Type Name"),
    "bar_diameter": ("Dimensions",    "Bar Diameter"),
    "spacing":      ("Rebar Set",     "Spacing"),
}

# ─────────────────────────────────────────────────────────────
# HOST_DIMENSION_KEYS — default config for standard Revit families
# Auto-corrected at runtime if model uses different key names
# ─────────────────────────────────────────────────────────────
HOST_DIMENSION_KEYS = {
    "column": {
        "width":  "b",
        "depth":  "System Length",
        "length": "h",
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

EXCLUDED_KEYS = [
    "volume", "area", "perimeter",
    "elevation at top", "elevation at bottom",
    "reinforcement volume", "maximum bend radius",
    "slope", "offset"
]

HOST_TYPE_DISPLAY = {
    "column":          "Column",
    "beam":            "Beam",
    "footing":         "Footing",
    "foundation slab": "Foundation Slab",
    "foundation":      "Foundation",
}

ROUNDING_INCREMENT_MM = 25


# ═════════════════════════════════════════════════════════════
# AUTO-DETECTION ENGINE
# ═════════════════════════════════════════════════════════════

def parse_mm_value(val_str):
    if val_str is None:
        return None
    s = str(val_str).strip()
    if "mm" not in s.lower():
        return None
    match = re.match(r"^([\d,]+\.?\d*)\s*mm", s, re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def is_excluded_key(key):
    key_lower = key.lower().strip().replace("[constraints] ", "")
    return any(excl in key_lower for excl in EXCLUDED_KEYS)


def auto_detect_dimension_keys(host_type, dim_keys):
    """
    Auto-detect width, depth, length keys for each host type.

    COLUMN:
      width  = 'b' always
      length = 'h' always
      depth  = 'System Length' if present — otherwise handled at
               runtime via _get_column_depth()

    BEAM:
      width  = 'b'
      depth  = 'h'
      length = 'Cut Length' or 'Length'

    FOOTING:
      width  = 'Width'
      depth  = 'Foundation Thickness'
      length = 'Length'

    FOUNDATION SLAB:
      width  = 'Width'
      depth  = 'Thickness'
      length = 'Length'
    """
    valid_mm = {}
    for key, val in dim_keys.items():
        if is_excluded_key(key):
            continue
        numeric = parse_mm_value(str(val))
        if numeric is not None and numeric > 0:
            valid_mm[key] = numeric

    if not valid_mm:
        return {"width": None, "depth": None, "length": None}

    detected      = {"width": None, "depth": None, "length": None}
    key_lower_map = {k.lower(): k for k in valid_mm}

    # ── Column ────────────────────────────────────────────────
    if host_type == "column":
        # Always: b = width, h = length (Revit standard — never swap)
        if "b" in valid_mm:
            detected["width"] = "b"
        elif "width" in key_lower_map:
            detected["width"] = key_lower_map["width"]

        if "h" in valid_mm:
            detected["length"] = "h"
        elif valid_mm:
            remaining = {k: v for k, v in valid_mm.items()
                         if k != detected.get("width")}
            if remaining:
                detected["length"] = min(remaining, key=remaining.get)

        # depth = System Length if available in Dimensions
        # If not, _get_column_depth() handles it at runtime
        for kw in ["system length", "column height"]:
            for k_lower, k_orig in key_lower_map.items():
                if kw in k_lower and not is_excluded_key(k_orig):
                    detected["depth"] = k_orig
                    break
            if detected["depth"]:
                break

    # ── Beam ──────────────────────────────────────────────────
    elif host_type == "beam":
        for kw in ["cut length", "system length", "length"]:
            for k_lower, k_orig in key_lower_map.items():
                if kw in k_lower and not is_excluded_key(k_orig):
                    detected["length"] = k_orig
                    break
            if detected["length"]:
                break

        if not detected["length"] and valid_mm:
            detected["length"] = max(valid_mm, key=valid_mm.get)

        remaining = {k: v for k, v in valid_mm.items()
                     if k != detected["length"]}

        if "b" in remaining:
            detected["width"] = "b"
        elif "width" in key_lower_map:
            detected["width"] = key_lower_map["width"]
        elif remaining:
            detected["width"] = min(remaining, key=remaining.get)

        remaining2 = {k: v for k, v in remaining.items()
                      if k != detected["width"]}

        if "h" in remaining2:
            detected["depth"] = "h"
        elif remaining2:
            detected["depth"] = min(remaining2, key=remaining2.get)

    # ── Footing ───────────────────────────────────────────────
    elif host_type == "footing":
        for kw in ["foundation thickness", "thickness", "depth"]:
            for k_lower, k_orig in key_lower_map.items():
                if kw in k_lower and not is_excluded_key(k_orig):
                    detected["depth"] = k_orig
                    break
            if detected["depth"]:
                break

        for kw in ["width", "b", "w"]:
            for k_lower, k_orig in key_lower_map.items():
                if k_lower == kw and not is_excluded_key(k_orig):
                    detected["width"] = k_orig
                    break
            if detected["width"]:
                break

        for kw in ["length", "l"]:
            for k_lower, k_orig in key_lower_map.items():
                if k_lower == kw and not is_excluded_key(k_orig):
                    detected["length"] = k_orig
                    break
            if detected["length"]:
                break

    # ── Foundation Slab ───────────────────────────────────────
    elif host_type == "foundation slab":
        for kw in ["thickness", "depth"]:
            for k_lower, k_orig in key_lower_map.items():
                if kw in k_lower and not is_excluded_key(k_orig):
                    detected["depth"] = k_orig
                    break
            if detected["depth"]:
                break

        if not detected["depth"] and valid_mm:
            detected["depth"] = min(valid_mm, key=valid_mm.get)

        for kw in ["width"]:
            for k_lower, k_orig in key_lower_map.items():
                if k_lower == kw:
                    detected["width"] = k_orig
                    break
            if detected["width"]:
                break

        for kw in ["length"]:
            for k_lower, k_orig in key_lower_map.items():
                if k_lower == kw:
                    detected["length"] = k_orig
                    break
            if detected["length"]:
                break

    return detected


def build_level_elevation_map(all_objects):
    """
    Build a map of level name → elevation in mm.

    Revit levels are stored as objects like 'Level 1', 'Level 2' etc.
    Their elevation is stored in the Constraints or Dimensions group.

    This is used as the FINAL fallback for column height when:
    - No System Length in Dimensions group
    - No height in Constraints group
    - Column height = elevation of top level - elevation of base level
    """
    level_map = {}

    for obj in all_objects:
        name = obj.get("name", "")

        # Level objects — named 'Level 1', 'Level 2', 'Ground Floor' etc.
        if not ("level" in name.lower() or "floor" in name.lower() or "storey" in name.lower()):
            continue

        # Levels have no bracket IDs
        if "[" in name:
            continue

        props = obj.get("properties", {})

        # Try Constraints group first
        for group_name in ["Constraints", "Dimensions", "Extents"]:
            group = props.get(group_name, {})
            if not isinstance(group, dict):
                continue
            for key, val in group.items():
                key_lower = key.lower()
                if "elevation" in key_lower or "height" in key_lower:
                    numeric = parse_mm_value(str(val))
                    if numeric is not None:
                        level_map[name] = numeric
                        break
            if name in level_map:
                break

    if level_map:
        print(f"\n   📐 Level elevations found: {level_map}")

    return level_map


def _get_column_depth(obj, dims, constr, level_map):
    """
    Get column height (depth in our output) using 4 methods in order:

    Method 1 — System Length in Dimensions group
    Method 2 — Named height key in Constraints group
    Method 3 — Top Offset - Base Offset in Constraints group
    Method 4 — Level elevation difference (top level - base level)

    Returns formatted mm string or None.
    """
    props = obj.get("properties", {})

    # ── Method 1: System Length in Dimensions ─────────────────
    system_length = dims.get("System Length")
    if system_length:
        val = clean_value(str(system_length))
        if val and val != "0.000 mm":
            return val

    # ── Method 2: Named key in Constraints ────────────────────
    if constr:
        constr_lower = {k.lower(): (k, v) for k, v in constr.items()}
        for kw in ["system length", "column height", "height"]:
            if kw in constr_lower:
                _, v = constr_lower[kw]
                val = clean_value(str(v))
                if val and val != "0.000 mm":
                    return val

    # ── Method 3: Top Offset - Base Offset ────────────────────
    if constr:
        constr_lower = {k.lower(): (k, v) for k, v in constr.items()}
        top_val  = None
        base_val = None

        for kw in ["top offset", "top level offset"]:
            if kw in constr_lower:
                _, v = constr_lower[kw]
                top_val = v
                break

        for kw in ["base offset", "base level offset"]:
            if kw in constr_lower:
                _, v = constr_lower[kw]
                base_val = v
                break

        if top_val is not None and base_val is not None:
            try:
                top_mm  = float(str(top_val).replace("mm", "").strip())
                base_mm = float(str(base_val).replace("mm", "").strip())
                height  = top_mm - base_mm
                if height > 0:
                    return f"{height:.3f} mm"
            except (ValueError, TypeError):
                pass

    # ── Method 4: Level elevation difference ──────────────────
    if constr and level_map:
        constr_lower = {k.lower(): (k, v) for k, v in constr.items()}

        top_level_name  = None
        base_level_name = None

        for kw in ["top level", "top constraint"]:
            if kw in constr_lower:
                _, v = constr_lower[kw]
                top_level_name = str(v).strip()
                break

        for kw in ["base level", "base constraint"]:
            if kw in constr_lower:
                _, v = constr_lower[kw]
                base_level_name = str(v).strip()
                break

        if top_level_name and base_level_name:
            top_elev  = level_map.get(top_level_name)
            base_elev = level_map.get(base_level_name)
            if top_elev is not None and base_elev is not None:
                height = top_elev - base_elev
                if height > 0:
                    print(f"      ℹ️  Column height from levels: {top_level_name}({top_elev}) - {base_level_name}({base_elev}) = {height}mm")
                    return f"{height:.3f} mm"

    # ── Method 5: Compute from Elevation at Top - Bottom ──────
    # Some families store top/bottom elevation of the column itself
    if dims:
        elev_top    = dims.get("Elevation at Top")
        elev_bottom = dims.get("Elevation at Bottom")
        if elev_top is not None and elev_bottom is not None:
            try:
                top_mm    = float(str(elev_top).replace("mm", "").strip())
                bottom_mm = float(str(elev_bottom).replace("mm", "").strip())
                height    = top_mm - bottom_mm
                if height > 0:
                    print(f"      ℹ️  Column height from Elevation at Top/Bottom: {height}mm")
                    return f"{height:.3f} mm"
            except (ValueError, TypeError):
                pass

    return None


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


def build_effective_dimension_keys(all_objects):
    """
    Scan all host elements and auto-detect correct dimension keys.
    For columns: also includes Constraints group in sample.
    Saves full report to output/.
    """
    host_keywords   = ["column", "beam", "foundation", "slab", "footing"]
    samples_by_type = {}

    for obj in all_objects:
        name = obj.get("name", "")
        if not ("[" in name and "]" in name):
            continue
        if not any(kw in name.lower() for kw in host_keywords):
            continue

        host_type = detect_host_type_from_name(name)
        if host_type is None or host_type in samples_by_type:
            continue

        props = obj.get("properties", {})
        dims  = props.get("Dimensions", {})
        if not isinstance(dims, dict):
            continue

        dim_keys = {k: str(v) for k, v in dims.items()
                    if v is not None and str(v).strip() != ""}

        if host_type == "column":
            constr = props.get("Constraints", {})
            if isinstance(constr, dict):
                for k, v in constr.items():
                    if v is not None and str(v).strip() != "":
                        dim_keys[f"[Constraints] {k}"] = str(v)

        samples_by_type[host_type] = {"name": name, "dim_keys": dim_keys}

    effective_keys = {}
    report_data    = {"model_file": os.path.basename(RVT_FILE_PATH), "host_types": {}}
    txt_lines      = []

    txt_lines.append("=" * 65)
    txt_lines.append("HOST DIMENSION AUTO-DETECTION REPORT")
    txt_lines.append(f"Model: {os.path.basename(RVT_FILE_PATH)}")
    txt_lines.append("=" * 65)
    txt_lines.append("")

    for host_type, sample in samples_by_type.items():
        txt_lines.append("─" * 65)
        txt_lines.append(f"HOST TYPE: {host_type.upper()}")
        txt_lines.append(f"Sample:    {sample['name']}")
        txt_lines.append("")

        dim_keys = sample["dim_keys"]
        txt_lines.append("All available dimension keys:")
        for k, v in sorted(dim_keys.items()):
            excluded = " (excluded)" if is_excluded_key(k) else ""
            txt_lines.append(f"   '{k}'  =  '{v}'{excluded}")
        txt_lines.append("")

        detected    = auto_detect_dimension_keys(host_type, dim_keys)
        default     = HOST_DIMENSION_KEYS.get(host_type, {})
        type_report = {"sample": sample["name"], "fields": {}}
        changed_any = False

        txt_lines.append("Detection result:")
        for field in ["width", "depth", "length"]:
            det_key = detected.get(field)
            def_key = default.get(field)
            det_val = dim_keys.get(det_key, "—") if det_key else "—"

            if field == "depth" and host_type == "column" and not det_key:
                status  = "⚠️  NOT IN DIMENSIONS — computed at runtime from Constraints/Levels"
                det_key = def_key
            elif det_key and det_key != def_key:
                status      = "🔄 AUTO-FIXED"
                changed_any = True
            elif det_key:
                status = "✅ MATCHES DEFAULT"
            else:
                status  = "⚠️  NOT DETECTED"
                det_key = def_key

            txt_lines.append(f"   {field:8} → detected='{det_key}'  default='{def_key}'  {status}")
            txt_lines.append(f"            value='{det_val}'")

            type_report["fields"][field] = {
                "detected_key": det_key,
                "default_key":  def_key,
                "status":       status,
                "value":        det_val,
            }

        txt_lines.append("")
        if changed_any:
            txt_lines.append(f"   ⚡ Keys were auto-fixed for this host type")
        else:
            txt_lines.append(f"   ✅ Default config is correct for this host type")
        txt_lines.append("")

        effective_keys[host_type] = {
            field: detected.get(field) or default.get(field)
            for field in ["width", "depth", "length"]
        }

        type_report["effective_config"] = effective_keys[host_type]
        type_report["auto_fixed"]       = changed_any
        report_data["host_types"][host_type] = type_report

    for host_type, default in HOST_DIMENSION_KEYS.items():
        if host_type not in effective_keys:
            effective_keys[host_type] = default

    txt_lines.append("=" * 65)
    txt_lines.append("FINAL EFFECTIVE CONFIG")
    txt_lines.append("=" * 65)
    txt_lines.append("")
    txt_lines.append("HOST_DIMENSION_KEYS = {")
    for host_type, keys in effective_keys.items():
        txt_lines.append(f'    "{host_type}": {{')
        for field, key in keys.items():
            txt_lines.append(f'        "{field}": "{key}",')
        txt_lines.append("    },")
    txt_lines.append("}")
    txt_lines.append("")
    txt_lines.append("NOTE: Column depth computed from Constraints/Level elevations")
    txt_lines.append("at runtime using 5-method fallback chain.")

    report_data["effective_config"] = effective_keys

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(REPORT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(txt_lines))
    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    print(f"\n   📋 Host detection report saved:")
    print(f"      {REPORT_TXT}")
    print(f"      {REPORT_JSON}")

    return effective_keys, report_data


def build_host_lookup(all_objects, effective_keys, level_map):
    """
    Build host element lookup using auto-detected dimension keys.

    Column depth uses 5-method fallback chain:
    1. System Length in Dimensions
    2. Named key in Constraints
    3. Top Offset - Base Offset in Constraints
    4. Top Level elevation - Base Level elevation
    5. Elevation at Top - Elevation at Bottom in Dimensions
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

        props  = obj.get("properties", {})
        dims   = props.get("Dimensions", {})
        constr = props.get("Constraints", {})

        if not isinstance(dims, dict):
            dims = {}
        if not isinstance(constr, dict):
            constr = {}

        key_map    = effective_keys.get(host_type, {})
        width_key  = key_map.get("width")
        depth_key  = key_map.get("depth")
        length_key = key_map.get("length")

        width_raw  = dims.get(width_key)  if width_key  else None
        length_raw = dims.get(length_key) if length_key else None

        # Depth extraction
        depth_raw = None
        if host_type == "column":
            # Use full 5-method fallback chain for column height
            depth_raw = _get_column_depth(obj, dims, constr, level_map)
        elif depth_key:
            depth_raw = dims.get(depth_key)

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
            rebar_host_map[object_id] = {"type": "single", "host_ids": []}
            print(f"      ⚠️  No host found for [{object_id}] {name} (category='{host_category}')")
            continue

        if host_category == "Structural Framing":
            rebar_host_map[object_id] = {
                "type":     "all",
                "host_ids": [h["object_id"] for h in candidates]
            }
        else:
            best = min(candidates, key=lambda h: abs(h["revit_id"] - rebar_revit_id))
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

        props       = obj.get("properties", {})
        record_base = {}
        for json_key, (group_name, key_name) in EXACT_FIELD_MAP.items():
            raw = extract_field(props, group_name, key_name)
            record_base[json_key] = clean_value(raw)

        host_info = rebar_host_map.get(object_id, {"type": "single", "host_ids": []})
        host_ids  = host_info.get("host_ids", [])
        map_type  = host_info.get("type", "single")

        if map_type == "all":
            if record_base.get("spacing") is None:
                beam_null_skipped += 1
                continue
            seen_lengths = set()
            for host_id in host_ids:
                host_data = host_lookup.get(host_id, {})
                beam_len  = host_data.get("length")
                if beam_len in seen_lengths:
                    continue
                seen_lengths.add(beam_len)
                record = dict(record_base)
                record["host_element"] = host_data.get("host_element")
                record["width"]        = host_data.get("width")
                record["depth"]        = host_data.get("depth")
                record["length"]       = beam_len
                rebar_records.append(record)
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

    # Step 3 — Build level elevation map (used for column height fallback)
    print(f"\n   📐 Building level elevation map...")
    level_map = build_level_elevation_map(all_objects)

    # Step 4 — Auto-detect dimension keys for this model
    print(f"\n   🔬 Auto-detecting host dimension keys...")
    effective_keys, report = build_effective_dimension_keys(all_objects)

    # Step 5 — Build host element lookup
    #           Column depth uses 5-method fallback chain
    print(f"\n   🏗️  Building host element lookup...")
    host_lookup    = build_host_lookup(all_objects, effective_keys, level_map)
    rebar_host_map = build_rebar_to_host_map(all_objects, host_lookup)

    # Step 6 — Extract rebar records
    raw_records = extract_rebar_records(all_objects, host_lookup, rebar_host_map)

    if not raw_records:
        print("\n   ⚠️  No rebar elements found!")
        return []

    # Step 7 — Format fields
    formatted_records = format_all_mm_fields(raw_records)

    # Step 8 — Deduplicate
    final_records = group_records(formatted_records)

    print(f"\n   Raw records:          {len(raw_records)}")
    print(f"   Unique final records: {len(final_records)}")

    # Step 9 — Save JSON
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(final_records, f, indent=2, ensure_ascii=False)

    print(f"\n   ✅ Saved {len(final_records)} rebar records to:")
    print(f"   {OUTPUT_JSON}")
    print_preview(final_records, count=3)

    return final_records
