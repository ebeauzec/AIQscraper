"""
Probe GQL capacity via watchlist (same path as harvest).
This bypasses the 403 on direct system() queries.
"""
import json, sys
from pathlib import Path

CONFIG_PATH = Path('aiq_config.json')
cfg = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
refresh_token = cfg.get('refreshToken') or cfg.get('refresh_token', '')
watchlist_ids_str = cfg.get('watchlistIds') or cfg.get('watchlistId') or ''
wl_ids = [w.strip() for w in watchlist_ids_str.split(',') if w.strip()]

from server import _http, REST_BASE

print("Getting access token...", flush=True)
status, raw = _http("POST", f"{REST_BASE}/v1/tokens/accessToken",
    {"Content-Type": "application/json", "Accept": "application/json"},
    {"refresh_token": refresh_token})
token_data = json.loads(raw.decode("utf-8", errors="replace"))
token = token_data.get("access_token")
print(f"Token OK: {token[:12]}...", flush=True)
print(f"Watchlists: {wl_ids}", flush=True)

GQL_URL = "https://api.activeiq.netapp.com/graphql"
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

def gql_raw(query, variables=None):
    body = {"query": query}
    if variables:
        body["variables"] = variables
    st, r = _http("POST", GQL_URL, headers, body)
    text = r.decode("utf-8", errors="replace") if isinstance(r, bytes) else str(r)
    return st, text

# Query the first watchlist for the first few systems including capacity
if not wl_ids:
    print("ERROR: No watchlist IDs in aiq_config.json")
    sys.exit(1)

wl_id = wl_ids[0]
print(f"\nQuerying watchlist {wl_id} for first 2 systems with capacity...\n", flush=True)

q = f'''{{
  watchlist(id: "{wl_id}") {{
    id
    systems(first: 2) {{
      nodes {{
        serialNumber
        systemName: hostName
        ... on ONTAPSystem {{
          capacity {{
            physical {{
              rawMarketingKiB
              usedKiB
              usablePerformanceTierKiB
              utilizationPercentage
              qoqUtilizationPercentage
            }}
            reportedOn
          }}
          monthlyCapacity {{
            month
            physical {{ rawMarketingKiB usedKiB utilizationPercentage }}
          }}
        }}
      }}
    }}
  }}
}}'''

st, text = gql_raw(q)
print(f"HTTP {st}", flush=True)
if st == 200:
    d = json.loads(text)
    if d.get('errors'):
        print(f"GQL errors: {json.dumps(d['errors'], indent=2)}")
    nodes = ((d.get('data') or {}).get('watchlist') or {}).get('systems', {}).get('nodes', [])
    print(f"Nodes returned: {len(nodes)}", flush=True)
    for node in nodes:
        sn = node.get('serialNumber')
        name = node.get('systemName')
        cap = (node.get('capacity') or {}).get('physical') or {}
        monthly = node.get('monthlyCapacity') or []
        print(f"\n  System: {name} ({sn})")
        print(f"    rawMarketingKiB     = {cap.get('rawMarketingKiB')}")
        print(f"    usedKiB             = {cap.get('usedKiB')}")
        print(f"    usableKiB           = {cap.get('usablePerformanceTierKiB')}")
        print(f"    utilizationPct      = {cap.get('utilizationPercentage')}")
        print(f"    monthlyCapacity[0]  = {monthly[0] if monthly else 'EMPTY'}")
        print(f"    reportedOn          = {(node.get('capacity') or {}).get('reportedOn')}")
else:
    print(f"Response: {text[:500]}")
