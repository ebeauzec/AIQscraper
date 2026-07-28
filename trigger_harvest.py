"""
Standalone harvest trigger — calls _do_full_harvest() directly from server.py
and stores the result in aiq_cache.db.  Run this to force a fresh harvest
without needing the server to be started.

Usage:  python trigger_harvest.py
"""
import sys, json, time
from pathlib import Path

PROJ = Path(r'G:\My Drive\AntiGravity\AIQscraper')
sys.path.insert(0, str(PROJ))

print("=" * 60)
print("AIQ Harvest Trigger")
print("=" * 60)

# Import the server module.  Its top-level code only sets globals; the
# actual HTTP server is only started from __main__, so this is safe.
import server

# Read watchlist IDs from config (same as the server does)
cfg_path = PROJ / 'aiq_config.json'
cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
wl_ids = []
for key in ('watchlistIds', 'watchlistId', 'watchlist_id', 'watchlist_ids'):
    val = cfg.get(key)
    if val:
        if isinstance(val, list):
            wl_ids = [str(v).strip() for v in val if str(v).strip()]
        else:
            wl_ids = [w.strip() for w in str(val).split(',') if w.strip()]
        break

print(f"Config: watchlist IDs = {wl_ids or '(none — full fleet)'}")
print("Starting harvest …\n")

t0 = time.time()
try:
    result = server._do_full_harvest(watchlist_ids=wl_ids if wl_ids else None)
    elapsed = time.time() - t0
    n_sys = result.get('totalSystems', 0)
    n_cl  = result.get('totalClusters', 0)
    n_risk = result.get('totalRisks', 0)
    n_case = result.get('totalCases', 0)
    print(f"\n✓ Harvest complete in {elapsed:.1f}s")
    print(f"  Systems:  {n_sys}")
    print(f"  Clusters: {n_cl}")
    print(f"  Risks:    {n_risk}")
    print(f"  Cases:    {n_case}")

    # Quick capacity sanity check
    systems = result.get('systems', [])
    nonzero_cap = sum(1 for s in systems if (s.get('clusterRawCapacityTB') or 0) > 0)
    has_shelves = sum(1 for s in systems if s.get('shelves'))
    live_drv_fw = sum(1 for s in systems if any(
        not d.get('_fromCatalog') and not d.get('_fromFleet')
        for d in (s.get('driveFirmware') or [])
    ))
    print(f"\n  Capacity data (non-zero rawTB): {nonzero_cap}/{len(systems)}")
    print(f"  Systems with shelves:           {has_shelves}/{len(systems)}")
    print(f"  Systems with live drive FW:     {live_drv_fw}/{len(systems)}")

    if nonzero_cap == 0:
        print("\n⚠  WARNING: All capacities are still zero — check GQL field tier output above.")
    else:
        print("\n✓ Capacity data successfully populated!")

except Exception as exc:
    elapsed = time.time() - t0
    print(f"\n✗ Harvest FAILED after {elapsed:.1f}s: {exc}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
