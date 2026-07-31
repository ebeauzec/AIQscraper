"""Probe the REST capacity endpoint for real serial numbers and dump the raw response."""
import sqlite3, json, sys
sys.path.insert(0, '.')

# Load a token from cache config
from pathlib import Path
CONFIG_PATH = Path('config.json')
cfg = json.loads(CONFIG_PATH.read_text(encoding='utf-8')) if CONFIG_PATH.exists() else {}
token = cfg.get('token', '')

if not token:
    # Try to find token in db
    conn = sqlite3.connect('aiq_cache.db')
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM kv WHERE key='token' LIMIT 1")
        row = cur.fetchone()
        if row:
            token = row[0]
    except Exception:
        pass
    conn.close()

print(f"Token: {'OK (' + token[:10] + '...)' if token else 'MISSING'}")

# Get some serial numbers from cache
conn = sqlite3.connect('aiq_cache.db')
cur = conn.cursor()
cur.execute('SELECT result_json FROM harvest_cache ORDER BY harvested_at DESC LIMIT 1')
d = json.loads(cur.fetchone()[0])
conn.close()

systems = d.get('systems', [])
serials = [s.get('serialNumber') for s in systems[:5] if s.get('serialNumber')]
print(f"Testing serials: {serials}")
print()

from server import _http, REST_BASE

headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

for sn in serials[:3]:
    print(f"=== Serial: {sn} ===")
    for path in [
        f"/v2/capacity/summary/level/system/id/{sn}",
        f"/v1/capacity/details/level/system/id/{sn}",
    ]:
        url = f"{REST_BASE}{path}"
        try:
            status, raw = _http("GET", url, headers)
            body = raw.decode('utf-8', errors='replace') if raw else ''
            print(f"  [{status}] {path}")
            if status == 200:
                parsed = json.loads(body)
                print(f"  Response keys: {list(parsed.keys())}")
                # Print first 600 chars
                print(f"  Body: {body[:600]}")
                break
            else:
                print(f"  Body (truncated): {body[:200]}")
        except Exception as e:
            print(f"  Exception: {e}")
    print()
