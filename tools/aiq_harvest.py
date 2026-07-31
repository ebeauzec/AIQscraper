"""
AIQ System Harvester
=====================
Uses the working endpoint: /v1/clusterview/get-cluster-summary/{serial}
Queries all known serials, extracts nodes, discovers more serials, repeats.
Also tries companyId-based lookups.
"""
import io, sys, json, ssl, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import urllib.request, urllib.error, urllib.parse
from pathlib import Path
from datetime import datetime

BASE = "https://api.activeiq.netapp.com"
SCRIPT_DIR = Path(__file__).parent
OUTPUT = SCRIPT_DIR / "aiq_harvested_systems.json"

# All known serials
SEED_SERIALS = ["211839000195", "952239002356", "952239002659", "952239002236", "952239002406"]
COMPANY_ID = "2372648"  # From user2/info


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
        with urllib.request.urlopen(req, timeout=45, context=ssl.create_default_context()) as r:
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
                d = json.loads(raw)
                t = d.get("access_token") or d.get("accessToken") or d.get("token")
                if t: return t
            except: pass
            raw_s = raw.decode("utf-8", errors="replace").strip().strip('"')
            if len(raw_s) > 30: return raw_s
    return None


def api_get(endpoint, token):
    """GET an API endpoint, return parsed JSON or None."""
    url = f"{BASE}{endpoint}"
    hdrs = {"AuthorizationToken": token, "Accept": "application/json"}
    status, raw = http("GET", url, hdrs)
    if status == 200:
        try:
            return json.loads(raw)
        except:
            pass
    return None


def extract_serials(data, depth=0):
    """Recursively find anything that looks like a serial number in nested data."""
    serials = set()
    if isinstance(data, dict):
        for key, val in data.items():
            k_lower = key.lower()
            if any(s in k_lower for s in ["serial", "sn", "system_id", "node_id"]):
                if isinstance(val, str) and len(val) >= 8 and val.replace("-","").isalnum():
                    serials.add(val)
                elif isinstance(val, list):
                    for v in val:
                        if isinstance(v, str) and len(v) >= 8:
                            serials.add(v)
            if depth < 5:
                serials |= extract_serials(val, depth + 1)
    elif isinstance(data, list):
        for item in data:
            if depth < 5:
                serials |= extract_serials(item, depth + 1)
    return serials


