"""Download OUI vendor database and save to config/oui.json.

Usage:
    python installers/shared/download_oui.py

Source: maclookup.app public CSV (~5 MB, ~30K entries).
Output format: [{"macPrefix": "AA:BB:CC", "vendorName": "TP-Link"}, ...]
"""

import csv
import io
import json
import sys
import urllib.request
from pathlib import Path

OUT_FILE = Path(__file__).parent.parent / "config" / "oui.json"

# Public OUI CSV from IEEE (no API key needed)
IEEE_URL = "https://standards-oui.ieee.org/oui/oui.csv"

# Fallback: maclookup.app bulk export
FALLBACK_URL = "https://maclookup.app/downloads/json-database/get-db?apiKey=free"


def download_ieee() -> list[dict]:
    print(f"Downloading from IEEE: {IEEE_URL}")
    req = urllib.request.Request(IEEE_URL, headers={"User-Agent": "AnomalyNet/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", errors="replace")

    entries = []
    reader = csv.DictReader(io.StringIO(raw))
    for row in reader:
        # IEEE CSV columns: Registry,Assignment,Organization Name,Organization Address
        assignment = row.get("Assignment", "").strip().upper()
        vendor = row.get("Organization Name", "").strip()
        if len(assignment) == 6 and vendor:
            prefix = f"{assignment[0:2]}:{assignment[2:4]}:{assignment[4:6]}"
            entries.append({"macPrefix": prefix, "vendorName": vendor})

    return entries


def main() -> None:
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    try:
        entries = download_ieee()
    except Exception as exc:
        print(f"IEEE download failed: {exc}")
        print(f"Trying fallback: {FALLBACK_URL}")
        try:
            req = urllib.request.Request(FALLBACK_URL, headers={"User-Agent": "AnomalyNet/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                entries = json.loads(resp.read())
        except Exception as exc2:
            print(f"Fallback also failed: {exc2}")
            print("\nPlease download manually and save as config/oui.json")
            print("Format: [{\"macPrefix\": \"AA:BB:CC\", \"vendorName\": \"TP-Link\"}, ...]")
            sys.exit(1)

    OUT_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=None), encoding="utf-8")
    print(f"Saved {len(entries)} entries to {OUT_FILE}")


if __name__ == "__main__":
    main()
