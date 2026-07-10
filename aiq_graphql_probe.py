"""
AIQ GraphQL Probe
==================
Tests the REAL Active IQ API at gql.aiq.netapp.com/graphql
Uses Authorization: Bearer <token> (NOT AuthorizationToken!)
"""
import io, sys, json, ssl
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import urllib.request, urllib.error, urllib.parse
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
REST_BASE = "https://api.activeiq.netapp.com"
GQL_URL = "https://gql.aiq.netapp.com/graphql"


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
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=45, context=ctx) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, str(e).encode("utf-8")


def get_access_token(refresh_token):
    body = json.dumps({"refresh_token": refresh_token})
    status, raw = http("POST", f"{REST_BASE}/v1/tokens/accessToken",
                       {"Content-Type": "application/json",
                        "Accept": "application/json"}, body)
    if status == 200:
        raw_s = raw.decode("utf-8", errors="replace").strip()
        try:
            d = json.loads(raw_s)
            return d.get("access_token") or d.get("accessToken") or d.get("token")
        except:
            raw_s = raw_s.strip('"')
            if len(raw_s) > 30:
                return raw_s
    print(f"  Token exchange failed: [{status}] {raw.decode('utf-8', errors='replace')[:200]}")
    return None


def gql(token, query, variables=None):
    """Execute a GraphQL query against the AIQ GraphQL endpoint."""
    body = {"query": query}
    if variables:
        body["variables"] = variables
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    status, raw = http("POST", GQL_URL, headers, body)
    raw_s = raw.decode("utf-8", errors="replace")
    return status, raw_s


