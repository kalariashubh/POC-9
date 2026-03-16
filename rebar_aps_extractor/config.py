import os

# ─────────────────────────────────────────────────
# FILL IN YOUR DETAILS HERE
# ─────────────────────────────────────────────────

CLIENT_ID     = "84brt2ueE7l53914PlqeFlg9CU93fqid204pXBguUZzo2wVi"
CLIENT_SECRET = "IpaF6PSGItMxgLiqtbe1DiqrXqfPgGFDCjFYoisUNJzQwhlkNCElYGEMzOERBbmw"

# Full path to your .rvt file
RVT_FILE_PATH = r"D:\Buniyad Byte\POC 9\model.rvt"

# Output JSON path
OUTPUT_JSON   = r"D:\Buniyad Byte\POC 9\rebar_aps_extractor\output\rebar_data.json"

# APS base URL
BASE_URL = "https://developer.api.autodesk.com"

# Bucket name — must be lowercase, no spaces, globally unique
# We append part of client ID to make it unique
BUCKET_KEY = "rebarextractor" + CLIENT_ID[:10].lower().replace("-", "").replace("_", "")