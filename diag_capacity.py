"""
Diagnostic: Fetch one system from the AIQ API and print its raw capacity fields.
This runs the same GQL request server.py would, to check if capacity data is returned.
"""
import os, sys, json, requests

TOKEN_FILE = os.path.join(os.path.dirname(__file__), "token_cache.json")
if not os.path.exists(TOKEN_FILE):
    print("No token_cache.json found. Please run a harvest first to populate the token.")
    sys.exit(1)

with open(TOKEN_FILE) as f:
    tok_data = json.load(f)

token = tok_data.get("access_token") or tok_data.get("token") or tok_data.get("accessToken", "")
if not token:
    print("Token not found in token_cache.json")
    sys.exit(1)

GQL_URL = "https://activeiq.netapp.com/graphql"
HEADERS = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "Accept": "application/json"
}

# Minimal query: fetch 3 systems with their capacity (same as TAM_SAFE)
QUERY = """
{
  systems(pageSize: 3) {
    cursor
    systems {
      serialNumber
      hostName
      type
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
          physical {
            rawMarketingKiB
            usedKiB
            utilizationPercentage
          }
        }
      }
    }
  }
}
"""

print("Querying AIQ GQL for capacity data on 3 systems...")
resp = requests.post(GQL_URL, headers=HEADERS, json={"query": QUERY}, timeout=30)
print(f"HTTP {resp.status_code}")
if resp.ok:
    data = resp.json()
    if data.get("errors"):
        print("GQL Errors:", json.dumps(data["errors"], indent=2))
    else:
        systems = (data.get("data") or {}).get("systems", {}).get("systems", [])
        print(f"Got {len(systems)} systems")
        for s in systems:
            print(f"\n--- SN={s.get('serialNumber')} name={s.get('hostName')} type={s.get('type')}")
            cap = s.get("capacity")
            monthly = s.get("monthlyCapacity", [])
            if cap:
                phys = cap.get("physical", {})
                print(f"  rawMarketingKiB: {phys.get('rawMarketingKiB')}")
                print(f"  usedKiB: {phys.get('usedKiB')}")
                print(f"  usablePerformanceTierKiB: {phys.get('usablePerformanceTierKiB')}")
                print(f"  utilizationPercentage: {phys.get('utilizationPercentage')}")
                print(f"  reportedOn: {cap.get('reportedOn')}")
            else:
                print("  capacity: None (not an ONTAPSystem or field empty)")
            print(f"  monthlyCapacity entries: {len(monthly)}")
            if monthly:
                print(f"  last month: {monthly[-1]}")
else:
    print("HTTP error:", resp.text[:300])
