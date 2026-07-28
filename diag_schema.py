"""
Schema probe: find the correct field names on System type and Query root.
"""
import json, ssl, urllib.request, urllib.error, os, sys

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "aiq_config.json")
GQL_URL = "https://gql.aiq.netapp.com/graphql"
TOKEN_URL = "https://api.activeiq.netapp.com/v1/tokens/accessToken"

with open(CONFIG_FILE, encoding="utf-8") as f:
    cfg = json.load(f)
refresh_token = cfg.get("refreshToken", "")

ctx = ssl.create_default_context()

def _post(url, body, headers=None):
    h = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

# Get token
st, tr = _post(TOKEN_URL, {"refresh_token": refresh_token})
token = tr.get("access_token", "")
print(f"Token status: {st}, len={len(token)}")

gql_headers = {"Authorization": f"Bearer {token}"}

def gql(query):
    st, r = _post(GQL_URL, {"query": query}, gql_headers)
    return st, r

# ── Introspect Query type fields ──────────────────────────────────────────────
print("\n=== TOP-LEVEL QUERY FIELDS ===")
st, r = gql("{ __schema { queryType { fields { name } } } }")
if st == 200:
    fields = (r.get("data", {}).get("__schema", {}).get("queryType", {}).get("fields") or [])
    for f in sorted(fields, key=lambda x: x["name"]):
        print(f"  {f['name']}")
else:
    print(f"HTTP {st}: {r}")

# ── Introspect System type ────────────────────────────────────────────────────
print("\n=== SYSTEM TYPE FIELDS ===")
st, r = gql('{ __type(name: "System") { fields { name type { name kind ofType { name } } } } }')
if st == 200:
    sys_fields = (r.get("data", {}).get("__type", {}).get("fields") or [])
    for f in sys_fields:
        t = f.get("type", {})
        type_name = t.get("name") or (t.get("ofType") or {}).get("name", "")
        print(f"  {f['name']}: {type_name}")
else:
    print(f"HTTP {st}: {r}")

# ── Try minimal systems query with just serialNumber ─────────────────────────
print("\n=== MINIMAL SYSTEMS QUERY (serialNumber only) ===")
st, r = gql("{ systems(pageSize: 5) { totalCount systems { serialNumber } } }")
if st == 200:
    d = (r.get("data") or {}).get("systems") or {}
    print(f"  totalCount={d.get('totalCount')}, returned={len(d.get('systems') or [])}")
    for s in (d.get("systems") or [])[:3]:
        print(f"  {s}")
else:
    print(f"HTTP {st}: {r.get('errors', r)}")

# ── Try watchlist-related query names ─────────────────────────────────────────
print("\n=== WATCHLIST QUERY PROBE ===")
for q_name in ["watchlists", "watchlist", "myWatchlists", "getWatchlists"]:
    st2, r2 = gql(f"{{ {q_name} {{ id name }} }}")
    if st2 == 200:
        print(f"  '{q_name}': WORKS -> {r2.get('data')}")
    else:
        errs = (r2.get("errors") or [{}])[0].get("message", "")[:80]
        print(f"  '{q_name}': HTTP {st2} -> {errs}")
