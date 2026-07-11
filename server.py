"""
AIQ Proxy Server with SQLite Cache Layer
=========================================
Drop-in replacement for server.py. Adds a persistent SQLite cache
(aiq_cache.db) so that subsequent page loads serve cached data instantly
while a background thread re-syncs from the AIQ GraphQL API.

Endpoints:
  GET /api/harvest         — returns cached data if available, triggers background sync
  GET /api/harvest?force=1 — bypasses cache, full re-harvest from API
  GET /api/sync-status     — returns sync metadata (last sync time, counts, is_syncing)
  GET /api/*               — proxy to api.activeiq.netapp.com
  POST /api/*              — proxy to api.activeiq.netapp.com
  POST /api/app/update     — git pull
"""

import http.server
import urllib.request
import urllib.error
import sys
import json
import ssl
import sqlite3
import threading
import time
from pathlib import Path
from datetime import datetime, timezone

PORT = 8080
SCRIPT_DIR = Path(__file__).parent
DB_PATH = SCRIPT_DIR / "aiq_cache.db"
CONFIG_PATH = SCRIPT_DIR / "aiq_config.json"
GQL_URL = "https://gql.aiq.netapp.com/graphql"
REST_BASE = "https://api.activeiq.netapp.com"

# Global sync state
_sync_lock = threading.Lock()
_is_syncing = False
_last_sync_error = None

# ─────────────────────────────────────────────────────────────────────
# SQLite Cache Layer
# ─────────────────────────────────────────────────────────────────────

def _init_db():
    """Create the SQLite database and tables if they don't exist."""
    db = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    db.execute("PRAGMA journal_mode=WAL")  # Better concurrent read/write
    db.execute("PRAGMA synchronous=NORMAL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS harvest_cache (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            result_json TEXT NOT NULL,
            harvested_at TEXT NOT NULL,
            duration_ms INTEGER DEFAULT 0,
            system_count INTEGER DEFAULT 0,
            cluster_count INTEGER DEFAULT 0,
            risk_count INTEGER DEFAULT 0,
            case_count INTEGER DEFAULT 0,
            risk_instance_count INTEGER DEFAULT 0
        );
    """)
    db.commit()
    return db


def _save_harvest(db, result, duration_ms=0):
    """Write the full harvest result to the cache."""
    now = datetime.now(timezone.utc).isoformat()
    result_json = json.dumps(result, default=str)
    db.execute("""
        INSERT OR REPLACE INTO harvest_cache
        (id, result_json, harvested_at, duration_ms, system_count, cluster_count,
         risk_count, case_count, risk_instance_count)
        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        result_json,
        now,
        duration_ms,
        result.get("totalSystems", 0),
        result.get("totalClusters", 0),
        result.get("totalRisks", 0),
        result.get("totalCases", 0),
        result.get("totalRiskInstances", result.get("riskInstances", 0)),
    ))
    db.commit()
    print(f"  [CACHE] Saved harvest to DB ({len(result_json)} bytes, {result.get('totalSystems', 0)} systems)", flush=True)


def _load_cached(db):
    """Load the cached harvest result from DB. Returns (result_dict, meta_dict) or (None, None)."""
    row = db.execute(
        "SELECT result_json, harvested_at, duration_ms, system_count, cluster_count, risk_count, case_count, risk_instance_count FROM harvest_cache WHERE id = 1"
    ).fetchone()
    if not row:
        return None, None
    result = json.loads(row[0])
    meta = {
        "harvested_at": row[1],
        "duration_ms": row[2],
        "system_count": row[3],
        "cluster_count": row[4],
        "risk_count": row[5],
        "case_count": row[6],
        "risk_instance_count": row[7],
    }
    return result, meta


def _get_sync_meta(db):
    """Return sync metadata for the /api/sync-status endpoint."""
    row = db.execute(
        "SELECT harvested_at, duration_ms, system_count, cluster_count, risk_count, case_count FROM harvest_cache WHERE id = 1"
    ).fetchone()
    if not row:
        return {
            "lastSync": None,
            "durationMs": 0,
            "systemCount": 0,
            "clusterCount": 0,
            "riskCount": 0,
            "caseCount": 0,
            "isSyncing": _is_syncing,
            "lastError": _last_sync_error,
        }
    return {
        "lastSync": row[0],
        "durationMs": row[1],
        "systemCount": row[2],
        "clusterCount": row[3],
        "riskCount": row[4],
        "caseCount": row[5],
        "isSyncing": _is_syncing,
        "lastError": _last_sync_error,
    }


# ─────────────────────────────────────────────────────────────────────
# API Harvest Logic (extracted from original handle_harvest)
# ─────────────────────────────────────────────────────────────────────

def _http(method, url, headers=None, body=None):
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
        with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, str(e).encode("utf-8")


def _gql(token, query, variables=None):
    body = {"query": query}
    if variables:
        body["variables"] = variables
    status, raw = _http("POST", GQL_URL, {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }, body)
    return status, json.loads(raw.decode("utf-8", errors="replace"))


