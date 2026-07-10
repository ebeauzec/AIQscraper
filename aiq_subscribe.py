"""
AIQ Format Finder - now that subscription is active,
find the exact request format that returns data.
"""
import io, sys, json, ssl, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import urllib.request, urllib.error, urllib.parse
from pathlib import Path

BASE = "https://api.activeiq.netapp.com"
SCRIPT_DIR = Path(__file__).parent


def http(method, url, headers=None, body=None):
    hdrs = headers or {}
    data = None
    if body is not None:
        if isinstance(body, dict):
            data = json.dumps(body).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        elif isinstance(body, str):
            data = body.encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, str(e).encode("utf-8")


def get_access_token(refresh_token):
    for ct, body in [
        ("application/x-www-form-urlencoded",
         f"grant_type=refresh_token&refresh_token={urllib.parse.quote(refresh_token)}"),
        ("application/json", json.dumps({"refresh_token": refresh_token})),
    ]:
        status, raw = http("POST", f"{BASE}/v1/tokens/accessToken",
                           {"Content-Type": ct, "Accept": "application/json"}, body)
        if status == 200:
            try:
                data = json.loads(raw)
                tok = data.get("access_token") or data.get("accessToken") or data.get("token")
                if tok: return tok
            except: pass
            raw_s = raw.decode("utf-8", errors="replace").strip().strip('"')
            if len(raw_s) > 30: return raw_s
    return None


def probe(label, method, endpoint, token, body=None):
    hdrs = {"AuthorizationToken": token, "Accept": "application/json"}
    if body and method in ["POST", "PUT"]:
        hdrs["Content-Type"] = "application/json"
    
    url = f"{BASE}{endpoint}"
    status, raw = http(method, url, hdrs, body)
    raw_s = raw.decode("utf-8", errors="replace")
    
    # Classify the response
    is_data = (status == 200 and raw_s.strip() not in ["{}", "[]", "null", ""]
               and "Unsupported" not in raw_s and "Unauthorized" not in raw_s
               and "Internal server error" not in raw_s)
    
    marker = "** HIT **" if is_data else f"   {status}   "
    print(f"  {marker}  {method:4} {endpoint[:80]}")
    if body:
        print(f"           body: {json.dumps(body)[:100]}")
    if is_data:
        print(f"           >>> {raw_s[:400]}")
    elif status not in [404]:
        print(f"           {raw_s[:150]}")
    
    return {"endpoint": endpoint, "method": method, "status": status,
            "body_sent": body, "response": raw_s[:2000], "has_data": is_data}


