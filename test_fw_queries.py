"""
Test the exact cluster query from server.py to see what breaks.
"""
import json, ssl, urllib.request, urllib.error

CACHE_FILE = "aiq_config.json"
GQL_URL = "https://gql.aiq.netapp.com/graphql"
TOKEN_URL = "https://api.activeiq.netapp.com/v1/tokens/accessToken"

with open(CACHE_FILE, encoding="utf-8") as f:
    cache = json.load(f)

refresh_token = cache.get("refreshToken", "")
print("Getting access token...")

def _http_post_json(url, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"}, method="POST")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

st, tok_resp = _http_post_json(TOKEN_URL, {"refresh_token": refresh_token})
print(f"Token status: {st}")
if st not in (200, 201):
    print(f"Token error: {tok_resp}")
    exit()

access_token = tok_resp.get("access_token") or tok_resp.get("accessToken") or ""
print(f"Token length: {len(access_token)}")
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {access_token}",
}

def gql(query, label=""):
    req = urllib.request.Request(GQL_URL,
        data=json.dumps({"query": query}).encode(),
        headers=headers, method="POST")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
    except Exception as ex:
        return 0, {"error": str(ex)}

# Test A: exact query from server.py (line 978-1020)
print("\n=== A: Server.py exact cluster query ===")
st, r = gql("""{
  clusters(pageSize: 3) {
    cursor
    clusters {
      id
      name
      managementIPAddress
      osVersion
      isHAConfigured
      ageInYears
      osRecommendation { recommendedVersion }
      snapMirrorRelationships { totalCount }
      systems { serialNumber }
      switches {
        switchSerialNumber
        deviceName
        role
        vendor
        model
        ipAddress
        isDiscovered
        isMonitored
        versionInfo { fwVersion rcfVersion }
      }
      shelves {
        serialNumber
        shelfId
        hardwareModel { name endOfAvailability endOfHwSupport }
        moduleHardwareModel { name }
        shelfFirmware { currentVersion recommendedVersion autoUpdateEligible postingDate }
      }
      capacity {
        physical { usedKiB rawMarketingKiB usablePerformanceTierKiB qoqUtilizationPercentage yoyUtilizationPercentage }
        logical { usedKiB }
        reportedOn
      }
      monthlyCapacity {
        month
        physical { usedKiB rawMarketingKiB qoqUtilizationPercentage }
      }
    }
  }
}""")
print(f"HTTP {st}")
if isinstance(r, dict) and r.get("errors"):
    print("ERRORS:")
    for e in r["errors"]:
        print(f"  - {e.get('message', '')[:200]}")
else:
    clusters = (r.get("data") or {}).get("clusters", {}).get("clusters", [])
    print(f"Clusters returned: {len(clusters)}")
    for cl in clusters[:3]:
        shelves = cl.get("shelves", [])
        systems = cl.get("systems", [])
        print(f"  Cluster: {cl.get('name')} | systems={len(systems)} | shelves={len(shelves)}")
        for sh in shelves[:2]:
            print(f"    Shelf: {json.dumps(sh)[:400]}")

# Test B: clusters with just shelves and shelfFirmware
print("\n=== B: Clusters shelves with shelfFirmware only ===")
st, r = gql("""{
  clusters(pageSize: 5) {
    clusters {
      id name
      shelves {
        serialNumber shelfId
        hardwareModel { name }
        moduleHardwareModel { name }
        shelfFirmware { currentVersion recommendedVersion autoUpdateEligible }
      }
    }
  }
}""")
print(f"HTTP {st}")
if isinstance(r, dict) and r.get("errors"):
    for e in r["errors"]:
        print(f"  ERROR: {e.get('message', '')[:200]}")
else:
    clusters = (r.get("data") or {}).get("clusters", {}).get("clusters", [])
    print(f"Clusters: {len(clusters)}")
    for cl in clusters:
        shelves = cl.get("shelves", [])
        print(f"  {cl.get('name')}: {len(shelves)} shelves")
        for sh in shelves[:2]:
            print(f"    {json.dumps(sh)[:400]}")

# Test C: system firmware per system
print("\n=== C: System firmware (systemFirmware on ONTAPSystem) ===")
st, r = gql("""{
  systems(pageSize: 3) {
    systems {
      serialNumber
      hostName
      ... on ONTAPSystem {
        systemFirmware { type currentVersion recommendedVersion autoUpdateEligible postingDate }
        diskQualificationPackage { currentVersion recommendedVersion autoUpdateEligible }
        motherboardFirmware { currentVersion recommendedVersion }
      }
    }
  }
}""")
print(f"HTTP {st}")
if isinstance(r, dict) and r.get("errors"):
    for e in r["errors"]:
        print(f"  ERROR: {e.get('message', '')[:200]}")
else:
    systems = (r.get("data") or {}).get("systems", {}).get("systems", [])
    print(f"Systems: {len(systems)}")
    for s in systems:
        fw = s.get("systemFirmware")
        dqp = s.get("diskQualificationPackage")
        mb = s.get("motherboardFirmware")
        print(f"  {s.get('serialNumber')}: systemFirmware={json.dumps(fw)}, dqp={json.dumps(dqp)}, motherboard={json.dumps(mb)}")

# Test D: system shelves with shelfFirmware
print("\n=== D: System shelves with shelfFirmware ===")
st, r = gql("""{
  systems(pageSize: 3) {
    systems {
      serialNumber
      ... on ONTAPSystem {
        shelves {
          serialNumber shelfId
          hardwareModel { name }
          moduleHardwareModel { name }
          shelfFirmware { currentVersion recommendedVersion autoUpdateEligible }
        }
      }
    }
  }
}""")
print(f"HTTP {st}")
if isinstance(r, dict) and r.get("errors"):
    for e in r["errors"]:
        print(f"  ERROR: {e.get('message', '')[:300]}")
else:
    systems = (r.get("data") or {}).get("systems", {}).get("systems", [])
    print(f"Systems: {len(systems)}")
    for s in systems:
        shelves = s.get("shelves", [])
        print(f"  SN {s.get('serialNumber')}: {len(shelves)} shelves")
        for sh in shelves[:2]:
            print(f"    {json.dumps(sh)[:400]}")
