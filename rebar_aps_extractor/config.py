import os

CLIENT_ID     = "84brt2ueE7l53914PlqeFlg9CU93fqid204pXBguUZzo2wVi"

CLIENT_SECRET = "IpaF6PSGItMxgLiqtbe1DiqrXqfPgGFDCjFYoisUNJzQwhlkNCElYGEMzOERBbmw"

RVT_FILE_PATH = r"D:\Buniyad Byte\POC 9\model.rvt"

OUTPUT_JSON   = r"D:\Buniyad Byte\POC 9\rebar_aps_extractor\output\rebar_data.json"

BASE_URL = "https://developer.api.autodesk.com"

BUCKET_KEY = "rebarextractor" + CLIENT_ID[:10].lower().replace("-", "").replace("_", "")
