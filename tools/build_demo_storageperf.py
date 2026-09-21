#!/usr/bin/env python3
"""Build data/demo_storageperf.json -- the StoragePerf (Plumb) data ARIA's Demo mode shows.

StoragePerf ships a built-in demo fleet (Config > "Use mock data"): Pure Storage and NetApp
arrays with realistic performance waveforms. This tool captures that fleet's real
`plumb.aria-export/1` snapshot from a running StoragePerf 0.21.0+ in mock mode, keeps only the
NetApp arrays (ARIA is a NetApp Active IQ tool; Pure systems have no place in it), and writes it
for ARIA's demo mode to associate with one mock customer's systems (see
_demoInjectStoragePerfCustomer in app.js).

Usage:
    python tools/build_demo_storageperf.py [http://localhost:8000] [hours]

Let StoragePerf's mock fleet run for a while first: it records real samples as it goes, so a
longer run gives longer series. The snapshot's own coverage_note says how much history it had.
"""
import json
import os
import sys
import urllib.request

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "demo_storageperf.json")


def main():
    base = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
    hours = sys.argv[2] if len(sys.argv) > 2 else "1"
    with urllib.request.urlopen("%s/api/aria/export?hours=%s" % (base, hours), timeout=300) as r:
        exp = json.load(r)
    if not exp.get("mock_data"):
        sys.exit("Refusing: this StoragePerf is not in mock-data mode, so its export describes real systems "
                 "and must not be committed as demo data.")
    kept = [a for a in exp["arrays"] if str(a.get("vendor", "")).startswith("netapp")]
    dropped = [a["id"] for a in exp["arrays"] if a not in kept]
    exp["arrays"] = kept
    keep_ids = {a["id"] for a in kept}
    exp["events"] = [e for e in exp.get("events", []) if e.get("array_id") in keep_ids]
    # It is StoragePerf's demo fleet by construction; ARIA's demo mode presents it as a customer's
    # StoragePerf, and ARIA's importer (correctly) refuses anything flagged mock_data.
    exp["mock_data"] = False
    exp["_demo_note"] = "Captured from StoragePerf's built-in demo fleet (NetApp arrays only); not customer data."
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(exp, f, separators=(",", ":"))
    print("kept %d NetApp array(s): %s" % (len(kept), ", ".join(a["id"] for a in kept)))
    print("dropped %d non-NetApp array(s): %s" % (len(dropped), ", ".join(dropped)))
    print("period_hours=%s  wrote %s (%d KB)" % (exp.get("period_hours"), OUT, os.path.getsize(OUT) // 1024))


if __name__ == "__main__":
    main()
