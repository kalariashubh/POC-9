# 🏗️ Revit Rebar Schedule Extractor

Extract rebar schedule data from Autodesk Revit `.rvt` files into clean JSON — **no Revit installation required, no plugins needed**.

Built using **Autodesk Platform Services (APS) API** to process the model entirely on Autodesk's cloud.

---

## 📋 What It Extracts

Any field available under **Structural Rebar** in Revit's Schedule Properties can be extracted. The default fields are:

| Field | Description | Example |
|---|---|---|
| `type` | Rebar bar type name | `H12`, `25 mm vertical` |
| `bar_length` | Scheduled bar length | `2825 mm` |
| `bar_diameter` | Bar diameter | `12 mm` |
| `spacing` | Distribution spacing | `200 mm` |
| `quantity` | Number of bars in group | `19` |

Output is saved as `output/rebar_data.json`.

---

## 🔁 How It Works

```
Your .rvt file
      ↓
Authenticate with Autodesk APS using Client ID + Secret
      ↓
Upload .rvt file to Autodesk cloud bucket (OSS)
      ↓
Trigger Revit engine on Autodesk cloud (Model Derivative API)
      ↓
Wait for translation to SVF2 format (2–10 minutes)
      ↓
Fetch all model object properties via API
      ↓
Filter actual rebar bar instances from all objects
      ↓
Extract target fields using exact Revit parameter names
      ↓
Clean null values + Round bar lengths + Format mm values
      ↓
Deduplicate rows to match Revit schedule grouping
      ↓
Save to output/rebar_data.json ✅
```

---

## 📁 Project Structure

```
rebar_aps_extractor/
│
├── config.py            ← Your APS credentials and .rvt file path
├── main.py              ← Entry point — runs all steps automatically
│
├── modules/
│   ├── auth.py          ← Step 1: Get OAuth 2.0 access token
│   ├── bucket.py        ← Step 2: Create cloud storage bucket
│   ├── upload.py        ← Step 3: Upload .rvt file to Autodesk cloud
│   ├── translate.py     ← Step 4: Start Revit translation job
│   ├── status.py        ← Step 5: Poll until translation completes
│   └── extract.py       ← Step 6: Extract rebar fields and save JSON
│
├── output/
│   └── rebar_data.json  ← Final extracted data (auto-generated)
│
└── requirements.txt
```

---

## ⚙️ Setup

### 1. Get Free APS Credentials

1. Go to [https://aps.autodesk.com](https://aps.autodesk.com)
2. Sign in or create a free Autodesk account
3. Go to **My Apps** → **Create App**
4. Enter any app name and select **Server-to-Server App** as the type
5. Click **Create** and copy your **Client ID** and **Client Secret**

### 2. Install Dependencies

```
pip install -r requirements.txt
```

### 3. Configure

Open `config.py` and fill in your **Client ID**, **Client Secret**, and the full path to your `.rvt` file.

### 4. Run

```
python main.py
```

---

## 🔄 What Happens When You Run — Step by Step

**Step 1 — Authentication**
The script sends your Client ID and Client Secret to Autodesk and receives a temporary access token valid for 1 hour. This is OAuth 2.0 Client Credentials (2-legged) — no browser or user login required.

**Step 2 — Bucket Creation**
A temporary cloud storage bucket is created on Autodesk's Object Storage Service (OSS). If it already exists from a previous run it is reused. Files auto-delete after 24 hours (transient policy).

**Step 3 — File Upload**
Your `.rvt` file is uploaded to the cloud bucket in 3 phases — request a signed upload URL, send the file bytes directly to Autodesk's S3 storage, then confirm the upload is complete.

**Step 4 — Translation**
Autodesk's Model Derivative API is called to translate the `.rvt` file into SVF2 format. This triggers Autodesk's own Revit engine running on their cloud servers — the same engine that runs Revit on your PC — to open and process your file.

**Step 5 — Status Polling**
The script checks the translation status every 15 seconds and waits until Autodesk reports it as complete. This typically takes 2–10 minutes depending on model size and server load.

**Step 6 — Property Extraction**
All model object properties are fetched from the translated model. The script filters only actual rebar bar instances — identified by having `rebar` in their name and a bracket instance ID like `[435914]`. Family type definitions like `H12` and category headers are excluded.

**Step 7 — Field Extraction**
For each rebar bar instance, the 5 target fields are extracted using exact Revit property group and key name lookup. These are Revit's built-in Structural Rebar parameters and are consistent across all Revit models.

**Step 8 — Cleaning and Rounding**
Empty strings, boolean false values and zero spacing values are converted to `null`. Bar lengths are rounded up to the nearest 25mm increment to match Revit's scheduled bar length display. Spacing values are rounded to the nearest whole mm. Trailing zeros are removed from all mm values.

**Step 9 — Deduplication**
Individual bar instances that share the same type, bar length, bar diameter and spacing are grouped into a single row — exactly how Revit groups rows in its Rebar Schedule. The quantity value comes directly from Revit's own Rebar Set parameter.

**Step 10 — Save JSON**
The final deduplicated records are saved to `output/rebar_data.json`.

---

## 📐 Bar Length Rounding Explained

Revit stores bar lengths internally as exact centerline geometry values (e.g. `3940.000 mm`) but displays rounded values in the Rebar Schedule (e.g. `3950 mm`). The difference is Revit's rounding increment — set in Revit under Structure → Rebar Settings.

This project applies the same ceiling rounding (always rounds UP, never down) to match what the schedule shows. The default increment is 25mm. If your project uses a different increment, change `ROUNDING_INCREMENT_MM` in `modules/extract.py`.

---

## ⚠️ Important Notes

- Translation takes **2–10 minutes** — this is Autodesk's Revit engine running on their cloud and the time depends on model size and server load
- Uploaded files are **auto-deleted after 24 hours** on the free APS tier
- The 5 core rebar fields are **Revit built-in parameters** and will work on any `.rvt` file containing Structural Rebar elements regardless of who created the model
- Width and depth of host elements such as columns, beams and footings are **not stored on the rebar bar itself** — they require additional host element matching which varies per model template
- If your Revit project is in a **language other than English**, property group names and key names may differ — run `debug_rebar_only.py` first to check the exact names used

---

## 🧠 Technical Methods Used

| Method | Purpose |
|---|---|
| OAuth 2.0 Client Credentials (2-legged) | Authenticate with Autodesk without user login |
| OSS 3-phase S3 Upload | Upload files efficiently to Autodesk cloud storage |
| Model Derivative API + SVF2 | Run Revit engine on Autodesk cloud to process `.rvt` |
| Long Polling | Wait for cloud translation job to complete |
| Exact Group + Key Lookup | Reliable extraction using Revit's built-in parameter names |
| Name Pattern Matching | Filter actual rebar instances from all model objects |
| Null Normalisation | Convert Revit's various empty value representations to JSON null |
| Ceiling Rounding | Match Revit's scheduled bar length display |
| Standard Rounding | Match Revit's spacing value display |
| Ordered Dictionary Deduplication | Group bars to match Revit schedule rows |
| Python g Format Specifier | Remove trailing zeros from mm values cleanly |

---
