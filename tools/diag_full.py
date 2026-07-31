"""
Test the EXACT server queries in full, identify which specific sub-field or 
argument is causing the 0-result response, and also probe the corp-network 
GQL URL to understand dual-environment requirements.
"""
import json, ssl, urllib.request, urllib.error, os, sys

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "aiq_config.json")
GQL_EXT   = "https://gql.aiq.netapp.com/graphql"
REST_BASE = "https://api.activeiq.netapp.com"

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

st, tr = _post(f"{REST_BASE}/v1/tokens/accessToken", {"refresh_token": cfg["refreshToken"]})
token = tr.get("access_token", "")
H = {"Authorization": f"Bearer {token}"}
print(f"Token OK (len={len(token)})\n")

def gql(q, label, url=GQL_EXT):
    st, r = _post(url, {"query": q}, H)
    errs = r.get("errors") or []
    d = r.get("data") or {}
    sys_data = d.get("systems") or {}
    count = len(sys_data.get("systems") or []) if isinstance(sys_data, dict) else 0
    total = sys_data.get("totalCount", "?") if isinstance(sys_data, dict) else "?"
    print(f"[{label}] HTTP {st}  totalCount={total}  returned={count}", end="")
    if errs:
        print(f"  ERR: {errs[0].get('message','')[:120]}")
    else:
        print()
    return st, r

# ── EXACT MINIMAL FIELDS from server.py ───────────────────────────────────────
MINIMAL = """
  hostName systemId serialNumber osVersion recommendedOSVersion
  type platformType ageInYears serviceTier incumbentResellerCompany
  customer { id name }
  site { id name city countryCode postalCode state }
  hardwareModel { name endOfAvailability endOfSupport }
  contactPerson { firstName lastName phone email }
  contract {
    softwareContractStartDate hardwareContractStartDate
    expiryDate softwareContractEndDate hardwareContractEndDate
    overallContractEndDate isContractActive
    hardwareServiceLevel hardwareWarrantyEndDate
  }
  latestAsup { asupId generatedDate receivedDate subject type isManual }
  latestAsupOfEachType { asupId generatedDate receivedDate subject type isManual }
  autoSupports { asupId generatedDate receivedDate subject type isManual }"""

print("=== EXACT MINIMAL (pageSize:1) ===")
gql(f"{{ systems(pageSize: 1) {{ totalCount cursor systems {{ {MINIMAL} }} }} }}", "minimal-exact")

# ── EXACT TAM FIELDS from server.py ───────────────────────────────────────────
TAM = """
  hostName systemId serialNumber osVersion recommendedOSVersion
  type platformType productType ageInYears serviceTier
  techRefreshStatus incumbentResellerCompany
  isFabricPool hasPvr
  customer { id name }
  site { id name city countryCode postalCode state }
  nagp { id name }
  hardwareModel { name modelRevision endOfAvailability endOfSupport }
  contactPerson { firstName lastName phone email }
  salesRepresentative { name emailAddress managerEmailAddress }
  csm { name emailAddress }
  sam { name emailAddress }
  gard { worldwide geo area region district territory }
  authorizedSupportPartner { name endDate }
  domesticParent { id name }
  contract {
    softwareContractId hardwareContractId
    softwareContractStartDate hardwareContractStartDate
    expiryDate softwareContractEndDate hardwareContractEndDate
    nrdContractEndDate overallContractEndDate isContractActive
    hardwareServiceLevel hardwareWarrantyEndDate hardwareWarrantyStartDate
  }
  autoSupportConfig { autoSupportStatus isAutoSupportOnDemandEnabled isAutoSupportOnDemandCapable autoSupportTransport systemDomain }
  latestAsup { asupId generatedDate receivedDate subject type isManual }
  latestAsupOfEachType { asupId generatedDate receivedDate subject type isManual }
  autoSupports { asupId generatedDate receivedDate subject type isManual }
  ... on ONTAPSystem {
    isMetroCluster isAllFlashOptimized operatingMode
    propensityCategory serviceProcessorIPAddress
    isARPEnabled autoUpdateEnabled nextBestAction
    lifecycleEvents { workflowCategory typeCode typeName criticalityCode daysToEvent talkingPoint }
    swRecommendationDetails { minRecommendedVersion latestRecommendedVersion }
    systemFirmware { type currentVersion recommendedVersion }
    capacity {
      physical { rawMarketingKiB usedKiB usedWithoutSnapshotsKiB usablePerformanceTierKiB qoqUtilizationPercentage yoyUtilizationPercentage utilizationPercentage }
      logical { usedKiB usedWithoutSnapshotsClonesKiB }
      efficiency {
        ratio { efficiencyRatio dataReductionRatio withSnapshotRatio }
        saved { savedKiB deDuplicationSavedKiB compactionSavedKiB }
      }
      reportedOn
    }
    monthlyCapacity {
      month
      physical { rawMarketingKiB usedKiB utilizationPercentage qoqUtilizationPercentage }
      logical { usedKiB }
      efficiency { ratio { efficiencyRatio dataReductionRatio } }
    }
  }"""