def main():
    print("=" * 65)
    print("  AIQ GraphQL Probe")
    print("  Endpoint: gql.aiq.netapp.com/graphql")
    print("=" * 65)

    cfg = json.loads((SCRIPT_DIR / "aiq_config.json").read_text(encoding="utf-8"))
    refresh_token = cfg.get("refreshToken") or cfg.get("refresh_token")

    print("\n  Getting access token...")
    token = get_access_token(refresh_token)
    if not token:
        print("  FAILED to get access token"); return
    print(f"  OK: {token[:50]}...")

    # ── 1. Introspection: discover available queries ──
    print("\n--- 1. Schema Introspection (root query types) ---")
    status, resp = gql(token, """
    {
      __schema {
        queryType {
          fields {
            name
            description
          }
        }
      }
    }
    """)
    print(f"  [{status}]")
    if status == 200:
        try:
            data = json.loads(resp)
            fields = data.get("data", {}).get("__schema", {}).get("queryType", {}).get("fields", [])
            print(f"  Available queries ({len(fields)}):")
            for f in fields:
                print(f"    - {f['name']}: {(f.get('description') or '')[:80]}")
        except Exception as e:
            print(f"  Parse error: {e}")
            print(f"  Raw: {resp[:500]}")
    else:
        print(f"  Response: {resp[:500]}")

    # ── 2. Systems query (basic) ──
    print("\n--- 2. Systems (first 5) ---")
    status, resp = gql(token, """
    query {
      systems(first: 5) {
        totalCount
        items {
          serialNumber
          systemName
          systemType
          model
          osVersion
          customerName
          siteName
          ... on ONTAPSystem {
            clusterName
            clusterSerialNumber
            platform
            isAllFlash
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """)
    print(f"  [{status}]")
    if status == 200:
        try:
            data = json.loads(resp)
            if data.get("errors"):
                print(f"  Errors: {json.dumps(data['errors'], indent=2)[:500]}")
            items = data.get("data", {}).get("systems", {})
            print(f"  Total count: {items.get('totalCount', '?')}")
            for s in (items.get("items") or [])[:5]:
                print(f"    - {s.get('systemName', '?')} | SN:{s.get('serialNumber', '?')} | {s.get('model', '?')} | {s.get('osVersion', '?')}")
        except Exception as e:
            print(f"  Parse error: {e}")
            print(f"  Raw: {resp[:500]}")
    else:
        print(f"  Response: {resp[:500]}")

    # ── 3. Clusters query ──
    print("\n--- 3. Clusters (first 5) ---")
    status, resp = gql(token, """
    query {
      clusters(first: 5) {
        totalCount
        items {
          clusterName
          clusterSerialNumber
          managementIp
          ontapVersion
          nodeCount
          totalCapacityBytes
          usedCapacityBytes
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """)
    print(f"  [{status}]")
    if status == 200:
        try:
            data = json.loads(resp)
            if data.get("errors"):
                print(f"  Errors: {json.dumps(data['errors'], indent=2)[:500]}")
            items = data.get("data", {}).get("clusters", {})
            print(f"  Total clusters: {items.get('totalCount', '?')}")
            for c in (items.get("items") or [])[:5]:
                print(f"    - {c.get('clusterName', '?')} | Nodes:{c.get('nodeCount', '?')} | ONTAP:{c.get('ontapVersion', '?')}")
        except Exception as e:
            print(f"  Parse error: {e}")
            print(f"  Raw: {resp[:500]}")
    else:
        print(f"  Response: {resp[:500]}")

    # ── 4. Customers query ──
    print("\n--- 4. Customers (first 10) ---")
    status, resp = gql(token, """
    query {
      customers(first: 10) {
        totalCount
        items {
          customerId
          customerName
        }
      }
    }
    """)
    print(f"  [{status}]")
    if status == 200:
        try:
            data = json.loads(resp)
            if data.get("errors"):
                print(f"  Errors: {json.dumps(data['errors'], indent=2)[:500]}")
            items = data.get("data", {}).get("customers", {})
            print(f"  Total customers: {items.get('totalCount', '?')}")
            for c in (items.get("items") or [])[:10]:
                print(f"    - [{c.get('customerId', '?')}] {c.get('customerName', '?')}")
        except Exception as e:
            print(f"  Parse error: {e}")
            print(f"  Raw: {resp[:500]}")
    else:
        print(f"  Response: {resp[:500]}")

    # ── 5. Risks query ──
    print("\n--- 5. Risks (first 5) ---")
    status, resp = gql(token, """
    query {
      risks(first: 5) {
        totalCount
        items {
          riskId
          severity
          category
          description
          systemSerialNumber
          systemName
        }
      }
    }
    """)
    print(f"  [{status}]")
    if status == 200:
        try:
            data = json.loads(resp)
            if data.get("errors"):
                print(f"  Errors: {json.dumps(data['errors'], indent=2)[:500]}")
            items = data.get("data", {}).get("risks", {})
            print(f"  Total risks: {items.get('totalCount', '?')}")
            for r in (items.get("items") or [])[:5]:
                print(f"    - [{r.get('severity', '?')}] {r.get('category', '?')}: {(r.get('description') or '')[:80]}")
        except Exception as e:
            print(f"  Parse error: {e}")
            print(f"  Raw: {resp[:500]}")
    else:
        print(f"  Response: {resp[:500]}")

    # ── 6. Summary query ──
    print("\n--- 6. Summary ---")
    status, resp = gql(token, """
    query {
      summary {
        totalSystems
        totalClusters
        totalRisks
        totalCustomers
        totalSites
      }
    }
    """)
    print(f"  [{status}]")
    if status == 200:
        try:
            data = json.loads(resp)
            if data.get("errors"):
                print(f"  Errors: {json.dumps(data['errors'], indent=2)[:500]}")
            s = data.get("data", {}).get("summary", {})
            for k, v in (s or {}).items():
                print(f"    {k}: {v}")
        except Exception as e:
            print(f"  Parse error: {e}")
            print(f"  Raw: {resp[:500]}")
    else:
        print(f"  Response: {resp[:500]}")

    # Save raw response for analysis
    print(f"\n  Done!")


if __name__ == "__main__":
    main()
