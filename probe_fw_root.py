"""
Live probe of root-level firmware queries:
  - systemFirmwares
  - driveFirmwares
  - shelfFirmwares
  - diskQualificationPackages
Also tests per-system shelves -> drives -> firmwareRevision
"""
import json, ssl, urllib.request, urllib.error

CACHE_FILE  = "aiq_config.json"
GQL_URL     = "https://gql.aiq.netapp.com/graphql"
TOKEN_URL   = "https://api.activeiq.netapp.com/v1/tokens/accessToken"

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
        with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

st, tok_resp = _http_post_json(TOKEN_URL, {"refresh_token": refresh_token})
if st not in (200, 201):
    print(f"Token error {st}: {tok_resp}")
    exit()
access_token = tok_resp.get("access_token") or tok_resp.get("accessToken") or ""
print(f"Token OK ({len(access_token)} chars)")
headers = {"Content-Type": "application/json", "Authorization": f"Bearer {access_token}"}

def gql(query):
    req = urllib.request.Request(GQL_URL,
        data=json.dumps({"query": query}).encode(),
        headers=headers, method="POST")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=45) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
    except Exception as ex:
        return 0, {"error": str(ex)}

# ═══════════════════════════════════════════════
# A: systemFirmwares root query - full introspection
# ═══════════════════════════════════════════════
print("\n=== A: __type(systemFirmwares) - discover return type ===")
st, r = gql("""{ __type(name: "Query") { fields { name args { name type { name kind ofType { name kind } } } } } }""")
print(f"HTTP {st}")
if not r.get("errors"):
    fields = r.get("data", {}).get("__type", {}).get("fields", [])
    fw_fields = [f for f in fields if any(x in f["name"].lower() for x in ("firmware", "shelf", "drive", "disk"))]
    for f in fw_fields:
        print(f"  {f['name']}: args={[a['name'] for a in f.get('args', [])]}")

# ═══════════════════════════════════════════════
# B: systemFirmwares - what does it return?
# ═══════════════════════════════════════════════
print("\n=== B: systemFirmwares(pageSize:3) ===")
st, r = gql("""{ systemFirmwares(pageSize: 3) { cursor totalCount systemFirmwares { type currentVersion recommendedVersion autoUpdateEligible postingDate } } }""")
print(f"HTTP {st}")
if r.get("errors"):
    for e in r["errors"]:
        print(f"  ERROR: {e.get('message','')[:300]}")
else:
    d = (r.get("data") or {}).get("systemFirmwares", {})
    print(f"  totalCount={d.get('totalCount')} cursor={d.get('cursor','')[:30]}")
    for fw in (d.get("systemFirmwares") or []):
        print(f"  {json.dumps(fw)}")

# ═══════════════════════════════════════════════
# C: driveFirmwares
# ═══════════════════════════════════════════════
print("\n=== C: driveFirmwares(pageSize:3) ===")
st, r = gql("""{ driveFirmwares(pageSize: 3) { cursor totalCount driveFirmwares { currentVersion recommendedVersion autoUpdateEligible driveModel } } }""")
print(f"HTTP {st}")
if r.get("errors"):
    for e in r["errors"]:
        print(f"  ERROR: {e.get('message','')[:300]}")
else:
    d = (r.get("data") or {}).get("driveFirmwares", {})
    print(f"  totalCount={d.get('totalCount')} cursor={d.get('cursor','')[:30]}")
    for fw in (d.get("driveFirmwares") or []):
        print(f"  {json.dumps(fw)}")

# ═══════════════════════════════════════════════
# D: shelfFirmwares
# ═══════════════════════════════════════════════
print("\n=== D: shelfFirmwares(pageSize:3) ===")
st, r = gql("""{ shelfFirmwares(pageSize: 3) { cursor totalCount shelfFirmwares { currentVersion recommendedVersion autoUpdateEligible postingDate hardwareModel { name } moduleHardwareModel { name } } } }""")
print(f"HTTP {st}")
if r.get("errors"):
    for e in r["errors"]:
        print(f"  ERROR: {e.get('message','')[:300]}")
else:
    d = (r.get("data") or {}).get("shelfFirmwares", {})
    print(f"  totalCount={d.get('totalCount')} cursor={d.get('cursor','')[:30]}")
    for fw in (d.get("shelfFirmwares") or []):
        print(f"  {json.dumps(fw)}")

# ═══════════════════════════════════════════════
# E: diskQualificationPackages
# ═══════════════════════════════════════════════
print("\n=== E: diskQualificationPackages(pageSize:3) ===")
st, r = gql("""{ diskQualificationPackages(pageSize: 3) { cursor totalCount diskQualificationPackages { currentVersion recommendedVersion autoUpdateEligible } } }""")
print(f"HTTP {st}")
if r.get("errors"):
    for e in r["errors"]:
        print(f"  ERROR: {e.get('message','')[:300]}")
else:
    d = (r.get("data") or {}).get("diskQualificationPackages", {})
    print(f"  totalCount={d.get('totalCount')} cursor={d.get('cursor','')[:30]}")
    for fw in (d.get("diskQualificationPackages") or []):
        print(f"  {json.dumps(fw)}")

# ═══════════════════════════════════════════════
# F: shelves with drives (firmwareRevision on Drive)
# ═══════════════════════════════════════════════
print("\n=== F: systems -> shelves -> drives with firmwareRevision ===")
st, r = gql("""{ systems(pageSize: 2) { systems { serialNumber ... on ONTAPSystem { shelves { serialNumber shelfId hardwareModel { name } drives { totalCount drives { firmwareRevision vendor hardwareModel { name } } } } } } } }""")
print(f"HTTP {st}")
if r.get("errors"):
    for e in r["errors"]:
        print(f"  ERROR: {e.get('message','')[:300]}")
else:
    systems = (r.get("data") or {}).get("systems", {}).get("systems", [])
    print(f"  Systems: {len(systems)}")
    for s in systems:
        shelves = s.get("shelves", [])
        print(f"  SN {s.get('serialNumber')}: {len(shelves)} shelves")
        for sh in shelves[:2]:
            drives = sh.get("drives", {})
            drive_list = drives.get("drives", [])
            print(f"    Shelf {sh.get('shelfId')} {sh.get('hardwareModel',{}).get('name','')} - {drives.get('totalCount',0)} drives")
            for d in drive_list[:3]:
                print(f"      Drive: model={d.get('hardwareModel',{}).get('name','')} fw={d.get('firmwareRevision','')} vendor={d.get('vendor','')}")

# ═══════════════════════════════════════════════
# G: systems -> systemFirmware -> type field (is it a list or single object?)
# ═══════════════════════════════════════════════
print("\n=== G: systemFirmware field - is it list or object? ===")
st, r = gql("""{ systems(pageSize: 3) { systems { serialNumber ... on ONTAPSystem { systemFirmware { type currentVersion recommendedVersion autoUpdateEligible postingDate } motherboardFirmware { currentVersion recommendedVersion } } } } }""")
print(f"HTTP {st}")
if r.get("errors"):
    for e in r["errors"]:
        print(f"  ERROR: {e.get('message','')[:300]}")
else:
    systems = (r.get("data") or {}).get("systems", {}).get("systems", [])
    for s in systems:
        sfw = s.get("systemFirmware")
        mbfw = s.get("motherboardFirmware")
        print(f"  SN {s.get('serialNumber')}: systemFirmware type={type(sfw).__name__} val={json.dumps(sfw)[:200]}")
        print(f"    motherboardFirmware: {json.dumps(mbfw)[:200]}")
