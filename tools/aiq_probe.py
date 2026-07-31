"""
AIQ Raw API Probe
==================
Direct Python HTTP calls to ActiveIQ API -- no proxy, no browser, no JS.
Tries every possible request format to find what returns real data.

Usage:
  python aiq_probe.py YOUR_REFRESH_TOKEN
  python aiq_probe.py                      # reads token from localStorage backup
"""

import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import json
import time
import urllib.request
import urllib.error
import urllib.parse
import ssl
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent
BASE       = "https://api.activeiq.netapp.com"
REPORT     = SCRIPT_DIR / "aiq_probe_report.json"

# Real customer names (confirmed visible in portal)
CUSTOMERS = ["Vodacom South Africa", "Telkom SA", "Liberty Group"]
# Real serial numbers (confirmed registered)
SERIALS   = ["211839000195", "952239002356", "952239002659", "952239002236", "952239002406"]


def http(method, url, headers=None, body=None, timeout=30):
    """Raw HTTP request. Returns (status, headers_dict, body_bytes)."""
    hdrs = headers or {}
    data = None
    if body:
        if isinstance(body, dict):
            data = json.dumps(body).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        elif isinstance(body, str):
            data = body.encode("utf-8")
        else:
            data = body

    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    ctx = ssl.create_default_context()

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except Exception as e:
        return 0, {}, str(e).encode("utf-8")


def get_access_token(refresh_token):
    """Exchange refresh token for access token."""
    print("\n=== Step 1: Token Exchange ===")
    url = f"{BASE}/v1/tokens/accessToken"

    # Try multiple body formats
    attempts = [
        ("Form-encoded",  "application/x-www-form-urlencoded",
         f"grant_type=refresh_token&refresh_token={urllib.parse.quote(refresh_token)}"),
        ("JSON body",     "application/json",
         json.dumps({"grant_type": "refresh_token", "refresh_token": refresh_token})),
        ("Plain token",   "application/json",
         json.dumps({"refresh_token": refresh_token})),
    ]

    for label, ct, body_str in attempts:
        print(f"\n  Trying: {label}")
        status, hdrs, raw = http("POST", url, {
            "Content-Type": ct,
            "Accept": "application/json",
        }, body_str.encode("utf-8"))

        try:
            data = json.loads(raw)
        except:
            data = {"raw": raw.decode("utf-8", errors="replace")[:500]}

        print(f"    Status: {status}")
        print(f"    Response keys: {list(data.keys()) if isinstance(data, dict) else 'not dict'}")

        if status == 200:
            token = None
            if isinstance(data, dict):
                token = (data.get("access_token") or data.get("accessToken") or
                         data.get("token") or data.get("id_token"))
            if not token and isinstance(data, str):
                token = data.strip()

            if token:
                print(f"    Token: {token[:40]}...")
                return token
            else:
                print(f"    Response (full): {json.dumps(data)[:300]}")
                # Maybe the response itself IS the token (raw string)?
                raw_s = raw.decode("utf-8", errors="replace").strip().strip('"')
                if len(raw_s) > 50 and " " not in raw_s[:50]:
                    print(f"    Trying raw response as token...")
                    return raw_s

    print("  FAILED: Could not obtain access token")
    return None