def _do_full_harvest(watchlist_id=None):
    """Execute the full AIQ GraphQL harvest. Returns the result dict.
    This is the core logic extracted from handle_harvest, now reusable
    for both synchronous and background calls.
    
    If watchlist_id is provided, only systems in that watchlist are fetched.
    """
    global _is_syncing, _last_sync_error

    with _sync_lock:
        if _is_syncing:
            raise Exception("Sync already in progress")
        _is_syncing = True
        _last_sync_error = None

    start_time = time.time()
    try:
        # 1. Read refresh token
        if not CONFIG_PATH.exists():
            raise Exception("No aiq_config.json found")
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        refresh_token = cfg.get("refreshToken") or cfg.get("refresh_token")
        if not refresh_token:
            raise Exception("No refresh token configured")

        print("  [HARVEST] Getting access token...", flush=True)

        # 2. Get access token
        status, raw = _http("POST", f"{REST_BASE}/v1/tokens/accessToken",
            {"Content-Type": "application/json", "Accept": "application/json"},
            {"refresh_token": refresh_token})
        if status != 200:
            raise Exception(f"Token exchange failed: HTTP {status}")
        token_data = json.loads(raw.decode("utf-8", errors="replace"))
        token = token_data.get("access_token")
        if not token:
            raw_s = raw.decode("utf-8", errors="replace").strip().strip('"')
            token = raw_s if len(raw_s) > 30 else None
        if not token:
            raise Exception("No access token in response")
        print("  [HARVEST] Authenticated OK", flush=True)

        # 3. Fetch summary
        print("  [HARVEST] Fetching summary...", flush=True)
        _, summary_resp = _gql(token, "{ summary { system cluster site } }")
        summary = (summary_resp.get("data") or {}).get("summary", {})
        total_sys = summary.get("system", 0)
        total_cl = summary.get("cluster", 0)
        total_sites = summary.get("site", 0)
        print(f"  [HARVEST] Fleet: {total_sys} systems, {total_cl} clusters, {total_sites} sites", flush=True)

        # 4. Fetch ALL systems with full details (pagination)
        #    Strategy: try the expanded TAM query first; if GraphQL rejects any
        #    field the whole response comes back with 0 systems.  In that case
        #    fall back to the proven minimal query.
        print("  [HARVEST] Fetching systems (full details)...", flush=True)


        # ── ORIGINAL (proven, from git commit b318118) ──
        SYSTEMS_FIELDS_MINIMAL = """
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

        # ── Extended: original + safe additional fields ──
        SYSTEMS_FIELDS_TAM = """
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

        # Try expanded first, fall back to minimal
        all_systems = []
        used_tam_query = False
        for attempt, fields in enumerate([SYSTEMS_FIELDS_TAM, SYSTEMS_FIELDS_MINIMAL]):
            all_systems = []
            cursor = None
            page = 0
            while True:
                page += 1
                after_arg = f', after: "{cursor}"' if cursor else ""
                wl_arg = f', watchlistId: "{watchlist_id}"' if watchlist_id else ""
                query_text = """{
                  systems(pageSize: 100""" + after_arg + wl_arg + """) {
                    totalCount cursor
                    systems {""" + fields + """
                    }
                  }
                }"""
                if page == 1:
                    print(f"  [HARVEST] Query attempt {attempt+1} first 300 chars: {query_text[:300]}", flush=True)
                _, sys_resp = _gql(token, query_text)
                sys_data = (sys_resp.get("data") or {}).get("systems", {})
                # Log GraphQL errors if present
                if sys_resp.get("errors") and page == 1:
                    err_msg = sys_resp["errors"][0].get("message", "")[:200]
                    print(f"  [HARVEST] GraphQL errors: {err_msg}", flush=True)
                systems_page = sys_data.get("systems") or []
                all_systems.extend(systems_page)
                new_cursor = sys_data.get("cursor")
                print(f"  [HARVEST] Page {page}: {len(systems_page)} systems (total so far: {len(all_systems)})", flush=True)
                if not systems_page or not new_cursor or new_cursor == cursor:
                    break
                cursor = new_cursor

            if len(all_systems) > 0:
                if attempt == 0:
                    used_tam_query = True
                    print(f"  [HARVEST] Expanded TAM query succeeded: {len(all_systems)} systems", flush=True)
                else:
                    print(f"  [HARVEST] Minimal query succeeded: {len(all_systems)} systems", flush=True)
                break
            elif attempt == 0:
                print("  [HARVEST] WARNING: Expanded TAM query returned 0 systems -- falling back to minimal query...", flush=True)


        # 5. Fetch clusters with full details (including switches and shelves)
        print("  [HARVEST] Fetching clusters...", flush=True)
        all_clusters = []
        cursor = None
        while True:
            after_arg = f', after: "{cursor}"' if cursor else ""
            _, cl_resp = _gql(token, """{
              clusters(pageSize: 100""" + after_arg + """) {
                cursor
                clusters {
                  id
                  name
                  managementIPAddress
                  osVersion
                  isHAConfigured
                  ageInYears
                  osRecommendation { recommendedVersion }
                  snapMirrorRelationships { totalCount }
                  systems { serialNumber }
                  switches {
                    switchSerialNumber
                    deviceName
                    role
                    vendor
                    model
                    ipAddress
                    isDiscovered
                    isMonitored
                    versionInfo { fwVersion rcfVersion }
                  }
                  shelves {
                    serialNumber
                    hardwareModel { name endOfAvailability endOfHwSupport }
                  }
                  capacity {
                    physical { usedKiB rawMarketingKiB usablePerformanceTierKiB qoqUtilizationPercentage yoyUtilizationPercentage }
                    logical { usedKiB }
                    reportedOn
                  }
                  monthlyCapacity {
                    month
                    physical { usedKiB rawMarketingKiB qoqUtilizationPercentage }
                  }
                }
              }
            }""")
            cl_data = (cl_resp.get("data") or {}).get("clusters", {})
            clusters_page = cl_data.get("clusters") or []
            all_clusters.extend(clusters_page)
            new_cursor = cl_data.get("cursor")
            if not clusters_page or not new_cursor or new_cursor == cursor:
                break
            cursor = new_cursor

        print(f"  [HARVEST] Clusters: {len(all_clusters)}", flush=True)

        # 6. Fetch risk instances (paginated, 500 per page)
        print("  [HARVEST] Fetching risk instances...", flush=True)
        all_risk_instances = []
        cursor = None
        ri_page = 0
        while True:
            ri_page += 1
            after_arg = f', after: "{cursor}"' if cursor else ""
            _, ri_resp = _gql(token, """{
                riskInstances(pageSize: 500""" + after_arg + """) {
                  cursor
                  riskInstances {
                    risk {
                      riskId
                      severity
                      category
                      shortName
                      riskDetail
                      potentialImpact
                      impactArea
                      correctiveAction { url displayName }
                    }
                    system { serialNumber hostName }
                    systemRiskDetail
                  }
                }
              }""")
            ri_data = (ri_resp.get("data") or {}).get("riskInstances", {})
            ri_page_items = ri_data.get("riskInstances") or []
            all_risk_instances.extend(ri_page_items)
            new_cursor = ri_data.get("cursor")
            print(f"  [HARVEST] Risk instances page {ri_page}: {len(ri_page_items)} (total so far: {len(all_risk_instances)})", flush=True)
            if not ri_page_items or not new_cursor or new_cursor == cursor:
                break
            cursor = new_cursor
        print(f"  [HARVEST] Total risk instances: {len(all_risk_instances)}", flush=True)

        # 7. Fetch all support cases (active + closed — client will sort/highlight)
        print("  [HARVEST] Fetching support cases...", flush=True)
        _, cases_resp = _gql(token, """{
          cases(pageSize: 500, productTypes: [FILER, SWApp]) {
            totalCount
            cases {
              caseId
              symptom
              description
              status
              priority
              highestPriority
              created
              lastUpdated
              closed
              type
              category
              subCategory
              caseReceivedVia
              reporterContact { name }
              system { serialNumber hostName }
            }
          }
        }""")
        cases_data = (cases_resp.get("data") or {}).get("cases", {})
        all_cases = cases_data.get("cases") or []
        print(f"  [HARVEST] Cases: {len(all_cases)} (totalCount={cases_data.get('totalCount','?')})", flush=True)

        # 8. Fetch customers (with sustainability)
        _, cust_resp = _gql(token, """{ customers(pageSize: 100) { customers {
            id cmatId name
            sustainabilityScorePercentage { overall }
        } } }""")
        customers = ((cust_resp.get("data") or {}).get("customers", {}).get("customers")) or []

        # ── TAM: Recommendations ──
        tam_recommendations = []
        try:
            print("  [HARVEST] Fetching TAM recommendations...", flush=True)
            _, rec_resp = _gql(token, """{ recommendations(isTopKeyRecommendation: true, limit: 50) {
                recommendation rank category subCategory score
            } }""")
            tam_recommendations = (rec_resp.get("data") or {}).get("recommendations") or []
            print(f"  [HARVEST] Recommendations: {len(tam_recommendations)}", flush=True)
        except Exception as e:
            print(f"  [HARVEST] WARNING: Recommendations failed: {e}", flush=True)

        # ── TAM: Sites ──
        tam_sites = []
        try:
            print("  [HARVEST] Fetching TAM sites...", flush=True)
            _, sites_resp = _gql(token, """{ sites(pageSize: 100) { sites {
                id cmatId name countryCode postalCode city state streetAddress
                vmwareFlag systemsWithCriticalPropensity systemsWithHighPropensity
                operationalDate ageInYears
            } } }""")
            tam_sites = ((sites_resp.get("data") or {}).get("sites", {}).get("sites")) or []
            print(f"  [HARVEST] Sites: {len(tam_sites)}", flush=True)
        except Exception as e:
            print(f"  [HARVEST] WARNING: Sites failed: {e}", flush=True)

        # ── TAM: Sustainability Score ──
        tam_sustainability = []
        try:
            print("  [HARVEST] Fetching sustainability score...", flush=True)
            _, sust_resp = _gql(token, """{ sustainabilityScore { sustainabilityScores {
                scorePercentage percentageChange generatedDate changeFactors
            } } }""")
            tam_sustainability = ((sust_resp.get("data") or {}).get("sustainabilityScore", {}).get("sustainabilityScores")) or []
            print(f"  [HARVEST] Sustainability scores: {len(tam_sustainability)}", flush=True)
        except Exception as e:
            print(f"  [HARVEST] WARNING: Sustainability failed: {e}", flush=True)

        # ── TAM: OS Version Catalog ──
        tam_os_versions = []
        try:
            print("  [HARVEST] Fetching OS version catalog...", flush=True)
            _, osv_resp = _gql(token, """{ osVersions(pageSize: 500) { osVersions {
                osVersion majorOsVersion osType operatingMode
                releaseDate endOfVersionFullSupport endOfVersionLimitedSupport endOfSelfServiceSupport
                supportState progressionPath
                bundledSystemFirmwares { type version biosVersion systemModel }
                bundledDriveFirmwares { driveModel version }
                bundledShelfFirmwares { shelfName shelfModuleName firmwareType shelfModuleFirmwareVersion sysShelfModuleFirmwareVersion }
                bundledSecurityFiles { fileType version }
            } } }""")
            tam_os_versions = ((osv_resp.get("data") or {}).get("osVersions", {}).get("osVersions")) or []
            print(f"  [HARVEST] OS versions: {len(tam_os_versions)}", flush=True)
        except Exception as e:
            print(f"  [HARVEST] WARNING: OS versions failed: {e}", flush=True)

        # ── TAM: Contract Renewals with Lifecycle Events ──
        tam_renewals = []
        try:
            print("  [HARVEST] Fetching contract renewals...", flush=True)
            _, ren_resp = _gql(token, """{ systemContractRenewals(pageSize: 200, beginDate: "2024-01-01", endDate: "2030-12-31") { systems {
                serialNumber hostName platformType serviceTier techRefreshStatus
                contract { expiryDate isContractActive hardwareServiceLevel hardwareContractEndDate softwareContractEndDate overallContractEndDate hardwareWarrantyEndDate }
                hardwareModel { name endOfAvailability endOfSupport }
                endOfSupport { earliestEndOfSupportDate latestPVRDate latestEndOfSupportDate }
            } } }""")
            tam_renewals = ((ren_resp.get("data") or {}).get("systemContractRenewals", {}).get("systems")) or []
            print(f"  [HARVEST] Renewals with lifecycle events: {len(tam_renewals)}", flush=True)
        except Exception as e:
            print(f"  [HARVEST] WARNING: Contract renewals failed: {e}", flush=True)

        # 9. Build risksBySerial lookup from riskInstances
        risks_by_serial = {}
        for ri in all_risk_instances:
            ri_sys = ri.get("system") or {}
            serial = ri_sys.get("serialNumber")
            if serial:
                risk_entry = dict(ri.get("risk") or {})
                risk_entry["systemRiskDetail"] = ri.get("systemRiskDetail", "")
                risks_by_serial.setdefault(serial, []).append(risk_entry)

        # 10. Build casesBySerial lookup from cases
        cases_by_serial = {}
        for c in all_cases:
            c_sys = c.get("system") or {}
            serial = c_sys.get("serialNumber")
            if serial:
                cases_by_serial.setdefault(serial, []).append(c)

        # 11. Build unique risks list (deduplicated by riskId)
        unique_risks = {}
        for ri in all_risk_instances:
            r = ri.get("risk") or {}
            rid = r.get("riskId")
            if rid and rid not in unique_risks:
                unique_risks[rid] = r
        all_risks = list(unique_risks.values())

        # 12. Build cluster lookup + serial→cluster reverse map
        cluster_map = {}
        serial_to_cluster = {}
        serial_to_cluster_cap = {}
        serial_to_cluster_sm = {}   # serial → snapMirror relationship count
        serial_to_cluster_ha = {}   # serial → HA configured flag
        serial_to_cluster_switches = {}  # serial → switches list from cluster
        serial_to_cluster_shelves = {}   # serial → shelves list from cluster
        for cl in all_clusters:
            cl_id = cl.get("id") or cl.get("name")
            cl_name = cl.get("name", "")
            if cl_id:
                cluster_map[cl_id] = cl
            cl_systems = cl.get("systems") or []
            cap = cl.get("capacity") or {}
            phys = cap.get("physical") or {}
            logical = cap.get("logical") or {}
            cap_data = {
                "physicalUsedTB": round((phys.get("usedKiB") or 0) / (1024**3), 2),
                "rawCapacityTB": round((phys.get("rawMarketingKiB") or 0) / (1024**3), 2),
                "logicalUsedTB": round((logical.get("usedKiB") or 0) / (1024**3), 2),
                "usableCapacityTB": round((phys.get("usablePerformanceTierKiB") or phys.get("rawMarketingKiB") or 0) / (1024**3), 2),
                "qoqUtilizationPct": phys.get("qoqUtilizationPercentage") or 0,
                "yoyUtilizationPct": phys.get("yoyUtilizationPercentage") or 0,
                "capacityReportedOn": (cap.get("reportedOn") or "")[:10],
                # Monthly history for chart: list of {month, usedKiB, rawKiB}
                "monthlyCapacity": [
                    {
                        "month": m.get("month", ""),
                        "usedTB": round(((m.get("physical") or {}).get("usedKiB") or 0) / (1024**3), 3),
                        "rawTB": round(((m.get("physical") or {}).get("rawMarketingKiB") or 0) / (1024**3), 2),
                        "qoqPct": (m.get("physical") or {}).get("qoqUtilizationPercentage") or None,
                    }
                    for m in (cl.get("monthlyCapacity") or [])
                ],
            }
            sm_count = ((cl.get("snapMirrorRelationships") or {}).get("totalCount")) or 0
            is_ha = cl.get("isHAConfigured", False)
            cl_os = cl.get("osVersion", "")
            cl_rec = ((cl.get("osRecommendation") or {}).get("recommendedVersion")) or ""
            cl_switches = cl.get("switches") or []
            cl_shelves = cl.get("shelves") or []
            for cs in cl_systems:
                cs_serial = cs.get("serialNumber")
                if cs_serial:
                    serial_to_cluster[cs_serial] = cl_name
                    serial_to_cluster_cap[cs_serial] = cap_data
                    serial_to_cluster_sm[cs_serial] = sm_count
                    serial_to_cluster_ha[cs_serial] = is_ha
                    serial_to_cluster_switches[cs_serial] = cl_switches
                    serial_to_cluster_shelves[cs_serial] = cl_shelves
        
        total_sw = sum(len(v) for v in serial_to_cluster_switches.values())
        print(f"  [HARVEST] Switch instances mapped: {total_sw // max(len(serial_to_cluster_switches), 1)} unique across clusters", flush=True)

        # 13. Build final systems output (with full TAM enrichment)
        systems_out = []
        for s in all_systems:
            cust = s.get("customer") or {}
            site = s.get("site") or {}
            hw = s.get("hardwareModel") or {}
            contact = s.get("contactPerson") or {}
            contract = s.get("contract") or {}
            asup = s.get("latestAsup") or {}
            nagp = s.get("nagp") or {}
            sr = s.get("salesRepresentative") or {}
            csm_d = s.get("csm") or {}
            sam_d = s.get("sam") or {}
            gard = s.get("gard") or {}
            asp = s.get("authorizedSupportPartner") or {}
            dp = s.get("domesticParent") or {}
            asup_cfg = s.get("autoSupportConfig") or {}
            sv = s.get("softwareVersion") or {}
            evd = sv.get("endOfVersionDetails") or {}
            eos = s.get("endOfSupport") or {}
            srd = s.get("swRecommendationDetails") or {}
            cap = s.get("capacity") or {}
            cap_phys = cap.get("physical") or {}
            cap_eff = cap.get("efficiency") or {}
            serial = s.get("serialNumber", "")

            cl_name = serial_to_cluster.get(serial, "")
            cl_cap = serial_to_cluster_cap.get(serial, {})

            # Extract switches from port connectivity (device names + port types)
            switches = []
            seen_devs = set()
            pi = s.get("portInterface") or {}
            all_ports = list(pi.get("onboardPorts") or [])
            for card in (pi.get("adapterCards") or []):
                all_ports.extend(card.get("ports") or [])
            for p in all_ports:
                dev = p.get("connectedDevice", "")
                if dev and dev not in seen_devs:
                    seen_devs.add(dev)
                    pt = (p.get("portType") or "").lower()
                    sw_type = "Data"
                    if "cluster" in pt: sw_type = "Cluster Interconnect"
                    elif "intercluster" in pt: sw_type = "Intercluster"
                    switches.append({
                        "deviceName": dev, "type": sw_type,
                        "connectedPort": p.get("connectedPort", ""),
                        "portSpeed": p.get("portSpeed", ""),
                        "portState": p.get("portState", ""),
                        "sourcePort": p.get("portName", ""),
                    })

            # Merge cluster-level switches (with model, firmware, validation data)
            cl_switches = serial_to_cluster_switches.get(serial, [])
            for csw in cl_switches:
                sw_serial = csw.get("switchSerialNumber", "")
                vi = csw.get("versionInfo") or {}
                fw = vi.get("fwVersion", "")
                rcf = vi.get("rcfVersion", "")
                is_monitored = csw.get("isMonitored", False)
                sw_model = csw.get("model") or ""
                sw_vendor = csw.get("vendor") or ""
                sw_name = csw.get("deviceName") or ""
                sw_role = csw.get("role") or "Cluster Interconnect"
                
                status = "Optimal"
                validation = "Switch firmware validated."
                if not is_monitored:
                    status = "Warning"
                    validation = f"Switch '{sw_name}' is not monitored. Enable CSHM for proactive alerting."
                if sw_model == "OTHER" or not sw_model:
                    validation = f"Discovered switch: {sw_name}. Model not recognized by Active IQ — verify IMT compatibility."
                
                switches.append({
                    "type": sw_role,
                    "model": sw_model if sw_model != "OTHER" else sw_vendor or sw_name,
                    "serialNumber": sw_serial,
                    "firmware": fw,
                    "targetFirmware": rcf or fw,
                    "status": status,
                    "ipAddress": csw.get("ipAddress") or "",
                    "validationDetails": validation,
                    "deviceName": sw_name,
                    "vendor": sw_vendor,
                    "isMonitored": is_monitored,
                })

            # Merge cluster-level shelves
            cl_shelves = serial_to_cluster_shelves.get(serial, [])
            shelves_out = s.get("shelves") or []
            for csh in cl_shelves:
                hm = csh.get("hardwareModel") or {}
                shelves_out.append({
                    "serialNumber": csh.get("serialNumber", ""),
                    "model": hm.get("name", ""),
                    "endOfAvailability": hm.get("endOfAvailability", ""),
                    "endOfHwSupport": hm.get("endOfHwSupport", ""),
                })

            # ── Pre-compute capacity from system-level ONTAPSystemPhysicalCapacity ──
            # System-level is preferred; cluster-level used as fallback for systems without cluster data.
            _sys_phys = cap_phys
            _sys_log  = (cap.get("logical") or {})
            _sys_eff  = (cap.get("efficiency") or {})
            _sys_eff_ratio = (_sys_eff.get("ratio") or {})
            _sys_eff_saved = (_sys_eff.get("saved") or {})
            # ── Efficiency ratio fields (ONTAPSystemEfficiency.ratio) ──
            _eff_ratio     = _sys_eff_ratio.get("efficiencyRatio")       # includes snapshots
            _data_red      = _sys_eff_ratio.get("dataReductionRatio")    # dedupe+compression only ← preferred
            _snap_ratio    = _sys_eff_ratio.get("withSnapshotRatio")     # with-snapshot ratio (reference)
            # ── Space saved KiB fields (ONTAPSystemEfficiency.saved) ──
            _saved_kib     = _sys_eff_saved.get("savedKiB")              # total (includes snapshot savings)
            _dedup_kib     = _sys_eff_saved.get("deDuplicationSavedKiB") # pure dedup savings
            _compact_kib   = _sys_eff_saved.get("compactionSavedKiB")    # compaction savings

            _sys_monthly = []
            for m in (s.get("monthlyCapacity") or []):
                mp  = m.get("physical") or {}
                ml  = m.get("logical") or {}
                mep = (m.get("efficiency") or {}).get("ratio") or {}
                mraw = mp.get("rawMarketingKiB") or 0
                mused = mp.get("usedKiB") or 0
                mutil = mp.get("utilizationPercentage") or 0
                # If usedKiB is 0 but utilizationPercentage is set, derive used
                if mused == 0 and mraw > 0 and mutil > 0:
                    mused = mraw * mutil / 100.0
                _sys_monthly.append({
                    "month":   m.get("month", ""),
                    "usedTB":  round(mused / (1024**3), 3),
                    "rawTB":   round(mraw  / (1024**3), 2),
                    "qoqPct":  mp.get("qoqUtilizationPercentage"),
                    "effRatio": mep.get("efficiencyRatio"),
                    "logUsedTB": round((ml.get("usedKiB") or 0) / (1024**3), 3),
                })
            _raw_kib  = _sys_phys.get("rawMarketingKiB") or 0
            _used_kib = _sys_phys.get("usedKiB") or 0
            _log_kib  = _sys_log.get("usedKiB") or 0
            _usbl_kib = _sys_phys.get("usablePerformanceTierKiB") or 0
            _qoq      = _sys_phys.get("qoqUtilizationPercentage") or 0
            _yoy      = _sys_phys.get("yoyUtilizationPercentage") or 0
            _util_pct = _sys_phys.get("utilizationPercentage") or 0
            # Fix API gap: if usedKiB is 0 but utilizationPercentage is set, derive it
            if _used_kib == 0 and _raw_kib > 0 and _util_pct > 0:
                _used_kib = _raw_kib * _util_pct / 100.0
            # Fall back to cluster-level if system-level raw is also zero
            if _raw_kib == 0:
                _raw_kib  = cl_cap.get("rawCapacityTB", 0) * (1024**3)
                _used_kib = cl_cap.get("physicalUsedTB", 0) * (1024**3)
                _log_kib  = cl_cap.get("logicalUsedTB", 0) * (1024**3)
                _usbl_kib = cl_cap.get("usableCapacityTB", 0) * (1024**3)
                _qoq      = cl_cap.get("qoqUtilizationPct", 0)
                _yoy      = cl_cap.get("yoyUtilizationPct", 0)

            systems_out.append({
                # ── Core identity ──
                "serialNumber": serial,
                "systemName": s.get("hostName", ""),
                "clusterName": cl_name,
                "customerName": cust.get("name", ""),
                "customerId": cust.get("id", ""),
                "siteName": site.get("name", ""),
                "siteId": site.get("id", ""),
                "siteCity": site.get("city", ""),
                "siteCountry": site.get("countryCode", ""),
                "siteState": site.get("state", ""),
                "nagpId": nagp.get("id", ""),
                "nagpName": nagp.get("name", ""),
                "model": hw.get("name", ""),
                "modelRevision": hw.get("modelRevision", ""),
                "osVersion": s.get("osVersion", ""),
                "platform": s.get("platformType", ""),
                "systemType": s.get("type", ""),
                "productType": s.get("productType", ""),
                "systemState": s.get("systemState", ""),
                "systemId": s.get("systemId", ""),
                "ageInYears": s.get("ageInYears"),
                "serviceTier": s.get("serviceTier", ""),
                "recommendedOSVersion": s.get("recommendedOSVersion", ""),
                "resellerCompany": s.get("incumbentResellerCompany", ""),
                "techRefreshStatus": s.get("techRefreshStatus", ""),
                "lastRebootTime": s.get("lastRebootTime", ""),
                "originalShipDate": s.get("originalShipDate", ""),
                "marketingType": s.get("marketingType", ""),
                "storageConfiguration": s.get("storageConfiguration", ""),
                "isFabricPool": s.get("isFabricPool"),
                "hasPvr": s.get("hasPvr"),
                # ── Platform personality (ASA r2 / AFX — detected via model name) ──
                "personality": "",
                "isDisaggregated": False,
                "isAsaR2": hw.get("name", "").upper().startswith("ASA A"),
                "isAfx": "EF50" in hw.get("name", "").upper() or "EF80" in hw.get("name", "").upper() or "AFX" in hw.get("name", "").upper(),
                # SAZ capacity not available via API
                "sazTotalRawKiB": 0,
                "sazUsedKiB": 0,
                "sazAvailableKiB": 0,
                "sazProvisionedKiB": 0,
                "sazEffectiveCapacityKiB": 0,
                "sazDataReductionRatio": None,
                # ASA r2 / storage unit counts not available via API
                "consistencyGroupCount": 0,
                "storageUnitCount": 0,
                # ── Contacts & personnel ──
                "contactFirstName": contact.get("firstName", ""),
                "contactLastName": contact.get("lastName", ""),
                "contactPhone": contact.get("phone", ""),
                "contactEmail": contact.get("email", ""),
                "salesRepName": sr.get("name", ""),
                "salesRepEmail": sr.get("emailAddress", ""),
                "csmName": csm_d.get("name", ""),
                "csmEmail": csm_d.get("emailAddress", ""),
                "samName": sam_d.get("name", ""),
                "samEmail": sam_d.get("emailAddress", ""),
                "gard": gard,
                "aspName": asp.get("name", ""),
                "aspEndDate": asp.get("endDate", ""),
                "domesticParentName": dp.get("name", ""),
                # ── Contract ──
                "contractActive": contract.get("isContractActive"),
                "contractEndDate": contract.get("overallContractEndDate", ""),
                "contractHWEndDate": contract.get("hardwareContractEndDate", ""),
                "contractSWEndDate": contract.get("softwareContractEndDate", ""),
                "contractNRDEndDate": contract.get("nrdContractEndDate", ""),
                "contractExpiry": contract.get("expiryDate", ""),
                "warrantyEndDate": contract.get("hardwareWarrantyEndDate", ""),
                "warrantyStartDate": contract.get("hardwareWarrantyStartDate", ""),
                "serviceLevel": contract.get("hardwareServiceLevel", ""),
                "contractSWId": contract.get("softwareContractId", ""),
                "contractHWId": contract.get("hardwareContractId", ""),
                # ── Hardware lifecycle ──
                "hwEndOfAvailability": hw.get("endOfAvailability", ""),
                "hwEndOfSupport": hw.get("endOfSupport", ""),
                "eosEarliest": eos.get("earliestEndOfSupportDate", ""),
                "eosShelf": eos.get("earliestShelfEndOfSupportDate", ""),
                "eosDisk": eos.get("earliestDiskEndOfSupportDate", ""),
                "eosPVR": eos.get("latestPVRDate", ""),
                "eosLatest": eos.get("latestEndOfSupportDate", ""),
                # ── Software version details ──
                "softwareVersionFull": sv.get("fullVersionString", ""),
                "swReleaseDate": evd.get("releaseDate", ""),
                "swEndOfFullSupport": evd.get("endOfVersionFullSupport", ""),
                "swEndOfLimitedSupport": evd.get("endOfVersionLimitedSupport", ""),
                "swEndOfSelfService": evd.get("endOfSelfServiceSupport", ""),
                "swRecMin": srd.get("minRecommendedVersion", ""),
                "swRecLatest": srd.get("latestRecommendedVersion", ""),
                "swCQV": (srd.get("cqvDetails") or {}).get("qualifiedVersion", ""),
                # ── ONTAP flags ──
                "isMetroCluster": s.get("isMetroCluster"),
                "isAllFlashOptimized": s.get("isAllFlashOptimized"),
                "isFlexPod": s.get("isFlexPod"),
                "isARPEnabled": s.get("isARPEnabled"),
                "operatingMode": s.get("operatingMode", ""),
                "propensityCategory": s.get("propensityCategory", ""),
                "nextBestAction": s.get("nextBestAction", ""),
                "belongsToMixModelCluster": s.get("belongsToMixModelCluster"),
                "serviceProcessorIP": s.get("serviceProcessorIPAddress", ""),
                "autoUpdateEnabled": s.get("autoUpdateEnabled"),
                # ASA r2: SAZ-level capacity (no aggregates; pull from storageAvailabilityZone)
                "sazTotalRawKiB": 0,
                "sazUsedKiB": 0,
                "sazAvailableKiB": 0,
                # ── AutoSupport ──
                "latestAsupDate": asup.get("receivedDate") or asup.get("generatedDate", ""),
                "latestAsupSubject": asup.get("subject", ""),
                "latestAsupType": asup.get("type", ""),
                "latestAsupIsManual": asup.get("isManual"),
                "latestAsupId": asup.get("asupId", ""),
                "asupStatus": asup_cfg.get("autoSupportStatus", ""),
                "asupTransport": asup_cfg.get("autoSupportTransport", ""),
                "asupOnDemand": asup_cfg.get("isAutoSupportOnDemandEnabled"),
                "asupDomain": asup_cfg.get("systemDomain", ""),
                "asupHistory": s.get("autoSupports") or [],
                "asupByType": s.get("latestAsupOfEachType") or [],
                # ── Firmware ──
                "systemFirmware": s.get("systemFirmware") or [],
                "motherboardFirmware": s.get("motherboardFirmware") or {},
                "diskQualificationPackage": s.get("diskQualificationPackage") or {},
                "autoUpdateSettings": s.get("autoUpdateSettings") or {},
                # ── Lifecycle & TAM intelligence ──
                "lifecycleEvents": s.get("lifecycleEvents") or [],
                "licenses": s.get("licenses") or [],
                "pvrs": s.get("pvrs") or [],
                # ── Downtime & monthly stats ──
                "downtimeEvents": s.get("downtimeEvents") or {},
                "monthlyUptimeStats": s.get("monthlyUptimeStats") or [],
                "monthlyCarbonStats": s.get("monthlyCarbonStats") or [],
                "monthlyResolvedRisksStats": s.get("monthlyResolvedRisksStats") or [],
                "monthlyArpStats": s.get("monthlyArpStats") or [],
                "monthlyAutoResolvedCases": s.get("monthlyAutoResolvedCases") or [],
                "sustainabilityScores": s.get("sustainabilityScores") or [],
                # ── Capacity ──
                "capacityAllocatedKB": 0,
                "capacityUsedKB": round(_used_kib),
                "capacityAvailableKB": round(max(0, _usbl_kib - _used_kib)),
                "dataReductionRatio": _data_red or cap_eff.get("dataReductionRatio"),
                "clusterPhysicalUsedTB": round(_used_kib  / (1024**3), 2),
                "clusterRawCapacityTB":  round(_raw_kib   / (1024**3), 2),
                "clusterLogicalUsedTB":  round(_log_kib   / (1024**3), 2),
                "clusterUsableCapacityTB": round((_usbl_kib or _raw_kib) / (1024**3), 2),
                "clusterQoQUtilPct": _qoq,
                "clusterYoYUtilPct": _yoy,
                "clusterCapacityUtilPct": _util_pct,
                "clusterCapacityReportedOn": (cap.get("reportedOn") or cl_cap.get("capacityReportedOn", "") or "")[:10],
                "clusterMonthlyCapacity": _sys_monthly if _sys_monthly else cl_cap.get("monthlyCapacity", []),
                # ── Efficiency (from system-level GQL) ──
                "efficiencyRatio": _eff_ratio,
                "dataReductionRatioSys": _data_red,
                "withSnapshotRatio": _snap_ratio,
                "savedKiB": _saved_kib,
                "dedupSavedKiB": _dedup_kib,
                "compactionSavedKiB": _compact_kib,
                "snapMirrorCount": serial_to_cluster_sm.get(serial, 0),
                "isHAConfigured": serial_to_cluster_ha.get(serial, False),
                # ── Shelves, drives, ports, switches ──
                "shelves": shelves_out,
                "portInterface": s.get("portInterface") or {},
                "networkPorts": s.get("networkPorts") or {},
                "switches": switches,
                "vcenters": s.get("vcenters") or [],
                # ── Risks & cases ──
                "risks": risks_by_serial.get(serial, []),
                "cases": cases_by_serial.get(serial, []),
                "_source": "graphql",
            })

        # 14. Try fetching watchlists from REST API
        watchlists_out = []
        try:
            for wl_path in ["/v1/watchlists/list", "/v1/watchlist/all", "/v2/watchlist/action"]:
                try:
                    wl_status, wl_raw = _http("GET", f"{REST_BASE}{wl_path}",
                        {"Authorization": f"Bearer {token}", "Accept": "application/json"})
                    if wl_status == 200:
                        wl_data = json.loads(wl_raw.decode("utf-8", errors="replace"))
                        wl_list = wl_data if isinstance(wl_data, list) else wl_data.get("results", wl_data.get("watchlists", []))
                        if isinstance(wl_list, list) and len(wl_list) > 0:
                            for wl in wl_list:
                                if isinstance(wl, dict):
                                    watchlists_out.append({
                                        "id": wl.get("watchListId") or wl.get("watchlistId") or wl.get("id", ""),
                                        "name": wl.get("watchListName") or wl.get("watchlistName") or wl.get("name", "Watchlist"),
                                        "systemSerials": [],
                                    })
                            if watchlists_out:
                                print(f"  [HARVEST] Watchlists: {len(watchlists_out)} from {wl_path}", flush=True)
                                break
                except Exception:
                    pass
        except Exception as e:
            print(f"  [HARVEST] Watchlist fetch skipped: {e}", flush=True)

        # 14b. Resolve system serial numbers for each watchlist via GraphQL
        if watchlists_out:
            print(f"  [HARVEST] Resolving system serials for {len(watchlists_out)} watchlist(s)...", flush=True)
            for wl in watchlists_out[:20]:  # Limit to 20 watchlists to avoid excessive API calls
                wl_id = wl.get("id", "")
                if not wl_id:
                    continue
                try:
                    serials = []
                    wl_cursor = None
                    for wl_page in range(50):  # Max 5000 systems per watchlist
                        after_arg = f', after: "{wl_cursor}"' if wl_cursor else ""
                        _, wl_sys_resp = _gql(token, """{
                          systems(pageSize: 100, watchlistId: \"""" + wl_id + """\" """ + after_arg + """) {
                            totalCount cursor
                            systems { serialNumber }
                          }
                        }""")
                        wl_sys_data = (wl_sys_resp.get("data") or {}).get("systems", {})
                        wl_systems = wl_sys_data.get("systems") or []
                        for ws in wl_systems:
                            sn = ws.get("serialNumber") or ""
                            if sn:
                                serials.append(sn)
                        new_cursor = wl_sys_data.get("cursor")
                        if not wl_systems or not new_cursor or new_cursor == wl_cursor:
                            break
                        wl_cursor = new_cursor
                    wl["systemSerials"] = serials
                    print(f"    Watchlist '{wl['name']}': {len(serials)} systems", flush=True)
                except Exception as wl_err:
                    print(f"    Watchlist '{wl.get('name', wl_id)}' serial resolve failed: {wl_err}", flush=True)

        duration_ms = int((time.time() - start_time) * 1000)

        result = {
            "status": "success",
            "systems": systems_out,
            "clusters": all_clusters,
            "risks": all_risks,
            "cases": all_cases,
            "riskInstances": len(all_risk_instances),
            "customers": customers,
            "watchlists": watchlists_out,
            "totalSystems": len(systems_out),
            "totalClusters": len(all_clusters),
            "totalRisks": len(all_risks),
            "totalCases": len(all_cases),
            "totalRiskInstances": len(all_risk_instances),
            "summary": summary,
            # ── TAM data ──
            "tamRecommendations": tam_recommendations,
            "tamSites": tam_sites,
            "tamSustainability": tam_sustainability,
            "tamOsVersions": tam_os_versions,
            "tamRenewals": tam_renewals,
        }

        print(f"  [HARVEST] Done in {duration_ms}ms: {len(systems_out)} systems, {len(all_clusters)} clusters, {len(all_risks)} unique risks, {len(all_risk_instances)} risk instances, {len(all_cases)} cases", flush=True)

        # Save to cache
        db = _init_db()
        try:
            _save_harvest(db, result, duration_ms)
        finally:
            db.close()

        return result

    except Exception as e:
        _last_sync_error = str(e)
        raise
    finally:
        with _sync_lock:
            _is_syncing = False


