"""
AIQ Interactive Discovery
==========================
Interactive tool: you type a search term, we hit every known API endpoint
with it, and show you what comes back. You pick the right result.

Usage:  python aiq_discover.py
"""

import io, sys, json, time, ssl, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from datetime import datetime

BASE = "https://api.activeiq.netapp.com"
SCRIPT_DIR = Path(__file__).parent
OUTPUT = SCRIPT_DIR / "aiq_discovered_systems.json"


def http(method, url, headers=None, body=None, timeout=30):
    hdrs = headers or {}
    data = None
    if body is not None:
        if isinstance(body, dict):
            data = json.dumps(body).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        elif isinstance(body, (str, bytes)):
            data = body.encode("utf-8") if isinstance(body, str) else body
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, str(e).encode("utf-8")


def get_access_token(refresh_token):
    """Exchange refresh token for access token."""
    url = f"{BASE}/v1/tokens/accessToken"

    formats = [
        ("application/x-www-form-urlencoded",
         f"grant_type=refresh_token&refresh_token={urllib.parse.quote(refresh_token)}"),
        ("application/json",
         json.dumps({"grant_type": "refresh_token", "refresh_token": refresh_token})),
        ("application/json",
         json.dumps({"refresh_token": refresh_token})),
    ]

    for ct, body in formats:
        status, raw = http("POST", url, {"Content-Type": ct, "Accept": "application/json"}, body)
        if status == 200:
            try:
                data = json.loads(raw)
                tok = data.get("access_token") or data.get("accessToken") or data.get("token")
                if tok:
                    return tok
            except:
                pass
            # Maybe raw response IS the token
            raw_s = raw.decode("utf-8", errors="replace").strip().strip('"')
            if len(raw_s) > 30 and " " not in raw_s[:30]:
                return raw_s

    print("  ERROR: Could not exchange refresh token for access token.")
    return None


def extract_lists(data):
    """Extract any array-like results from an API response."""
    if not data:
        return []
    if isinstance(data, list):
        return [("root", data)]
    if isinstance(data, dict):
        found = []
        for key, val in data.items():
            if isinstance(val, list) and len(val) > 0:
                found.append((key, val))
        return found
    return []


def try_endpoint(method, endpoint, token, body=None):
    """Hit an endpoint, return (status, parsed_json, response_time_ms)."""
    url = f"{BASE}{endpoint}"
    hdrs = {"AuthorizationToken": token, "Accept": "application/json"}
    t0 = time.time()
    status, raw = http(method, url, hdrs, body)
    ms = int((time.time() - t0) * 1000)
    try:
        data = json.loads(raw)
    except:
        data = None
    return status, data, ms


