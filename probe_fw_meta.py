"""
Introspect SystemFirmwareMeta, DriveFirmwareMeta, ShelfFirmwareMeta, DiskQualificationPackageMeta
to understand the correct field structure.
"""
import json, ssl, urllib.request, urllib.error

CACHE_FILE  = "aiq_config.json"
GQL_URL     = "https://gql.aiq.netapp.com/graphql"
TOKEN_URL   = "https://api.activeiq.netapp.com/v1/tokens/accessToken"

with open(CACHE_FILE, encoding="utf-8") as f:
    cache = json.load(f)
refresh_token = cache.get("refreshToken", "")

def _http_post_json(url, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

st, tok_resp = _http_post_json(TOKEN_URL, {"refresh_token": refresh_token})
access_token = tok_resp.get("access_token") or tok_resp.get("accessToken") or ""
print(f"Token OK ({len(access_token)} chars)")
headers = {"Content-Type": "application/json", "Authorization": f"Bearer {access_token}"}

def gql(query):
    req = urllib.request.Request(GQL_URL, data=json.dumps({"query": query}).encode(), headers=headers, method="POST")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=45) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
    except Exception as ex:
        return 0, {"error": str(ex)}

# Introspect all Meta types
for type_name in ["SystemFirmwareMeta", "DriveFirmwareMeta", "ShelfFirmwareMeta", "DiskQualificationPackageMeta"]:
    print(f"\n=== {type_name} ===")
    st, r = gql(f'{{ __type(name: "{type_name}") {{ name kind fields {{ name type {{ name kind ofType {{ name kind }} }} }} }} }}')
    if r.get("errors"):
        for e in r["errors"]: print(f"  ERROR: {e.get('message','')[:200]}")
    else:
        t = (r.get("data") or {}).get("__type", {})
        if not t:
            print(f"  NOT FOUND")
        else:
            for f in t.get("fields", []):
                ot = f.get("type", {})
                fname = ot.get("name") or f"{ot.get('kind')}({(ot.get('ofType') or {}).get('name','')})"
                print(f"  {f['name']}: {fname}")

# Now try the correct structure
print("\n=== systemFirmwares actual query ===")
# First try with just querying the type field
st, r = gql("{ systemFirmwares(pageSize: 3) { type version serialNumbers } }")
print(f"HTTP {st}")
if r.get("errors"):
    for e in r["errors"]: print(f"  {e.get('message','')[:300]}")
else:
    print(json.dumps((r.get("data") or {}), indent=2)[:500])

print("\n=== driveFirmwares actual query ===")
st, r = gql("{ driveFirmwares(pageSize: 3) { driveModel version serialNumbers } }")
print(f"HTTP {st}")
if r.get("errors"):
    for e in r["errors"]: print(f"  {e.get('message','')[:300]}")
else:
    print(json.dumps((r.get("data") or {}), indent=2)[:500])

print("\n=== shelfFirmwares actual query ===")
st, r = gql("{ shelfFirmwares(pageSize: 3) { shelfModuleName version serialNumbers } }")
print(f"HTTP {st}")
if r.get("errors"):
    for e in r["errors"]: print(f"  {e.get('message','')[:300]}")
else:
    print(json.dumps((r.get("data") or {}), indent=2)[:500])

print("\n=== diskQualificationPackages actual query ===")
st, r = gql("{ diskQualificationPackages(pageSize: 3) { version serialNumbers } }")
print(f"HTTP {st}")
if r.get("errors"):
    for e in r["errors"]: print(f"  {e.get('message','')[:300]}")
else:
    print(json.dumps((r.get("data") or {}), indent=2)[:500])