def probe(label, method, endpoint, token, body=None, show_full=False):
    """Make an API call and log the result."""
    url = f"{BASE}{endpoint}"
    headers = {
        "AuthorizationToken": token,
        "Accept": "application/json",
    }

    t0 = time.time()
    status, resp_hdrs, raw = http(method, url, headers, body)
    ms = int((time.time() - t0) * 1000)

    try:
        data = json.loads(raw)
    except:
        data = None

    raw_s = raw.decode("utf-8", errors="replace")
    is_empty = raw_s.strip() in ["{}", "[]", "null", "", '""', "0"]
    size = len(raw_s)

    # Check if we got real data
    has_data = False
    record_count = 0
    if isinstance(data, list) and len(data) > 0:
        has_data = True
        record_count = len(data)
    elif isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list) and len(v) > 0:
                has_data = True
                record_count = len(v)
                break
        if not has_data and len(data) > 1:
            has_data = True  # Has fields at least

    marker = ">>DATA<<" if has_data and not is_empty else "  empty "
    print(f"  [{status:3}] {ms:5}ms  {marker}  {size:>7} bytes  {method:4} {endpoint[:90]}")

    if has_data and not is_empty:
        preview = json.dumps(data, default=str)[:400] if data else raw_s[:400]
        print(f"           Preview: {preview}")
        if isinstance(data, dict):
            print(f"           Keys: {list(data.keys())}")
    elif show_full and data:
        print(f"           Full: {json.dumps(data, default=str)[:500]}")

    return {
        "label": label, "method": method, "endpoint": endpoint,
        "status": status, "ms": ms, "size": size,
        "empty": is_empty, "has_data": has_data,
        "record_count": record_count,
        "body": data, "preview": raw_s[:1000],
    }