print("\n=== EXACT TAM (pageSize:1) ===")
st1, r1 = gql(f"{{ systems(pageSize: 1) {{ totalCount cursor systems {{ {TAM} }} }} }}", "tam-exact")

# If TAM fails, bisect the problem
if (r1.get("errors") or []):
    print("\n=== BISECT: TAM without ONTAP fragment ===")
    TAM_NO_ONTAP = TAM[:TAM.find("... on ONTAPSystem")]
    gql(f"{{ systems(pageSize: 1) {{ totalCount systems {{ {TAM_NO_ONTAP} }} }} }}", "tam-no-ontap")

    print("\n=== BISECT: ONTAP fragment only ===")
    gql("""{ systems(pageSize: 1) { totalCount systems { serialNumber ... on ONTAPSystem {
      isMetroCluster isAllFlashOptimized operatingMode propensityCategory serviceProcessorIPAddress
      isARPEnabled autoUpdateEnabled nextBestAction
      lifecycleEvents { workflowCategory typeCode typeName criticalityCode daysToEvent talkingPoint }
      swRecommendationDetails { minRecommendedVersion latestRecommendedVersion }
      systemFirmware { type currentVersion recommendedVersion }
      capacity {
        physical { rawMarketingKiB usedKiB usedWithoutSnapshotsKiB usablePerformanceTierKiB qoqUtilizationPercentage yoyUtilizationPercentage utilizationPercentage }
        logical { usedKiB usedWithoutSnapshotsClonesKiB }
        efficiency { ratio { efficiencyRatio dataReductionRatio withSnapshotRatio } saved { savedKiB deDuplicationSavedKiB compactionSavedKiB } }
        reportedOn
      }
    } } } }""", "ontap-only")

# ── CORP NETWORK URL probe ─────────────────────────────────────────────────────
print("\n=== CORP NETWORK URL CANDIDATES ===")
corp_urls = [
    "https://gql.aiq.netapp.com/graphql",           # external (current)
    "https://aiq.netapp.com/graphql",               # corp root
    "https://api.activeiq.netapp.com/graphql",      # REST base + /graphql
    "https://activeiq.netapp.com/graphql",          # portal base
]
simple_q = "{ systems(pageSize: 1) { totalCount } }"
for url in corp_urls:
    try:
        st2, r2 = _post(url, {"query": simple_q}, H)
        d = r2.get("data") or {}
        tc = (d.get("systems") or {}).get("totalCount", "no systems key")
        errs = r2.get("errors") or []
        print(f"  {url}: HTTP {st2}  totalCount={tc}", end="")
        if errs:
            print(f"  ERR: {errs[0].get('message','')[:80]}")
        else:
            print(" ✓")
    except Exception as ex:
        print(f"  {url}: EXCEPTION {str(ex)[:80]}")
