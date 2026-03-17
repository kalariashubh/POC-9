"""
Revit Rebar Schedule Extractor — APS API
=========================================
What it does:
  1. Authenticates with Autodesk APS
  2. Creates a cloud bucket
  3. Uploads your .rvt file
  4. Triggers Revit translation on Autodesk servers
  5. Waits for completion
  6. Extracts 6 rebar fields from ALL rebar elements
  7. Saves everything to output/rebar_data.json
"""

from modules.auth      import get_access_token
from modules.bucket    import create_bucket
from modules.upload    import upload_rvt_file
from modules.translate import start_translation
from modules.status    import wait_for_translation
from modules.extract   import extract_and_save, OUTPUT_JSON
from config            import RVT_FILE_PATH, OUTPUT_DIR
import os, sys

def main():
    print("=" * 60)
    print("  🏗️   Revit Rebar Extractor — Autodesk APS")
    print("=" * 60)
    print(f"  Input:  {RVT_FILE_PATH}")
    print(f"  Output: {OUTPUT_JSON}")
    print("=" * 60 + "\n")

    if not os.path.exists(RVT_FILE_PATH):
        print(f"❌ ERROR: .rvt file not found at:\n   {RVT_FILE_PATH}")
        print("   Please update RVT_FILE_PATH in config.py")
        sys.exit(1)

    try:
        # Step 1 — Authentication
        token = get_access_token()

        # Step 2 — Create bucket
        create_bucket(token)

        # Step 3 — Upload .rvt file
        object_id = upload_rvt_file(token)

        # Step 4 — Start translation (Revit processes the file on cloud)
        urn = start_translation(token, object_id)

        # Step 5 — Wait for translation to finish
        success, urn = wait_for_translation(token, urn)

        if not success:
            print("\n❌ Translation failed. Cannot extract data.")
            print("   Possible reasons:")
            print("   - .rvt file is corrupted or password protected")
            print("   - Model uses features not supported by cloud translation")
            sys.exit(1)

        # Step 6 — Extract rebar data and save JSON
        records = extract_and_save(token, urn)

        print("\n" + "=" * 60)
        print(f"  ✅ DONE! {len(records)} rebar records extracted")
        print(f"  📄 Output: {OUTPUT_JSON}")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
