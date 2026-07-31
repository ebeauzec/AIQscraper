"""
Standalone diagnostic: test the systems GQL query directly using the same
token the server has cached, and print exactly what the API returns.
"""
import json, ssl, urllib.request, urllib.error, os, sys

CACHE_FILE = os.path.join(os.path.dirname(__file__), "aiq_config.json")
GQL_URL = "https://gql.aiq.netapp.com/graphql"
TOKEN_URL = "https://api.activeiq.netapp.com/v1/tokens/accessToken"

# ── Load cached config ────────────────────────────────────────────────────────
try:
    with open(CACHE_FILE, encoding="utf-8") as f:
        cache = json.load(f)
except Exception as e:
    print(f"ERROR: could not load cache: {e}")
    sys.exit(1)

refresh_token = cache.get("refreshToken", "")
if not refresh_token:
    print("ERROR: No refreshToken in cache. Save settings first.")
    sys.exit(1)

# ── Get fresh access token ────────────────────────────────────────────────────
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

print("Exchanging refresh token for access token...")
st, tok_resp = _http_post_json(TOKEN_URL, {"refresh_token": refresh_token})
print(f"  Token exchange status: {st}")
if st not in (200, 201) or not isinstance(tok_resp, dict):
    print(f"  Response: {tok_resp}")
    sys.exit(1)

access_token = tok_resp.get("access_token") or tok_resp.get("accessToken") or ""
if not access_token:
    print(f"  ERROR: no access_token in response: {tok_resp}")
    sys.exit(1)
print(f"  Access token obtained (length={len(access_token)})")

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
            resp = json.loads(r.read())
            if label:
                print(f"\n[{label}] HTTP 200")
            return resp
    except urllib.error.HTTPError as e:
        body = e.read()
        if label:
            print(f"\n[{label}] HTTP {e.code}: {body[:300]}")
        return {}
    except Exception as ex:
        if label:
            print(f"\n[{label}] Exception: {ex}")
        return {}

# ── Test 1: Watchlists ────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 1: Discover watchlists")
wl_resp = gql("{ watchlists { id name } }", "Watchlists")
wl_data = (wl_resp.get("data") or {}).get("watchlists") or []
print(f"  Found {len(wl_data)} watchlists:")
for w in wl_data:
    print(f"    id={w.get('id')}  name={w.get('name')}")
errors = wl_resp.get("errors")
if errors:
    print(f"  GQL errors: {errors}")

# ── Test 2: Systems UNFILTERED ────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 2: Systems query — UNFILTERED (no watchlistId)")
q2 = """{ systems(pageSize: 5) { totalCount cursor systems { serialNumber hostname } } }"""
r2 = gql(q2, "Systems unfiltered")
d2 = (r2.get("data") or {}).get("systems") or {}
print(f"  totalCount={d2.get('totalCount')}  systems returned={len(d2.get('systems') or [])}")
if r2.get("errors"):
    print(f"  GQL errors: {r2['errors']}")

# ── Test 3: Systems per watchlist ─────────────────────────────────────────────
if wl_data:
    for wl in wl_data[:3]:
        wid = wl.get("id", "")
        wname = wl.get("name", "")
        print("\n" + "="*60)
        print(f"TEST 3: Systems in watchlist '{wname}' (id={wid})")
        q3 = '{ systems(pageSize: 5, watchlistId: "' + wid + '") { totalCount cursor systems { serialNumber hostname } } }'
        r3 = gql(q3, f"Systems wl={wid[:20]}")
        d3 = (r3.get("data") or {}).get("systems") or {}
        print(f"  totalCount={d3.get('totalCount')}  systems returned={len(d3.get('systems') or [])}")
        if r3.get("errors"):
            print(f"  GQL errors: {r3['errors']}")
        syss = d3.get("systems") or []
        for s in syss[:3]:
            print(f"    serial={s.get('serialNumber')}  host={s.get('hostname')}")
else:
    print("\nNo watchlists to test with watchlistId filter.")

# ── Test 4: Clusters ──────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 4: Clusters (sanity check that API is returning data)")
q4 = "{ clusters(pageSize: 5) { cursor clusters { id name } } }"
r4 = gql(q4, "Clusters")
d4 = (r4.get("data") or {}).get("clusters") or {}
cls = d4.get("clusters") or []
print(f"  clusters returned: {len(cls)}")
for c in cls[:3]:
    print(f"    id={c.get('id')}  name={c.get('name')}")
if r4.get("errors"):
    print(f"  GQL errors: {r4['errors']}")

print("\n" + "="*60)
print("DONE. Review the output above to identify why systems returns 0.")