def main():
    print("=" * 60)
    print("  AIQ Format Finder")
    print("  Subscription is active - finding correct request format")
    print("=" * 60)

    cfg_path = SCRIPT_DIR / "aiq_config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    refresh_token = cfg.get("refreshToken") or cfg.get("refresh_token")
    
    print("\n  Getting access token...")
    token = get_access_token(refresh_token)
    if not token:
        print("  FAILED."); return
    print(f"  OK: {token[:40]}...")

    results = []
    
    # ── Watchlists (v1 gave 500 = it's alive, just needs right format) ──
    print("\n--- Watchlists (was 500 = endpoint exists) ---")
    results.append(probe("WL GET v1", "GET", "/v1/watchlist/all", token))
    results.append(probe("WL POST v1", "POST", "/v1/watchlist/all", token, {}))
    results.append(probe("WL POST v1 list", "POST", "/v1/watchlist/all", token, {"action": "list"}))
    results.append(probe("WL GET no ver", "GET", "/watchlist/all", token))
    # v2 watchlist action endpoint (documented as POST)
    results.append(probe("WL v2 action", "POST", "/v2/watchlist/action", token, {"action": "list"}))
    results.append(probe("WL v2 action2", "POST", "/v2/watchlist/action", token, {"type": "list"}))
    results.append(probe("WL v2 action3", "POST", "/v2/watchlist/action", token, {}))

    # ── v3 search (was 400 Bad Request = endpoint exists, format wrong) ──
    print("\n--- v3 Search (was 400 = needs right params) ---")
    # Different parameter names
    for param_name in ["searchText", "search", "query", "q", "text", "name", "filter"]:
        results.append(probe(f"v3 sys ?{param_name}", "GET",
            f"/v3/search/system?{param_name}=vodacom&limit=10", token))
    
    # POST with different body formats
    for body in [
        {"searchText": "vodacom", "limit": 10},
        {"search": "vodacom", "limit": 10},
        {"query": "vodacom", "limit": 10},
        {"q": "vodacom"},
        {"text": "vodacom"},
        {"filter": {"name": "vodacom"}},
        {"searchText": "vodacom", "level": "customer", "limit": 10},
        {"searchText": "vodacom", "searchType": "system", "limit": 10},
    ]:
        results.append(probe(f"v3 sys POST", "POST", "/v3/search/system", token, body))

    # ── v3 aggregate search ──
    print("\n--- v3 Aggregate Search ---")
    for param in ["searchText", "search", "query", "q"]:
        results.append(probe(f"v3 agg ?{param}", "GET",
            f"/v3/search/aggregate?{param}=vodacom&limit=10", token))
    results.append(probe("v3 agg POST", "POST", "/v3/search/aggregate", token,
                         {"searchText": "vodacom", "limit": 10}))

    # ── v3 parent search ──
    print("\n--- v3 Parent Search ---")
    for param in ["searchText", "search", "query", "q"]:
        results.append(probe(f"v3 parent ?{param}", "GET",
            f"/v3/search/parent?{param}=vodacom&limit=10", token))

    # ── v2 health risks (said "No search parameter specified") ──
    print("\n--- v2 Health Risks (needs search params) ---")
    for param in ["searchText", "search", "query", "serialNumber", "customerId", "customerName"]:
        results.append(probe(f"v2 risks ?{param}", "GET",
            f"/v2/health/risks?{param}=vodacom&limit=10", token))
    # POST variants
    results.append(probe("v2 risks POST", "POST", "/v2/health/risks", token,
                         {"searchText": "vodacom"}))
    results.append(probe("v2 risks POST sn", "POST", "/v2/health/risks", token,
                         {"serialNumber": "211839000195"}))
    results.append(probe("v2 risks POST sns", "POST", "/v2/health/risks", token,
                         {"serialNumbers": ["211839000195"]}))

    # ── Serial number direct lookups ──
    print("\n--- Serial Number Lookups ---")
    sn = "211839000195"
    results.append(probe("clusterview", "GET", f"/v1/clusterview/get-cluster-summary/{sn}", token))
    results.append(probe("health sys", "GET", f"/v1/health/summary/level/system/id/{sn}", token))
    results.append(probe("v3 search sn", "GET", f"/v3/search/system?searchText={sn}&limit=10", token))
    results.append(probe("v3 search sn q", "GET", f"/v3/search/system?query={sn}&limit=10", token))
    results.append(probe("v3 search sn POST", "POST", "/v3/search/system", token,
                         {"searchText": sn, "limit": 10}))
    # system-level endpoints
    results.append(probe("sys detail", "GET", f"/v1/system/details/{sn}", token))
    results.append(probe("sys info", "GET", f"/v1/system/info/{sn}", token))
    results.append(probe("sys overview", "GET", f"/v1/system/overview/{sn}", token))

    # ── Count endpoints (lightweight, might reveal structure) ──
    print("\n--- Count Endpoints ---")
    results.append(probe("count agg", "GET", "/v3/search/count/aggregate?searchText=vodacom", token))
    results.append(probe("count parent", "GET", "/v3/search/count/parent?searchText=vodacom", token))
    results.append(probe("count agg q", "GET", "/v3/search/count/aggregate?query=vodacom", token))

    # ── User info (partner level) ──
    print("\n--- User/Partner Info ---")
    results.append(probe("user info", "GET", "/v1/user2/info", token))
    results.append(probe("user partner", "GET", "/v1/partner/customers", token))
    results.append(probe("user partner2", "GET", "/v2/partner/customers", token))
    results.append(probe("partner sys", "GET", "/v1/search/system/level/partner?limit=10", token))
    results.append(probe("partner sys2", "GET", "/v1/search/system/level/partner?searchText=vodacom&limit=10", token))

    # ── Summary ──
    print("\n" + "=" * 60)
    hits = [r for r in results if r["has_data"]]
    print(f"  TOTAL PROBES: {len(results)}")
    print(f"  WITH DATA:    {len(hits)}")
    if hits:
        print("\n  *** WORKING ENDPOINTS: ***")
        for h in hits:
            print(f"    {h['method']} {h['endpoint'][:80]}")
            print(f"    Response: {h['response'][:300]}")
    else:
        # Show non-404 responses (these are alive but need different format)
        alive = [r for r in results if r["status"] not in [404, 0]]
        print(f"\n  Non-404 responses (these endpoints exist): {len(alive)}")
        for a in alive:
            print(f"    [{a['status']}] {a['method']} {a['endpoint'][:70]}")
            print(f"           {a['response'][:100]}")

    # Save report
    report_path = SCRIPT_DIR / "aiq_format_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Full report: {report_path}")


if __name__ == "__main__":
    main()
