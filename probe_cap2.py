"""
Find what capacity-related endpoints actually work.
Reads the token from the running server's config/db properly.
"""
import sqlite3, json, sys
from pathlib import Path

# Try to load token from all possible locations
token = ''

# 1. config.json
for cfg_name in ['config.json', 'settings.json', '.config.json']:
    p = Path(cfg_name)
    if p.exists():
        try:
            cfg = json.loads(p.read_text(encoding='utf-8'))
            token = cfg.get('token') or cfg.get('accessToken') or cfg.get('access_token') or ''
            if token:
                print(f"Token found in {cfg_name}")
                break
        except Exception:
            pass

# 2. DB kv table
if not token:
    for db_name in ['aiq_cache.db', 'cache.db']:
        if Path(db_name).exists():
            try:
                conn = sqlite3.connect(db_name)
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [r[0] for r in cur.fetchall()]
                print(f"DB tables in {db_name}: {tables}")
                for tbl in tables:
                    try:
                        cur.execute(f"SELECT * FROM {tbl} LIMIT 3")
                        rows = cur.fetchall()
                        print(f"  {tbl}: {rows[:2]}")
                    except Exception as e:
                        print(f"  {tbl}: error - {e}")
                conn.close()
            except Exception as e:
                print(f"DB error: {e}")

if not token:
    print("ERROR: No token found. Cannot probe REST endpoints.")
    sys.exit(1)

print(f"Token: {token[:12]}...")

from server import _http, REST_BASE

headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
sn = '211715000458'  # First serial from cache

# Probe a wider set of capacity endpoint patterns
endpoints = [
    f"/v2/capacity/summary/level/system/id/{sn}",
    f"/v1/capacity/details/level/system/id/{sn}",
    f"/v2/capacity/system/{sn}",
    f"/v2/capacity/cluster/{sn}",
    f"/v2/storage/capacity/{sn}",
    f"/v2/system/{sn}/capacity",
    f"/v1/system/{sn}/capacity",
    f"/v2/capacity/summary/level/cluster/id/{sn}",
    # Watchlist-level
    "/v2/capacity/summary/level/watchlist",
    "/v2/capacity/summary/level/customer",
]

print(f"\nProbing {len(endpoints)} endpoint variants for SN={sn}:")
for path in endpoints:
    url = f"{REST_BASE}{path}"
    try:
        status, raw = _http("GET", url, headers)
        body = raw.decode('utf-8', errors='replace')[:300] if raw else ''
        marker = "OK" if status == 200 else f"HTTP {status}"
        print(f"  [{marker}] {path}")
        if status == 200:
            print(f"    Body: {body[:400]}")
    except Exception as e:
        print(f"  [ERR] {path}: {e}")