def search_all_endpoints(term, token):
    """Fire the search term at every known endpoint format. Return all hits."""
    enc = urllib.parse.quote(term)
    hits = []

    endpoints = [
        # GET search variants
        ("GET",  f"/v1/search/system/level/customer?searchText={enc}&limit=100"),
        ("GET",  f"/v2/search/system/level/customer?searchText={enc}&limit=100"),
        ("GET",  f"/v3/search/system?searchText={enc}&limit=100"),
        ("GET",  f"/v1/search/system/level/watchlist?searchText={enc}&limit=100"),
        ("GET",  f"/v1/search/system/level/site?searchText={enc}&limit=100"),
        ("GET",  f"/v1/search/system/level/group?searchText={enc}&limit=100"),
        # Aggregate / parent (returns customer IDs, not systems)
        ("GET",  f"/v3/search/aggregate?searchText={enc}&limit=100"),
        ("GET",  f"/v1/search/aggregate/level/customer?searchText={enc}&limit=100"),
        ("GET",  f"/v3/search/parent?searchText={enc}&limit=100"),
        ("GET",  f"/v1/search/parent/level/customer?searchText={enc}&limit=100"),
        ("GET",  f"/v3/search/location?searchText={enc}&limit=100"),
        # Count endpoints
        ("GET",  f"/v3/search/count/aggregate?searchText={enc}"),
        ("GET",  f"/v3/search/count/parent?searchText={enc}"),
        # Cluster view (if term is a serial number)
        ("GET",  f"/v1/clusterview/get-cluster-summary/{enc}"),
        # Health by search
        ("GET",  f"/v1/health/summary/level/customer?searchText={enc}&limit=100"),
        # Capacity by search
        ("GET",  f"/v2/capacity/summary/level/customer?searchText={enc}&limit=100"),
    ]

    # POST search variants (some APIs require POST)
    post_endpoints = [
        ("POST", "/v1/search/system/level/customer",  {"searchText": term, "limit": 100}),
        ("POST", "/v3/search/system",                  {"searchText": term, "limit": 100}),
        ("POST", "/v3/search/aggregate",               {"searchText": term, "limit": 100}),
        ("POST", "/v1/search/aggregate/level/customer", {"searchText": term, "limit": 100}),
        ("POST", "/v3/search/parent",                  {"searchText": term, "limit": 100}),
    ]

    total = len(endpoints) + len(post_endpoints)
    idx = 0

    for method, ep in endpoints:
        idx += 1
        sys.stdout.write(f"\r  Probing {idx}/{total}...")
        sys.stdout.flush()
        status, data, ms = try_endpoint(method, ep, token)
        lists = extract_lists(data)
        for key, arr in lists:
            if len(arr) > 0:
                hits.append({
                    "endpoint": f"{method} {ep[:80]}",
                    "status": status, "ms": ms,
                    "key": key, "count": len(arr),
                    "records": arr,
                    "preview": json.dumps(arr[0], default=str)[:200] if arr else "",
                })

    for method, ep, body in post_endpoints:
        idx += 1
        sys.stdout.write(f"\r  Probing {idx}/{total}...")
        sys.stdout.flush()
        status, data, ms = try_endpoint(method, ep, token, body)
        lists = extract_lists(data)
        for key, arr in lists:
            if len(arr) > 0:
                hits.append({
                    "endpoint": f"{method} {ep[:80]}",
                    "status": status, "ms": ms,
                    "key": key, "count": len(arr),
                    "records": arr,
                    "preview": json.dumps(arr[0], default=str)[:200] if arr else "",
                })

    print(f"\r  Probed {total} endpoints.{' ' * 20}")
    return hits


def try_breadth_endpoints(token):
    """Try endpoints that return data without any search term."""
    print("\n  Trying breadth endpoints (no search term needed)...")
    breadth = [
        ("GET", "/watchlist/all"),
        ("GET", "/v2/watchlist/all"),
        ("GET", "/eos/details"),
        ("GET", "/eos/contracts/details"),
        ("GET", "/v2/health/risks"),
        ("GET", "/capacity2/usage"),
        ("GET", "/firmware/details"),
        ("GET", "/keystone/customers"),
        ("GET", "/v1/api/registration"),
        ("GET", "/v1/api/catalogSubscription"),
    ]

    hits = []
    for i, (method, ep) in enumerate(breadth):
        sys.stdout.write(f"\r  Probing breadth {i+1}/{len(breadth)}...")
        sys.stdout.flush()
        status, data, ms = try_endpoint(method, ep, token)
        lists = extract_lists(data)
        for key, arr in lists:
            if len(arr) > 0:
                hits.append({
                    "endpoint": f"{method} {ep}",
                    "status": status, "ms": ms,
                    "key": key, "count": len(arr),
                    "records": arr,
                    "preview": json.dumps(arr[0], default=str)[:200] if arr else "",
                })
        # Also show non-array results with content
        if data and isinstance(data, dict) and len(data) > 0:
            raw_s = json.dumps(data, default=str)
            if raw_s not in ["{}", "[]"]:
                hits.append({
                    "endpoint": f"{method} {ep}",
                    "status": status, "ms": ms,
                    "key": "(object)", "count": len(data),
                    "records": [data],
                    "preview": raw_s[:200],
                })

    print(f"\r  Probed {len(breadth)} breadth endpoints.{' ' * 20}")
    return hits


def display_hits(hits, label="Results"):
    """Show results and let user choose."""
    if not hits:
        print(f"\n  {label}: No data returned from any endpoint.")
        return None

    print(f"\n  {label}: {len(hits)} endpoints returned data:\n")
    for i, h in enumerate(hits, 1):
        print(f"    {i:2}. [{h['status']}] {h['endpoint']}")
        print(f"        Key: \"{h['key']}\"  |  Records: {h['count']}  |  {h['ms']}ms")
        print(f"        Preview: {h['preview'][:150]}")
        print()

    return hits