def main():
    print("=" * 65)
    print("  AIQ System Harvester")
    print("  Using /v1/clusterview/get-cluster-summary/{serial}")
    print("=" * 65)

    cfg_path = SCRIPT_DIR / "aiq_config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    refresh_token = cfg.get("refreshToken") or cfg.get("refresh_token")

    print("\n  Getting access token...")
    token = get_access_token(refresh_token)
    if not token:
        print("  FAILED."); return
    print(f"  OK: {token[:40]}...")

    # ── Phase 1: Try partner/company-level endpoints ──
    print("\n--- Phase 1: Company/Partner discovery (companyId={}) ---".format(COMPANY_ID))
    partner_endpoints = [
        f"/v1/search/system/level/customer?id={COMPANY_ID}&limit=500",
        f"/v2/search/system/level/customer?id={COMPANY_ID}&limit=500",
        f"/v1/health/summary/level/customer/id/{COMPANY_ID}",
        f"/v1/health/details/level/customer/id/{COMPANY_ID}",
        f"/v1/clusterview/get-clusters-by-customer/{COMPANY_ID}",
        f"/v1/clusterview/customer/{COMPANY_ID}",
        f"/v1/customer/{COMPANY_ID}/systems",
        f"/v1/customer/systems?customerId={COMPANY_ID}",
        f"/v1/systems/customer/{COMPANY_ID}",
        f"/v1/search/system?customerId={COMPANY_ID}&limit=500",
    ]
    for ep in partner_endpoints:
        data = api_get(ep, token)
        if data:
            raw_s = json.dumps(data, default=str)
            is_empty = raw_s.strip() in ["{}", "[]"]
            has_msg = "Unsupported" in raw_s or "not found" in raw_s.lower()
            if not is_empty and not has_msg:
                print(f"  ** HIT ** {ep}")
                print(f"            {raw_s[:300]}")
            else:
                print(f"  [skip]    {ep[:60]}  ({raw_s[:60]})")
        else:
            print(f"  [fail]    {ep[:60]}")

    # ── Phase 2: Cluster view for all known serials ──
    print("\n--- Phase 2: Cluster view for all {} known serials ---".format(len(SEED_SERIALS)))
    all_clusters = {}
    all_nodes = []
    discovered_serials = set()

    for sn in SEED_SERIALS:
        print(f"\n  Serial: {sn}")
        data = api_get(f"/v1/clusterview/get-cluster-summary/{sn}", token)
        if not data:
            print(f"    No data")
            continue

        raw_s = json.dumps(data, default=str)
        print(f"    Response size: {len(raw_s)} bytes")

        # Extract cluster info
        cluster_data = data.get("data", [data])
        if not isinstance(cluster_data, list):
            cluster_data = [cluster_data]

        for cluster in cluster_data:
            cname = cluster.get("cluster_name") or cluster.get("clusterName") or "unknown"
            print(f"    Cluster: {cname}")

            # Print key fields
            for field in ["cluster_mgmt_ip_address", "raw_capacity_tib",
                          "usable_capacity_tib", "used_capacity_tib",
                          "available_capacity_tib", "node_storage_vm_count",
                          "data_storage_vm_count", "os_version", "ontap_version"]:
                if field in cluster:
                    print(f"      {field}: {cluster[field]}")

            # Look for nodes
            nodes = cluster.get("nodes") or cluster.get("nodeList") or cluster.get("node_details") or []
            if isinstance(nodes, list):
                print(f"    Nodes: {len(nodes)}")
                for node in nodes:
                    if isinstance(node, dict):
                        nsn = node.get("serial_number") or node.get("serialNumber") or ""
                        nname = node.get("node_name") or node.get("nodeName") or ""
                        model = node.get("model") or node.get("platform") or ""
                        print(f"      - {nname}  SN:{nsn}  Model:{model}")
                        if nsn:
                            discovered_serials.add(nsn)
                        all_nodes.append(node)

            all_clusters[sn] = data

        # Find any serial numbers embedded in the response
        found = extract_serials(data)
        if found:
            new = found - set(SEED_SERIALS) - discovered_serials
            discovered_serials |= found
            if new:
                print(f"    Discovered {len(new)} new serials: {list(new)[:10]}")

    # ── Phase 3: Query discovered serials ──
    new_serials = discovered_serials - set(SEED_SERIALS)
    if new_serials:
        print(f"\n--- Phase 3: Querying {len(new_serials)} discovered serials ---")
        for sn in list(new_serials)[:20]:  # Cap at 20 to avoid rate limiting
            print(f"  Serial: {sn}")
            data = api_get(f"/v1/clusterview/get-cluster-summary/{sn}", token)
            if data:
                raw_s = json.dumps(data, default=str)
                if "not found" not in raw_s.lower() and raw_s.strip() != "{}":
                    print(f"    ** DATA ** ({len(raw_s)} bytes)")
                    all_clusters[sn] = data
                    # Extract more serials
                    more = extract_serials(data)
                    discovered_serials |= more
                else:
                    print(f"    Not found")
            else:
                print(f"    No response")
            time.sleep(0.5)  # Be gentle

    # ── Phase 4: Try other clusterview endpoints ──
    print(f"\n--- Phase 4: Other cluster view endpoints ---")
    other_endpoints = [
        "/v1/clusterview/get-cluster-list",
        "/v1/clusterview/clusters",
        "/v1/clusterview/all",
        "/v1/clusterview/summary",
    ]
    for ep in other_endpoints:
        data = api_get(ep, token)
        if data:
            raw_s = json.dumps(data, default=str)
            if raw_s.strip() not in ["{}", "[]"] and "Unsupported" not in raw_s:
                print(f"  ** HIT ** {ep}")
                print(f"            {raw_s[:300]}")
            else:
                print(f"  [empty]   {ep}")
        else:
            print(f"  [fail]    {ep}")

    # ── Phase 5: Try interop/capacity/performance endpoints with known serials ──
    print(f"\n--- Phase 5: Detail endpoints for first serial ---")
    sn = SEED_SERIALS[0]
    detail_eps = [
        f"/v1/clusterview/get-node-details/{sn}",
        f"/v1/clusterview/get-svm-details/{sn}",
        f"/v1/clusterview/get-aggregate-details/{sn}",
        f"/v1/clusterview/get-volume-details/{sn}",
        f"/v1/capacity/details/{sn}",
        f"/v1/performance/summary/{sn}",
        f"/v1/interop/details/{sn}",
        f"/v1/firmware/details/{sn}",
        f"/v1/eos/details/{sn}",
    ]
    for ep in detail_eps:
        data = api_get(ep, token)
        if data:
            raw_s = json.dumps(data, default=str)
            if raw_s.strip() not in ["{}", "[]"] and "Unsupported" not in raw_s and "not found" not in raw_s.lower():
                print(f"  ** HIT ** {ep}")
                print(f"            {raw_s[:300]}")
            else:
                print(f"  [empty]   {ep[:60]}  {raw_s[:60]}")
        else:
            print(f"  [fail]    {ep[:60]}")

    # ── Save everything ──
    print(f"\n--- Results ---")
    print(f"  Clusters queried:     {len(all_clusters)}")
    print(f"  Nodes found:          {len(all_nodes)}")
    print(f"  Total serials known:  {len(discovered_serials)}")
    print(f"  All serials:          {sorted(discovered_serials)}")

    result = {
        "harvest_timestamp": datetime.now().isoformat(),
        "user": {"id": "MALCOLM.TILEY", "type": "RESELLER",
                 "company": "Sithabile Technology Services", "companyId": COMPANY_ID},
        "seed_serials": SEED_SERIALS,
        "discovered_serials": sorted(discovered_serials),
        "total_clusters": len(all_clusters),
        "total_nodes": len(all_nodes),
        "clusters": all_clusters,
        "nodes": all_nodes,
    }

    OUTPUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"\n  Saved to: {OUTPUT}")
    print(f"  Done!")


if __name__ == "__main__":
    main()