def run(refresh_token):
    results = []
    access_token = get_access_token(refresh_token)
    if not access_token:
        print("\nCannot continue without access token.")
        return

    tok = access_token

    # Also try with Bearer auth header for comparison
    print(f"\n=== Step 2: Probe with AuthorizationToken header ===")
    print(f"    Token prefix: {tok[:50]}...")

    # -- Registration & subscription (tells us what we have access to) -------
    print("\n--- Account Info ---")
    results.append(probe("Registration",    "GET", "/v1/api/registration", tok, show_full=True))
    results.append(probe("Subscription",    "GET", "/v1/api/catalogSubscription", tok, show_full=True))
    results.append(probe("User Info",       "GET", "/v1/user2/info", tok, show_full=True))
    results.append(probe("User CT",         "GET", "/v1/user2/isValidControlTowerUser", tok, show_full=True))

    # -- Watchlists ----------------------------------------------------------
    print("\n--- Watchlists ---")
    results.append(probe("WL all",          "GET", "/v1/watchlist/all", tok, show_full=True))
    results.append(probe("WL v2 all",       "GET", "/v2/watchlist/all", tok, show_full=True))
    # POST variant
    results.append(probe("WL v2 action GET","GET", "/v2/watchlist/action", tok, show_full=True))
    results.append(probe("WL v2 action POST","POST", "/v2/watchlist/action", tok,
                         body={"action": "list"}, show_full=True))

    # -- GET search with real customer names ---------------------------------
    print("\n--- GET Search (customer names) ---")
    for name in CUSTOMERS:
        enc = urllib.parse.quote(name)
        results.append(probe(f"v1 sys cust: {name}",  "GET",
            f"/v1/search/system/level/customer?searchText={enc}&limit=50", tok))
        results.append(probe(f"v3 sys: {name}",       "GET",
            f"/v3/search/system?searchText={enc}&limit=50", tok))
        results.append(probe(f"v3 agg: {name}",       "GET",
            f"/v3/search/aggregate?searchText={enc}&limit=50", tok))

    # -- POST search (maybe the API needs POST for search) -------------------
    print("\n--- POST Search (customer names) ---")
    for name in CUSTOMERS:
        results.append(probe(f"POST v1 sys cust: {name}", "POST",
            "/v1/search/system/level/customer", tok,
            body={"searchText": name, "limit": 50}))
        results.append(probe(f"POST v3 sys: {name}", "POST",
            "/v3/search/system", tok,
            body={"searchText": name, "limit": 50}))
        results.append(probe(f"POST v3 agg: {name}", "POST",
            "/v3/search/aggregate", tok,
            body={"searchText": name, "limit": 50}))

    # -- Serial number probes ------------------------------------------------
    print("\n--- Serial Number Probes ---")
    for sn in SERIALS:
        results.append(probe(f"v3 sys sn:{sn}",       "GET",
            f"/v3/search/system?searchText={sn}&limit=10", tok))
        results.append(probe(f"POST v3 sys sn:{sn}",  "POST",
            "/v3/search/system", tok, body={"searchText": sn, "limit": 10}))
        results.append(probe(f"clusterview:{sn}",      "GET",
            f"/v1/clusterview/get-cluster-summary/{sn}", tok, show_full=True))
        results.append(probe(f"health sys:{sn}",       "GET",
            f"/v1/health/summary/level/system/id/{sn}", tok, show_full=True))
        break  # Just first serial to save time; expand if we get hits

    # -- Capacity / EoS / Health (breadth, no scope) -------------------------
    print("\n--- Breadth Endpoints ---")
    for ep in ["/eos/details", "/eos/contracts/details", "/v2/health/risks",
               "/capacity2/usage", "/firmware/details", "/keystone/customers",
               "/v1/health/summary", "/v1/health/details"]:
        results.append(probe(f"breadth: {ep}", "GET", ep, tok))

    # -- POST breadth (maybe these need POST too?) ---------------------------
    print("\n--- POST Breadth ---")
    results.append(probe("POST /eos/details", "POST", "/eos/details", tok, body={}))
    results.append(probe("POST /v2/health/risks", "POST", "/v2/health/risks", tok, body={}))

    # -- Try with Bearer auth instead of AuthorizationToken ------------------
    print("\n--- Bearer Auth Comparison (first customer) ---")
    name = CUSTOMERS[0]
    enc  = urllib.parse.quote(name)
    url  = f"{BASE}/v1/search/system/level/customer?searchText={enc}&limit=50"
    bearer_hdrs = {"Authorization": f"Bearer {tok}", "Accept": "application/json"}
    status, _, raw = http("GET", url, bearer_hdrs)
    try:
        data = json.loads(raw)
    except:
        data = {}
    raw_s = raw.decode("utf-8", errors="replace")
    print(f"  [{status}] Bearer GET {url[:80]}")
    print(f"         Size: {len(raw_s)}, Preview: {raw_s[:300]}")

    # -- Try with the refresh token directly as AuthorizationToken -----------
    print("\n--- Refresh Token as AuthorizationToken ---")
    url = f"{BASE}/v1/search/system/level/customer?searchText={enc}&limit=50"
    rt_hdrs = {"AuthorizationToken": refresh_token, "Accept": "application/json"}
    status, _, raw = http("GET", url, rt_hdrs)
    raw_s = raw.decode("utf-8", errors="replace")
    print(f"  [{status}] Refresh-as-token GET {url[:80]}")
    print(f"         Size: {len(raw_s)}, Preview: {raw_s[:300]}")

    # -- Summary -------------------------------------------------------------
    print("\n\n" + "=" * 72)
    print("  SUMMARY")
    print("=" * 72)
    hits = [r for r in results if r.get("has_data") and not r.get("empty")]
    print(f"\n  Total probes:      {len(results)}")
    print(f"  With real data:    {len(hits)}")
    if hits:
        print(f"\n  Endpoints that returned data:")
        for h in hits:
            print(f"    [{h['status']}] {h['method']:4} {h['endpoint'][:80]}  ({h['record_count']} records, {h['size']} bytes)")
    else:
        print(f"\n  NO ENDPOINT RETURNED DATA.")
        print(f"  This means the API token may not have data catalog access.")
        print(f"  Check: activeiq.netapp.com -> Quick Links -> API Services -> Catalog Subscription")

    # Save full report
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Full report: {REPORT}")


if __name__ == "__main__":
    # Get refresh token from argv or from the config file
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        token = sys.argv[1]
    else:
        # Try to read from the app's saved config
        config_paths = [
            SCRIPT_DIR / "aiq_config.json",
            Path.home() / "NetApp AIQ Advisor" / "aiq_config.json",
        ]
        token = None
        for cp in config_paths:
            if cp.exists():
                try:
                    cfg = json.loads(cp.read_text(encoding="utf-8"))
                    token = cfg.get("refreshToken") or cfg.get("refresh_token")
                    if token:
                        print(f"  Read token from: {cp}")
                        break
                except:
                    pass

        if not token:
            print("Usage: python aiq_probe.py YOUR_REFRESH_TOKEN")
            print("  or save it in aiq_config.json as {\"refreshToken\": \"...\"}")
            sys.exit(1)

    run(token)