def main():
    print("=" * 72)
    print("  NetApp Active IQ - Interactive Discovery")
    print("  Type a customer name, serial number, or search term.")
    print("  We'll try EVERY API endpoint and show you what returns data.")
    print("=" * 72)

    # Get refresh token
    refresh_token = None

    # Try reading from environment or file
    for cp in [SCRIPT_DIR / "aiq_config.json",
               Path.home() / "NetApp AIQ Advisor" / "aiq_config.json"]:
        if cp.exists():
            try:
                cfg = json.loads(cp.read_text(encoding="utf-8"))
                refresh_token = cfg.get("refreshToken") or cfg.get("refresh_token")
                if refresh_token:
                    print(f"\n  Token loaded from: {cp}")
                    break
            except:
                pass

    if not refresh_token:
        print("\n  Enter your Active IQ API Refresh Token:")
        print("  (Get it from activeiq.netapp.com -> Quick Links -> API Services)")
        refresh_token = input("\n  Token: ").strip()
        if not refresh_token:
            print("  No token provided. Exiting.")
            return

        # Save for next time
        cfg_path = SCRIPT_DIR / "aiq_config.json"
        cfg_path.write_text(json.dumps({"refreshToken": refresh_token}, indent=2), encoding="utf-8")
        print(f"  Token saved to: {cfg_path}")

    # Exchange for access token
    print("\n  Authenticating...")
    access_token = get_access_token(refresh_token)
    if not access_token:
        print("  Authentication failed. Check your refresh token.")
        return

    print(f"  Authenticated! Token: {access_token[:30]}...")

    # First, try breadth endpoints (no search needed)
    print("\n" + "-" * 72)
    breadth_hits = try_breadth_endpoints(access_token)
    if breadth_hits:
        display_hits(breadth_hits, "Breadth Endpoints")

    # Interactive search loop
    all_systems = []
    while True:
        print("\n" + "-" * 72)
        term = input("  Search term (or 'quit' to save & exit): ").strip()
        if not term or term.lower() in ["quit", "exit", "q"]:
            break

        print(f"\n  Searching for: \"{term}\"")
        hits = search_all_endpoints(term, access_token)

        if not hits:
            print("\n  No results. Try a different term.")
            print("  Tips: try partial names, serial numbers, or site names.")
            continue

        display_hits(hits, f"Results for \"{term}\"")

        # Ask user which results to keep
        print("  Enter numbers to keep (comma-separated), 'all', or 'skip':")
        choice = input("  Keep: ").strip().lower()

        if choice == "skip":
            continue
        elif choice == "all":
            for h in hits:
                all_systems.extend(h["records"])
        else:
            try:
                nums = [int(x.strip()) for x in choice.split(",")]
                for n in nums:
                    if 1 <= n <= len(hits):
                        all_systems.extend(hits[n - 1]["records"])
                        print(f"    Added {hits[n-1]['count']} records from option {n}")
            except ValueError:
                print("    Invalid input, skipping.")

        print(f"\n  Total collected systems: {len(all_systems)}")

    # Save results
    if all_systems:
        # Deduplicate
        seen = set()
        unique = []
        for s in all_systems:
            sn = str(s.get("serialNumber") or s.get("serial_number") or
                     s.get("systemSerialNumber") or s.get("id") or "").strip()
            key = sn or json.dumps(s, sort_keys=True, default=str)[:100]
            if key not in seen:
                seen.add(key)
                unique.append(s)

        result = {
            "discovery_timestamp": datetime.now().isoformat(),
            "total_systems": len(unique),
            "systems": unique,
        }
        OUTPUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(f"\n  Saved {len(unique)} systems to: {OUTPUT}")
        print(f"  Import this file into the AIQ Advisor app via Settings -> Import Config.")
    else:
        print("\n  No systems collected.")

    # Also save the breadth results for analysis
    if breadth_hits:
        report_path = SCRIPT_DIR / "aiq_breadth_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            simplified = [{
                "endpoint": h["endpoint"], "status": h["status"],
                "key": h["key"], "count": h["count"],
                "preview": h["preview"]
            } for h in breadth_hits]
            json.dump(simplified, f, indent=2, default=str)
        print(f"  Breadth report: {report_path}")

    print("\n  Done.")


if __name__ == "__main__":
    main()