def _background_sync():
    """Run a full harvest in the background. Errors are logged, not raised."""
    try:
        # Read watchlistId from config for background sync
        wl_id = None
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
            wl_id = cfg.get("watchlistId") or cfg.get("watchlist_id") or None
        except Exception:
            pass
        scope_msg = f" (watchlist: {wl_id})" if wl_id else " (all systems)"
        print(f"  [BACKGROUND] Starting background re-sync{scope_msg}...", flush=True)
        _do_full_harvest(watchlist_id=wl_id)
        print("  [BACKGROUND] Background re-sync complete.", flush=True)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"  [BACKGROUND] Sync failed: {e}", flush=True)


# ─────────────────────────────────────────────────────────────────────
# HTTP Request Handler
# ─────────────────────────────────────────────────────────────────────

class ProxyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Inject CORS headers for local origin access
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, AuthorizationToken, Content-Type')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def do_OPTIONS(self):
        # Handle CORS preflight options check
        self.send_response(200, "OK")
        self.end_headers()

    def do_GET(self):
        # Serve the development HTML (external app.js) instead of the
        # compiled single-file index.html, so code changes take effect
        # without recompiling.
        if self.path in ('/', '/index.html', '/index.html?'):
            self.path = '/index_src.html'
        if self.path.startswith('/api/harvest'):
            self.handle_harvest()
        elif self.path.startswith('/api/sync-status'):
            self.handle_sync_status()
        elif self.path.startswith('/api/resolve-watchlist'):
            self.handle_resolve_watchlist()
        elif self.path.startswith('/api/config'):
            self.handle_config_get()
        elif self.path.startswith('/api/watchlists'):
            self.handle_watchlists()
        elif self.path.startswith('/api/'):
            self.handle_proxy('GET')
        else:
            super().do_GET()

    def handle_resolve_watchlist(self):
        """GET /api/resolve-watchlist?watchlistId=xxx — resolve system serials for a watchlist via GQL."""
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        watchlist_id = params.get("watchlistId", [None])[0]

        if not watchlist_id:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "watchlistId parameter required"}).encode("utf-8"))
            return

        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
            refresh_token = cfg.get("refreshToken") or cfg.get("refresh_token")
            if not refresh_token:
                raise Exception("No refresh token configured")

            # Get access token
            status, raw = _http("POST", f"{REST_BASE}/v1/tokens/accessToken",
                {"Content-Type": "application/json", "Accept": "application/json"},
                {"refresh_token": refresh_token})
            if status != 200:
                raise Exception(f"Token exchange failed: HTTP {status}")
            token_data = json.loads(raw.decode("utf-8", errors="replace"))
            token = token_data.get("access_token")
            if not token:
                raw_s = raw.decode("utf-8", errors="replace").strip().strip('"')
                token = raw_s if len(raw_s) > 30 else None
            if not token:
                raise Exception("No access token")

            # Query systems for this watchlist
            serials = []
            cursor = None
            for page in range(50):  # Max 5000 systems per watchlist
                after_arg = f', after: "{cursor}"' if cursor else ""
                _, sys_resp = _gql(token, """{
                  systems(pageSize: 100, watchlistId: \"""" + watchlist_id + """\" """ + after_arg + """) {
                    totalCount cursor
                    systems { serialNumber }
                  }
                }""")
                sys_data = (sys_resp.get("data") or {}).get("systems", {})
                systems_page = sys_data.get("systems") or []
                for s in systems_page:
                    sn = s.get("serialNumber") or ""
                    if sn:
                        serials.append(sn)
                new_cursor = sys_data.get("cursor")
                total = sys_data.get("totalCount", 0)
                if not systems_page or not new_cursor or new_cursor == cursor:
                    break
                cursor = new_cursor

            print(f"  [RESOLVE] Watchlist {watchlist_id}: {len(serials)} systems (totalCount: {total})", flush=True)

            res_bytes = json.dumps({"watchlistId": watchlist_id, "systemSerials": serials, "totalCount": total}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(res_bytes)
        except Exception as e:
            print(f"  [RESOLVE] Error: {e}", flush=True)
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e), "systemSerials": []}).encode("utf-8"))

    def handle_sync_status(self):
        """Return sync metadata as JSON."""
        db = _init_db()
        try:
            meta = _get_sync_meta(db)
        finally:
            db.close()
        res_bytes = json.dumps(meta, default=str).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(res_bytes)

    def handle_harvest(self):
        """Server-side harvest with SQLite cache layer.
        
        Default: serve cached data instantly, trigger background re-sync.
        With ?force=1: bypass cache, do full harvest synchronously.
        """
        # Parse query params
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        force = params.get("force", ["0"])[0] == "1"
        watchlist_id = params.get("watchlistId", [None])[0]

        # If no watchlistId in query params, check config
        if not watchlist_id:
            try:
                cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
                watchlist_id = cfg.get("watchlistId") or cfg.get("watchlist_id") or None
            except Exception:
                pass

        try:
            if force:
                # Force mode: full synchronous harvest, bypass cache
                scope_msg = f" (watchlist: {watchlist_id})" if watchlist_id else " (all systems)"
                print(f"  [HARVEST] Force sync requested{scope_msg}", flush=True)
                result = _do_full_harvest(watchlist_id=watchlist_id)
                res_bytes = json.dumps(result, default=str).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("X-Cache", "BYPASS")
                self.send_header("X-Sync-Mode", "force")
                self.end_headers()
                self.wfile.write(res_bytes)
                return

            # Check cache first
            db = _init_db()
            try:
                cached_result, meta = _load_cached(db)
            finally:
                db.close()

            if cached_result:
                # Serve cached data immediately
                last_sync = meta.get("harvested_at", "unknown")
                sys_count = meta.get("system_count", 0)
                print(f"  [CACHE] Serving cached data ({sys_count} systems, synced: {last_sync})", flush=True)

                # Inject cache metadata into response
                cached_result["_cache"] = {
                    "hit": True,
                    "lastSync": last_sync,
                    "durationMs": meta.get("duration_ms", 0),
                }

                res_bytes = json.dumps(cached_result, default=str).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("X-Cache", "HIT")
                self.send_header("X-Last-Sync", last_sync)
                self.end_headers()
                self.wfile.write(res_bytes)

                # Trigger background re-sync (non-blocking)
                if not _is_syncing:
                    t = threading.Thread(target=_background_sync, daemon=True)
                    t.start()
                    print("  [CACHE] Background re-sync thread started", flush=True)
                else:
                    print("  [CACHE] Sync already in progress, skipping background sync", flush=True)
                return

            # No cache — do full synchronous harvest
            scope_msg = f" (watchlist: {watchlist_id})" if watchlist_id else " (all systems)"
            print(f"  [CACHE] No cached data — doing full harvest{scope_msg}", flush=True)
            result = _do_full_harvest(watchlist_id=watchlist_id)
            res_bytes = json.dumps(result, default=str).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Cache", "MISS")
            self.end_headers()
            self.wfile.write(res_bytes)

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  [HARVEST] FAILED: {e}", flush=True)

            # On failure, try to serve stale cache if available
            try:
                db = _init_db()
                try:
                    cached_result, meta = _load_cached(db)
                finally:
                    db.close()

                if cached_result:
                    last_sync = meta.get("harvested_at", "unknown")
                    print(f"  [CACHE] Serving stale cache after error (last sync: {last_sync})", flush=True)
                    cached_result["_cache"] = {
                        "hit": True,
                        "stale": True,
                        "lastSync": last_sync,
                        "error": str(e),
                    }
                    res_bytes = json.dumps(cached_result, default=str).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("X-Cache", "STALE")
                    self.send_header("X-Last-Sync", last_sync)
                    self.end_headers()
                    self.wfile.write(res_bytes)
                    return
            except Exception:
                pass

            # No cache at all — return error
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "error", "message": str(e), "systems": [], "watchlists": []
            }).encode("utf-8"))

    def do_POST(self):
        if self.path == '/api/app/update':
            self.handle_app_update()
        elif self.path == '/api/config':
            self.handle_config_post()
        elif self.path.startswith('/api/') or self.path == '/graphql':
            self.handle_proxy('POST')
        else:
            self.send_error(404, "Not Found")

    def do_PUT(self):
        if self.path.startswith('/api/'):
            self.handle_proxy('PUT')
        else:
            self.send_error(404, "Not Found")

    def handle_config_get(self):
        """GET /api/config — return current config (without sensitive tokens)."""
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
            # Return only non-sensitive fields
            safe_cfg = {
                "watchlistId": cfg.get("watchlistId") or cfg.get("watchlist_id") or "",
                "watchlistName": cfg.get("watchlistName", ""),
                "hasToken": bool(cfg.get("refreshToken") or cfg.get("refresh_token")),
            }
            res_bytes = json.dumps(safe_cfg).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(res_bytes)
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def handle_config_post(self):
        """POST /api/config — update config fields (merges with existing)."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length).decode("utf-8"))
            # Read existing config
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
            # Merge allowed fields
            if "watchlistId" in body:
                cfg["watchlistId"] = body["watchlistId"] or ""
            if "watchlistName" in body:
                cfg["watchlistName"] = body["watchlistName"] or ""
            # Write back
            CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
            print(f"  [CONFIG] Updated: watchlistId={cfg.get('watchlistId', '')}, watchlistName={cfg.get('watchlistName', '')}", flush=True)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def handle_watchlists(self):
        """GET /api/watchlists — fetch available watchlists from AIQ REST API."""
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
            refresh_token = cfg.get("refreshToken") or cfg.get("refresh_token")
            if not refresh_token:
                raise Exception("No refresh token configured")

            # Get access token
            status, raw = _http("POST", f"{REST_BASE}/v1/tokens/accessToken",
                {"Content-Type": "application/json", "Accept": "application/json"},
                {"refresh_token": refresh_token})
            if status != 200:
                raise Exception(f"Token exchange failed: HTTP {status}")
            token_data = json.loads(raw.decode("utf-8", errors="replace"))
            token = token_data.get("access_token")
            if not token:
                raw_s = raw.decode("utf-8", errors="replace").strip().strip('"')
                token = raw_s if len(raw_s) > 30 else None
            if not token:
                raise Exception("No access token")

            # Fetch watchlists
            watchlists = []
            for wl_path in ["/v1/watchlists/list", "/v1/watchlist/all", "/v2/watchlist/action"]:
                try:
                    wl_status, wl_raw = _http("GET", f"{REST_BASE}{wl_path}",
                        {"Authorization": f"Bearer {token}", "Accept": "application/json"})
                    if wl_status == 200:
                        wl_data = json.loads(wl_raw.decode("utf-8", errors="replace"))
                        wl_list = wl_data if isinstance(wl_data, list) else wl_data.get("results", wl_data.get("watchlists", []))
                        if isinstance(wl_list, list) and len(wl_list) > 0:
                            for wl in wl_list:
                                if isinstance(wl, dict):
                                    watchlists.append({
                                        "id": wl.get("watchListId") or wl.get("watchlistId") or wl.get("id", ""),
                                        "name": wl.get("watchListName") or wl.get("watchlistName") or wl.get("name", "Watchlist"),
                                        "systemCount": wl.get("systemCount") or wl.get("system_count") or 0,
                                    })
                            if watchlists:
                                break
                except Exception:
                    pass

            res_bytes = json.dumps({"watchlists": watchlists}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(res_bytes)
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e), "watchlists": []}).encode("utf-8"))

    def handle_app_update(self):
        import subprocess
        try:
            res = subprocess.run(["git", "pull"], capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                res_json = {"status": "success", "message": "Application code updated from Git repository successfully!"}
                self.wfile.write(json.dumps(res_json).encode('utf-8'))
            else:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                err_msg = res.stderr or res.stdout or "Git pull command failed."
                res_json = {"status": "error", "message": f"Git update failed: {err_msg.strip()}"}
                self.wfile.write(json.dumps(res_json).encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            res_json = {"status": "error", "message": f"Server error: {str(e)}"}
            self.wfile.write(json.dumps(res_json).encode('utf-8'))

    def handle_proxy(self, method):
        if self.path == '/graphql':
            target_url = "https://api.activeiq.netapp.com/graphql"
        else:
            # Strip /api prefix, leaving e.g. /watchlist/all or /v2/watchlist/action
            endpoint = self.path[4:]  # removes leading /api

            # If the endpoint already carries an explicit version (/v2/...), use it
            # as-is on the base domain. Otherwise, default to /v1.
            import re
            if re.match(r'^/v\d+/', endpoint):
                target_url = f"https://api.activeiq.netapp.com{endpoint}"
            else:
                target_url = f"https://api.activeiq.netapp.com/v1{endpoint}"
        
        # Read request body data for POST
        content_length = int(self.headers.get('Content-Length', 0))
        req_data = self.rfile.read(content_length) if content_length > 0 else None
        
        # Clone headers (skipping host and connection to prevent conflicts)
        headers = {}
        for key, val in self.headers.items():
            if key.lower() not in ['host', 'connection', 'content-length', 'accept-encoding']:
                headers[key] = val

        if method == 'POST' and 'Content-Type' not in headers:
            headers['Content-Type'] = 'application/json'

        # Query NetApp API using standard urllib
        print(f"  → PROXY {method} {target_url}", flush=True)
        req = urllib.request.Request(target_url, data=req_data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as response:
                res_data = response.read()
                print(f"  ← {response.status} ({len(res_data)} bytes)", flush=True)
                self.send_response(response.status)
                
                # Forward remote response headers
                for key, val in response.getheaders():
                    if key.lower() not in ['transfer-encoding', 'content-encoding', 'access-control-allow-origin']:
                        self.send_header(key, val)
                
                self.end_headers()
                self.wfile.write(res_data)
        except urllib.error.HTTPError as e:
            res_data = e.read()
            body_preview = res_data[:200].decode('utf-8', errors='replace')
            print(f"  ← HTTP {e.code} ERROR: {body_preview}", flush=True)
            self.send_response(e.code)
            for key, val in e.headers.items():
                if key.lower() not in ['transfer-encoding', 'content-encoding', 'access-control-allow-origin']:
                    self.send_header(key, val)
            self.end_headers()
            self.wfile.write(res_data)
        except Exception as e:
            print(f"  ← PROXY EXCEPTION: {e}", flush=True)
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode('utf-8'))


if __name__ == '__main__':
    # Initialize the cache DB on startup
    db = _init_db()
    cached, meta = _load_cached(db)
    db.close()

    print(f"Starting CORS Proxy Web Server on port {PORT}...")
    if cached:
        print(f"  [CACHE] Found cached data: {meta['system_count']} systems (last sync: {meta['harvested_at']})")
    else:
        print(f"  [CACHE] No cached data — first harvest will be from API")
    print(f"Access the dashboard at http://localhost:{PORT}")

    server = http.server.HTTPServer(('127.0.0.1', PORT), ProxyHTTPRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
        server.server_close()
