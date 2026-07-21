"""
Probe AutoSupport type fields and test sub-field validity.
Also test what minimal query actually works end-to-end.
"""
import json, ssl, urllib.request, urllib.error, os

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "aiq_config.json")
GQL_URL = "https://gql.aiq.netapp.com/graphql"

with open(CONFIG_FILE, encoding="utf-8") as f:
    cfg = json.load(f)

ctx = ssl.create_default_context()

def _post(url, body, headers=None):
    h = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

st, tr = _post("https://api.activeiq.netapp.com/v1/tokens/accessToken",
               {"refresh_token": cfg["refreshToken"]})
token = tr.get("access_token", "")
H = {"Authorization": f"Bearer {token}"}

def gql(q, label=""):
    st, r = _post(GQL_URL, {"query": q}, H)
    errs = r.get("errors") or []
    if label:
        print(f"\n[{label}] HTTP {st}")
        if errs:
            for e in errs:
                print(f"  ERROR: {e.get('message','')[:200]}")
    return st, r

# Probe types
for tname in ["AutoSupport", "SystemContract", "Nagp", "HardwareModel", "ContactPerson",
              "Customer", "Site", "SystemContactPerson", "Asp", "DomesticParent",
              "SystemHardwareCapabilities", "EndOfSupport", "SalesTerritoryHierarchy"]:
    st2, r2 = gql(f'{{ __type(name: "{tname}") {{ fields {{ name }} }} }}', tname)
    if st2 == 200:
        fields = [f["name"] for f in ((r2.get("data") or {}).get("__type") or {}).get("fields") or []]
        print(f"  {tname}: {', '.join(fields) if fields else 'NOT FOUND'}")

# Test minimal safe query
print("\n\n=== SAFE MINIMAL QUERY ===")
gql("""{ systems(pageSize: 3) { totalCount systems {
  hostName systemId serialNumber osVersion type platformType ageInYears
  customer { id name }
  site { id name city countryCode }
  hardwareModel { name endOfSupport }
} } }""", "minimal-safe")

# Test with latestAsup
print("\n=== WITH latestAsup ===")
gql("""{ systems(pageSize: 3) { totalCount systems {
  serialNumber
  latestAsup { asupId generatedDate receivedDate subject type }
} } }""", "latestAsup")

# Test autoSupports (which is a list)
print("\n=== WITH autoSupports ===")
gql("""{ systems(pageSize: 1) { systems {
  serialNumber
  autoSupports { asupId subject }
} } }""", "autoSupports")

# Test contract fields
print("\n=== CONTRACT FIELDS ===")
gql("""{ systems(pageSize: 1) { systems {
  serialNumber
  contract { expiryDate isContractActive hardwareServiceLevel }
} } }""", "contract")

# Test TAM-specific fields
print("\n=== TAM FIELDS ===")
gql("""{ systems(pageSize: 1) { systems {
  serialNumber
  nagp { id name }
  salesRepresentative { name emailAddress }
  csm { name emailAddress }
  sam { name emailAddress }
  gard { worldwide geo area region district territory }
  authorizedSupportPartner { name endDate }
  domesticParent { id name }
} } }""", "tam-fields")

# Test ONTAP inline fragment
print("\n=== ONTAP INLINE FRAGMENT ===")
gql("""{ systems(pageSize: 1) { systems {
  serialNumber
  ... on ONTAPSystem {
    isMetroCluster isAllFlashOptimized operatingMode
    capacity {
      physical { usedKiB utilizationPercentage rawMarketingKiB }
      logical { usedKiB }
      efficiency { ratio { efficiencyRatio } }
    }
  }
} } }""", "ontap-fragment")
