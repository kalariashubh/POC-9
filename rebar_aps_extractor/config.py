import os

CLIENT_ID     = "84brt2ueE7l53914PlqeFlg9CU93fqid204pXBguUZzo2wVi"
# CLIENT_ID     = "Mc7RCA93iFvb4DvYjs0JjTQG828UQdcuKSvl7kKnrLcAdh8w"

CLIENT_SECRET = "IpaF6PSGItMxgLiqtbe1DiqrXqfPgGFDCjFYoisUNJzQwhlkNCElYGEMzOERBbmw"
# CLIENT_SECRET = "Dhhfw3DDZTjm4AFc1igvJZDfL4tHoJ92eAb8R9njGRZDT8bhdnmaIFLEGRkhVWPG"

RVT_FILE_PATH = r"D:\Buniyad Byte\POC 9\model.rvt"

BASE_URL      = "https://developer.api.autodesk.com"

BUCKET_KEY    = "rebarextractor" + CLIENT_ID[:10].lower().replace("-", "").replace("_", "")

OUTPUT_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
