"""
Mirrors the exact harvest GQL query for systems to see raw capacity data.
"""
import json, sys
from pathlib import Path

CONFIG_PATH = Path('aiq_config.json')
cfg = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
refresh_token = cfg.get('refreshToken') or cfg.get('refresh_token', '')

from server import _http, _gql, REST_BASE

print("Getting access token...", flush=True)
status, raw = _http("POST", f"{REST_BASE}/v1/tokens/accessToken",
    {"Content-Type": "application/json", "Accept": "application/json"},
    {"refresh_token": refresh_token})
token_data = json.loads(raw.decode("utf-8", errors="replace"))
token = token_data.get("access_token")
print(f"Token OK: {token[:12]}...", flush=True)

# First discover watchlists
print("\nDiscovering watchlists...", flush=True)
wl_ids = []

# Try REST
for wl_path in ["/v1/watchlists/list", "/v1/watchlist/all", "/v1/watchlists"]:
    try:
        wl_st, wl_raw = _http("GET", f"{REST_BASE}{wl_path}",
            {"Authorization": f"Bearer {token}", "Accept": "application/json"})
        if wl_st == 200:
            wl_data = json.loads(wl_raw.decode("utf-8", errors="replace"))
            wl_list = wl_data if isinstance(wl_data, list) else wl_data.get("results", wl_data.get("watchlists", wl_data.get("data", [])))
            if isinstance(wl_list, list):
                for wl in wl_list:
                    if isinstance(wl, dict):
                        wid = wl.get("watchListId") or wl.get("watchlistId") or wl.get("id", "")
                        if wid:
                            wl_ids.append(wid)
            if wl_ids:
                print(f"Found {len(wl_ids)} watchlists via {wl_path}: {wl_ids[:5]}", flush=True)
                break
            else:
                print(f"  {wl_path} HTTP {wl_st}: {wl_raw.decode()[:100]}")
    except Exception as e:
        print(f"  {wl_path} error: {e}")

# Try GQL watchlists
if not wl_ids:
    _, wl_gql_resp = _gql(token, "{ watchlists { id name } }")
    if isinstance(wl_gql_resp, dict):
        for wl in (wl_gql_resp.get("data") or {}).get("watchlists") or []:
            wid = (wl or {}).get("id", "")
            if wid:
                wl_ids.append(wid)
        print(f"Found {len(wl_ids)} watchlists via GQL: {wl_ids[:5]}", flush=True)

if not wl_ids:
    print("No watchlists found — trying unscoped query")
    scope_wl_id = None
else:
    scope_wl_id = wl_ids[0]

# Now do the exact harvest query for 2 systems, extract capacity
wl_arg = f', watchlistId: "{scope_wl_id}"' if scope_wl_id else ""
query_text = """{
  systems(pageSize: 2""" + wl_arg + """) {
    totalCount cursor
    systems {
      serialNumber
      hostName
      ... on ONTAPSystem {
        capacity {
          physical {
            rawMarketingKiB
            usedKiB
            usablePerformanceTierKiB
            utilizationPercentage
          }
          reportedOn
        }
        monthlyCapacity {
          month
          physical { rawMarketingKiB usedKiB utilizationPercentage }
        }
      }
    }
  }
}"""

print(f"\nRunning harvest-style systems query (scope={scope_wl_id})...", flush=True)
_, resp = _gql(token, query_text)

if not isinstance(resp, dict):
    print(f"Non-dict response: {type(resp)}, value: {str(resp)[:400]}")
    sys.exit(1)

if resp.get("errors"):
    print(f"GQL errors: {json.dumps(resp['errors'], indent=2)}")

sys_data = (resp.get("data") or {}).get("systems") or {}
total = sys_data.get("totalCount", "?")
page_systems = sys_data.get("systems") or []
print(f"Total systems in scope: {total}")
print(f"Systems on this page: {len(page_systems)}")
print()

for s in page_systems:
    sn = s.get("serialNumber")
    name = s.get("hostName")
    cap = (s.get("capacity") or {}).get("physical") or {}
    rep = (s.get("capacity") or {}).get("reportedOn")
    monthly = s.get("monthlyCapacity") or []
    print(f"System: {name} ({sn})")
    print(f"  rawMarketingKiB    = {cap.get('rawMarketingKiB')}")
    print(f"  usedKiB            = {cap.get('usedKiB')}")
    print(f"  usableKiB          = {cap.get('usablePerformanceTierKiB')}")
    print(f"  utilizationPct     = {cap.get('utilizationPercentage')}")
    print(f"  reportedOn         = {rep}")
    print(f"  monthlyCapacity    = {len(monthly)} months")
    if monthly:
        m0 = monthly[0]
        mp = m0.get("physical") or {}
        print(f"    [{m0.get('month')}] raw={mp.get('rawMarketingKiB')} used={mp.get('usedKiB')}")
    print()
