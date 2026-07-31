"""
Probe GQL capacity using server's own _gql helper properly.
Dumps the raw response to understand what capacity data the API actually returns.
"""
import json, sys
from pathlib import Path

CONFIG_PATH = Path('aiq_config.json')
cfg = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
refresh_token = cfg.get('refreshToken') or cfg.get('refresh_token', '')

from server import _http, REST_BASE

# Exchange refresh token for access token
print("Getting access token...", flush=True)
status, raw = _http("POST", f"{REST_BASE}/v1/tokens/accessToken",
    {"Content-Type": "application/json", "Accept": "application/json"},
    {"refresh_token": refresh_token})

if isinstance(raw, bytes):
    token_data = json.loads(raw.decode("utf-8", errors="replace"))
else:
    print("raw is not bytes:", type(raw), str(raw)[:200])
    sys.exit(1)

token = token_data.get("access_token")
if not token:
    print("ERROR: No access token:", str(token_data)[:200])
    sys.exit(1)
print(f"Token OK: {token[:12]}...", flush=True)

GQL_URL = "https://api.activeiq.netapp.com/graphql"
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# Get serials from cache
import sqlite3
conn = sqlite3.connect('aiq_cache.db')
cur = conn.cursor()
cur.execute('SELECT result_json FROM harvest_cache ORDER BY harvested_at DESC LIMIT 1')
systems = json.loads(cur.fetchone()[0]).get('systems', [])
conn.close()
serials = [s['serialNumber'] for s in systems
           if s.get('serialNumber') and not s['serialNumber'].startswith(('ASUP','ES-'))][:2]
print(f"Testing: {serials}\n", flush=True)

def gql_raw(query, variables=None):
    body = {"query": query}
    if variables:
        body["variables"] = variables
    st, r = _http("POST", GQL_URL, headers, body)
    if isinstance(r, bytes):
        text = r.decode("utf-8", errors="replace")
    else:
        text = str(r)
    return st, text

for sn in serials:
    print(f"=== {sn} ===", flush=True)

    # Simple capacity query
    q = '''query Cap($sn: String!) {
  system(serialNumber: $sn) {
    serialNumber
    systemName
    capacity {
      physical {
        rawMarketingKiB
        usedKiB
        usablePerformanceTierKiB
        utilizationPercentage
        qoqUtilizationPercentage
        yoyUtilizationPercentage
      }
      logical {
        usedKiB
        savedKiB
      }
    }
  }
}'''
    st, text = gql_raw(q, {"sn": sn})
    print(f"HTTP {st}", flush=True)
    if st == 200:
        d = json.loads(text)
        sys_obj = (d.get('data') or {}).get('system') or {}
        cap = sys_obj.get('capacity') or {}
        phys = cap.get('physical') or {}
        print(f"  rawMarketingKiB     = {phys.get('rawMarketingKiB')}")
        print(f"  usedKiB             = {phys.get('usedKiB')}")
        print(f"  usableKiB           = {phys.get('usablePerformanceTierKiB')}")
        print(f"  utilizationPct      = {phys.get('utilizationPercentage')}")
        if d.get('errors'):
            print(f"  errors: {d['errors']}")
    else:
        print(f"  Response (first 400 chars): {text[:400]}")
    print()
