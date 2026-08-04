import os
import json
import re
import time
import urllib.request
import urllib.error
import argparse
from datetime import datetime

_ENRICH_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
_LAST_REQUEST_TIME = 0

def fetch_url(url, accept='text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'):
    """Fetch a URL with rate limiting and proper headers."""
    global _LAST_REQUEST_TIME
    now = time.time()
    elapsed = now - _LAST_REQUEST_TIME
    if elapsed < 2.0:
        time.sleep(2.0 - elapsed)
    
    _LAST_REQUEST_TIME = time.time()
    
    req = urllib.request.Request(url, headers={
        'User-Agent': _ENRICH_UA,
        'Accept': accept,
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"  [FW-HARVEST] Error fetching {url}: {e}")
        return ""

def fetch_json(url):
    """Fetch and parse a JSON URL."""
    raw = fetch_url(url, accept='application/json,*/*;q=0.8')
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"  [FW-HARVEST] JSON parse error for {url}: {e}")
    return None

def version_greater(v_new, v_old):
    if not v_old:
        return True
    
    def parse_v(v):
        return [int(x) for x in re.findall(r'\d+', str(v))]
    
    try:
        return parse_v(v_new) > parse_v(v_old)
    except Exception:
        return v_new > v_old

# ═══════════════════════════════════════════════════════════════════════
#  Source 1: endoflife.date API — ONTAP lifecycle data
#  Returns: [{cycle, latest, releaseDate, eol, lts}, ...]
# ═══════════════════════════════════════════════════════════════════════
def harvest_ontap_endoflife():
    """Fetch ONTAP versions from endoflife.date public API."""
    versions = {"latestGA": None, "latestByBranch": {}, "source": "endoflife.date"}
    data = fetch_json("https://endoflife.date/api/netapp-ontap.json")
    if not data or not isinstance(data, list):
        return versions
    
    for entry in data:
        cycle = entry.get("cycle", "")
        latest = entry.get("latest", cycle)
        if not cycle:
            continue
        
        # latestGA = the newest cycle (first entry since sorted desc by endoflife.date)
        if versions["latestGA"] is None:
            versions["latestGA"] = cycle
        
        # Track latest patch per branch
        branch_match = re.match(r'(9\.\d{1,2}\.\d+)', latest)
        if branch_match:
            branch = branch_match.group(1)
            versions["latestByBranch"][branch] = latest
    
    if versions["latestGA"]:
        print(f"  [FW-HARVEST] endoflife.date: latestGA={versions['latestGA']}, {len(versions['latestByBranch'])} branches")
    return versions

# ═══════════════════════════════════════════════════════════════════════
#  Source 2: PyPI netapp-ontap SDK — releases mirror ONTAP versions
#  Returns version list like ["9.16.1.0", "9.15.1.0", ...]
# ═══════════════════════════════════════════════════════════════════════
def harvest_ontap_pypi():
    """Fetch ONTAP version info from PyPI netapp-ontap package releases."""
    versions = {"latestGA": None, "latestByBranch": {}, "source": "pypi.org"}
    data = fetch_json("https://pypi.org/pypi/netapp-ontap/json")
    if not data:
        return versions
    
    releases = data.get("releases", {})
    ontap_versions = []
    for ver in releases.keys():
        # Match only clean GA versions: 9.X.Y or 9.X.Y.Z (no rc/alpha/beta/dev suffixes)
        if re.match(r'^9\.\d{1,2}\.\d+(\.\d+)?$', ver):
            ontap_versions.append(ver)
    
    if not ontap_versions:
        return versions
    
    # Sort by version tuple
    def vkey(v):
        return tuple(int(x) for x in re.findall(r'\d+', v))
    
    ontap_versions.sort(key=vkey, reverse=True)
    
    # Latest GA = highest version (strip .0 suffix if present)
    latest = ontap_versions[0]
    # Convert "9.16.1.0" → "9.16.1"
    parts = latest.split('.')
    if len(parts) == 4 and parts[3] == '0':
        latest = '.'.join(parts[:3])
    versions["latestGA"] = latest
    
    # Build branch map
    for v in ontap_versions:
        parts = v.split('.')
        if len(parts) >= 3:
            branch = '.'.join(parts[:3])
            if branch not in versions["latestByBranch"]:
                versions["latestByBranch"][branch] = branch
    
    if versions["latestGA"]:
        print(f"  [FW-HARVEST] PyPI: latestGA={versions['latestGA']}, {len(versions['latestByBranch'])} branches")
    return versions

# ═══════════════════════════════════════════════════════════════════════
#  Source 3: GitHub API — NetApp ONTAP REST Python SDK releases
#  Returns tag_name list like ["v9.16.1.0", "v9.15.1.0", ...]
# ═══════════════════════════════════════════════════════════════════════
def harvest_ontap_github():
    """Fetch ONTAP version info from GitHub NetApp/ontap-rest-python releases."""
    versions = {"latestGA": None, "latestByBranch": {}, "source": "github.com"}
    data = fetch_json("https://api.github.com/repos/NetApp/ontap-rest-python/releases?per_page=30")
    if not data or not isinstance(data, list):
        return versions
    
    ontap_versions = []
    for rel in data:
        tag = rel.get("tag_name", "").lstrip("v")
        if re.match(r'^9\.\d{1,2}\.\d+', tag):
            ontap_versions.append(tag)
    
    if not ontap_versions:
        return versions
    
    def vkey(v):
        return tuple(int(x) for x in re.findall(r'\d+', v))
    
    ontap_versions.sort(key=vkey, reverse=True)
    
    latest = ontap_versions[0]
    parts = latest.split('.')
    if len(parts) == 4 and parts[3] == '0':
        latest = '.'.join(parts[:3])
    versions["latestGA"] = latest
    
    for v in ontap_versions:
        parts = v.split('.')
        if len(parts) >= 3:
            branch = '.'.join(parts[:3])
            if branch not in versions["latestByBranch"]:
                versions["latestByBranch"][branch] = branch
    
    if versions["latestGA"]:
        print(f"  [FW-HARVEST] GitHub: latestGA={versions['latestGA']}, {len(versions['latestByBranch'])} branches")
    return versions

# ═══════════════════════════════════════════════════════════════════════
#  Source 4: NetApp Harvest GitHub Pages — ONTAP compat matrix
# ═══════════════════════════════════════════════════════════════════════
def harvest_ontap_harvest_docs():
    """Fetch ONTAP versions from NetApp Harvest documentation."""
    versions = {"latestGA": None, "latestByBranch": {}, "source": "netapp.github.io"}
    html = fetch_url("https://netapp.github.io/harvest/latest/prepare-cdot-clusters/")
    if not html:
        return versions
    
    ontap_raw = re.findall(r'\b(9\.(?:[3-9]|1[0-9])\.\d{1})\b', html)
    if not ontap_raw:
        return versions
    
    def vkey(v):
        return tuple(int(x) for x in re.findall(r'\d+', v))
    
    ontap_versions = sorted(set(ontap_raw), key=vkey, reverse=True)
    versions["latestGA"] = ontap_versions[0]
    
    for v in ontap_versions:
        if v not in versions["latestByBranch"]:
            versions["latestByBranch"][v] = v
    
    if versions["latestGA"]:
        print(f"  [FW-HARVEST] Harvest docs: latestGA={versions['latestGA']}, {len(versions['latestByBranch'])} branches")
    return versions

# ═══════════════════════════════════════════════════════════════════════
#  Source 5: docs.netapp.com (legacy — may return 403 due to WAF)
# ═══════════════════════════════════════════════════════════════════════
def harvest_ontap_docs():
    """Legacy: fetch ONTAP versions from docs.netapp.com release notes."""
    versions = {"latestGA": None, "latestByBranch": {}, "source": "docs.netapp.com"}
    html = fetch_url("https://docs.netapp.com/us-en/ontap/release-notes/index.html")
    if not html:
        return versions
    
    ga_match = re.search(r'What[^\w]*s new in ONTAP (9\.\d{1,2}\.\d+)', html, re.IGNORECASE)
    if ga_match:
        versions["latestGA"] = ga_match.group(1)
        
    p_releases = re.findall(r'\b(9\.\d{1,2}\.\d+P\d+)\b', html)
    for p in p_releases:
        branch_match = re.match(r'(9\.\d{1,2}\.\d+)P', p)
        if branch_match:
            branch = branch_match.group(1)
            if branch not in versions["latestByBranch"] or version_greater(p, versions["latestByBranch"][branch]):
                versions["latestByBranch"][branch] = p

    return versions

def harvest_trident_github():
    """Fetch latest Trident release from GitHub API."""
    versions = {"latestGA": None, "source": "github.com/NetApp/trident"}
    data = fetch_json("https://api.github.com/repos/NetApp/trident/releases?per_page=10")
    if not data or not isinstance(data, list):
        return versions
    
    for rel in data:
        if rel.get("prerelease"):
            continue
        tag = rel.get("tag_name", "").lstrip("v")
        if tag and not versions["latestGA"]:
            versions["latestGA"] = tag
            break
    return versions

def harvest_harvest_github():
    """Fetch latest NetApp Harvest release from GitHub API."""
    versions = {"latestGA": None, "source": "github.com/NetApp/harvest"}
    data = fetch_json("https://api.github.com/repos/NetApp/harvest/releases?per_page=10")
    if not data or not isinstance(data, list):
        return versions
    
    for rel in data:
        if rel.get("prerelease") or "nightly" in rel.get("tag_name", "").lower():
            continue
        tag = rel.get("tag_name", "").lstrip("v")
        if tag and not versions["latestGA"]:
            versions["latestGA"] = tag
            break
    return versions

def harvest_snapcenter_docs():
    """Best-effort scrape for SnapCenter version."""
    versions = {"latestGA": None, "source": "docs.netapp.com"}
    html = fetch_url("https://docs.netapp.com/us-en/snapcenter/release-notes/release-notes.html")
    if not html:
        html = fetch_url("https://docs.netapp.com/us-en/snapcenter/")
    if html:
        matches = re.findall(r'SnapCenter\s+(\d+\.\d+(?:\.\d+)?)', html, re.IGNORECASE)
        for m in matches:
            if version_greater(m, versions["latestGA"]):
                versions["latestGA"] = m
    return versions

def harvest_storagegrid():
    """Fetch StorageGRID version."""
    versions = {"latestGA": None, "source": "docs.netapp.com"}
    html = fetch_url("https://docs.netapp.com/us-en/storagegrid/release-notes/index.html")
    if html:
        matches = re.findall(r'StorageGRID\s+(\d+\.\d+(?:\.\d+)?)', html, re.IGNORECASE)
        for m in matches:
            if version_greater(m, versions["latestGA"]):
                versions["latestGA"] = m
    return versions

def harvest_host_utilities():
    """Fetch Host Utilities version."""
    versions = {"latestGA": None, "source": "docs.netapp.com"}
    html = fetch_url("https://docs.netapp.com/us-en/ontap-sanhost/")
    if html:
        matches = re.findall(r'Host Utilities\s+(\d+\.\d+)', html, re.IGNORECASE)
        for m in matches:
            if version_greater(m, versions["latestGA"]):
                versions["latestGA"] = m
    return versions

def harvest_ontap_eol_dates():
    """Fetch ONTAP branch EOL dates from endoflife.date."""
    result = {"branches": {}, "supportedBranches": [], "eolBranches": []}
    data = fetch_json("https://endoflife.date/api/netapp-ontap.json")
    if not data or not isinstance(data, list):
        return result
    
    now = datetime.now()
    
    for entry in data:
        cycle = entry.get("cycle")
        eol = entry.get("eol")
        releaseDate = entry.get("releaseDate")
        lts = entry.get("lts", False)
        
        if not cycle or not eol or not isinstance(eol, str):
            continue
            
        result["branches"][cycle] = {
            "eol": eol,
            "releaseDate": releaseDate,
            "lts": lts
        }
        
        try:
            eol_date = datetime.strptime(eol, "%Y-%m-%d")
            if eol_date > now:
                result["supportedBranches"].append(cycle)
            else:
                result["eolBranches"].append(cycle)
        except ValueError:
            pass
            
    return result

def harvest_cvo_version():
    """Fetch Cloud Volumes ONTAP version."""
    versions = {"latestGA": None, "source": "docs.netapp.com"}
    html = fetch_url("https://docs.netapp.com/us-en/cloud-volumes-ontap-relnotes/")
    if html:
        matches = re.findall(r'Cloud Volumes ONTAP\s+(\d+\.\d+\.\d+)', html, re.IGNORECASE)
        for m in matches:
            if version_greater(m, versions["latestGA"]):
                versions["latestGA"] = m
    return versions

def harvest_santricity():
    """Fetch SANtricity versions from docs.netapp.com (fallback: web search)."""
    versions = {"latestGA": None}
    
    # Try docs.netapp.com first
    html = fetch_url("https://docs.netapp.com/us-en/e-series/index.html")
    if html:
        matches = re.findall(r'(?:SANtricity|OS)\s+(1[12]\.\d{2}(?:\.\d+|R\d+)?)', html, re.IGNORECASE)
        for m in matches:
            if version_greater(m, versions["latestGA"]):
                versions["latestGA"] = m
    
    # Fallback: try E-Series SANtricity docs whats-new page
    if not versions["latestGA"]:
        html2 = fetch_url("https://docs.netapp.com/us-en/e-series-santricity/whats-new.html")
        if html2:
            matches2 = re.findall(r'\b(1[12]\.\d{2}(?:\.\d+)?)\b', html2)
            for m in matches2:
                if version_greater(m, versions["latestGA"]):
                    versions["latestGA"] = m
    
    return versions

def harvest_switches():
    """Fetch switch firmware versions — try docs.netapp.com, fallback to static."""
    versions = {}
    html = fetch_url("https://docs.netapp.com/us-en/ontap-systems-switches/")
    
    if html:
        nxos_matches = re.findall(r'NX-OS\s+(\d+\.\d+(?:\.\d+|\([A-Za-z0-9]+\)))', html)
        for m in nxos_matches:
            versions["Cisco NX-OS"] = m
            break

        fos_matches = re.findall(r'Fabric OS\s+(\d+\.\d+\.\d+[a-z]?)', html, re.IGNORECASE)
        if fos_matches:
            versions["Brocade FOS"] = fos_matches[0]
            
        efos_matches = re.findall(r'EFOS\s+(\d+\.\d+\.\d+\.\d+)', html, re.IGNORECASE)
        if efos_matches:
            versions["Broadcom EFOS"] = efos_matches[0]
        
    return versions


def harvest_ontap():
    """Multi-source ONTAP version harvester with cascading fallbacks.
    
    Tries sources in order of reliability/accessibility:
      1. endoflife.date API (most reliable, structured JSON)
      2. PyPI netapp-ontap package (SDK tracks ONTAP versions 1:1)
      3. GitHub NetApp/ontap-rest-python releases
      4. NetApp Harvest docs (GitHub Pages, no WAF)
      5. docs.netapp.com (may be WAF-blocked — legacy fallback)
    
    Merges results from all successful sources, picking the highest versions.
    """
    # Try all sources, merge results
    sources = [
        ("endoflife.date", harvest_ontap_endoflife),
        ("PyPI", harvest_ontap_pypi),
        ("GitHub", harvest_ontap_github),
        ("Harvest docs", harvest_ontap_harvest_docs),
        ("docs.netapp.com", harvest_ontap_docs),
    ]
    
    merged = {"latestGA": None, "latestByBranch": {}}
    successful_sources = []
    
    for name, fn in sources:
        try:
            result = fn()
            if result.get("latestGA"):
                successful_sources.append(name)
                # Take the highest latestGA
                if version_greater(result["latestGA"], merged["latestGA"]):
                    merged["latestGA"] = result["latestGA"]
                # Merge branch data
                for branch, ver in result.get("latestByBranch", {}).items():
                    if branch not in merged["latestByBranch"] or version_greater(ver, merged["latestByBranch"][branch]):
                        merged["latestByBranch"][branch] = ver
        except Exception as e:
            print(f"  [FW-HARVEST] {name} failed: {e}")
    
    if successful_sources:
        print(f"  [FW-HARVEST] ONTAP merged from {len(successful_sources)} sources: {', '.join(successful_sources)}")
        print(f"  [FW-HARVEST]   latestGA={merged['latestGA']}, branches={list(merged['latestByBranch'].keys())}")
    else:
        print("  [FW-HARVEST] WARNING: All ONTAP sources failed!")
    
    return merged


def run_harvest(baselines_path=None, dry_run=False, ontap_only=False, spbmc_only=False):
    if baselines_path is None:
        baselines_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'firmware_baselines.json')
        
    try:
        with open(baselines_path, 'r', encoding='utf-8') as f:
            baselines = json.load(f)
    except Exception as e:
        print(f"Error loading baselines: {e}")
        return {}

    changes = {}

    # ONTAP (multi-source)
    if not spbmc_only:
        print("Harvesting ONTAP versions (multi-source)...")
        ontap_data = harvest_ontap()
        if ontap_data.get("latestGA") and version_greater(ontap_data["latestGA"], baselines.get("ontap", {}).get("latestGA")):
            changes["ontap.latestGA"] = {"old": baselines.get("ontap", {}).get("latestGA"), "new": ontap_data["latestGA"]}
            if "ontap" not in baselines:
                baselines["ontap"] = {}
            baselines["ontap"]["latestGA"] = ontap_data["latestGA"]
            
        for branch, latest_p in ontap_data.get("latestByBranch", {}).items():
            current_p = baselines.get("ontap", {}).get("latestByBranch", {}).get(branch)
            if version_greater(latest_p, current_p):
                changes[f"ontap.latestByBranch.{branch}"] = {"old": current_p, "new": latest_p}
                if "ontap" not in baselines:
                    baselines["ontap"] = {}
                if "latestByBranch" not in baselines["ontap"]:
                    baselines["ontap"]["latestByBranch"] = {}
                baselines["ontap"]["latestByBranch"][branch] = latest_p

        print("Harvesting ONTAP EOL dates...")
        eol_data = harvest_ontap_eol_dates()
        if eol_data.get("supportedBranches"):
            current_supported = baselines.get("ontap", {}).get("supportedBranches", [])
            if set(eol_data["supportedBranches"]) != set(current_supported):
                changes["ontap.supportedBranches"] = {"old": current_supported, "new": eol_data["supportedBranches"]}
                if "ontap" not in baselines:
                    baselines["ontap"] = {}
                baselines["ontap"]["supportedBranches"] = eol_data["supportedBranches"]
                baselines["ontap"]["eolBranches"] = eol_data["eolBranches"]

    # Trident
    if not spbmc_only:
        print("Harvesting Trident version...")
        trident_data = harvest_trident_github()
        if trident_data.get("latestGA"):
            current = baselines.get("trident", {}).get("latestGA")
            if version_greater(trident_data["latestGA"], current):
                changes["trident.latestGA"] = {"old": current, "new": trident_data["latestGA"]}
                if "trident" not in baselines:
                    baselines["trident"] = {}
                baselines["trident"]["latestGA"] = trident_data["latestGA"]

    # Harvest
    if not spbmc_only:
        print("Harvesting NetApp Harvest version...")
        harvest_gh_data = harvest_harvest_github()
        if harvest_gh_data.get("latestGA"):
            current = baselines.get("harvest", {}).get("latestGA")
            if version_greater(harvest_gh_data["latestGA"], current):
                changes["harvest.latestGA"] = {"old": current, "new": harvest_gh_data["latestGA"]}
                if "harvest" not in baselines:
                    baselines["harvest"] = {}
                baselines["harvest"]["latestGA"] = harvest_gh_data["latestGA"]

    # SnapCenter
    if not spbmc_only:
        print("Harvesting SnapCenter version...")
        sc_data = harvest_snapcenter_docs()
        if sc_data.get("latestGA"):
            current = baselines.get("snapcenter", {}).get("latestGA")
            if version_greater(sc_data["latestGA"], current):
                changes["snapcenter.latestGA"] = {"old": current, "new": sc_data["latestGA"]}
                if "snapcenter" not in baselines:
                    baselines["snapcenter"] = {}
                baselines["snapcenter"]["latestGA"] = sc_data["latestGA"]

    # StorageGRID
    if not spbmc_only:
        print("Harvesting StorageGRID version...")
        sg_data = harvest_storagegrid()
        if sg_data.get("latestGA"):
            current = baselines.get("storagegrid", {}).get("latestGA")
            if version_greater(sg_data["latestGA"], current):
                changes["storagegrid.latestGA"] = {"old": current, "new": sg_data["latestGA"]}
                if "storagegrid" not in baselines:
                    baselines["storagegrid"] = {}
                baselines["storagegrid"]["latestGA"] = sg_data["latestGA"]

    # Host Utilities
    if not spbmc_only:
        print("Harvesting Host Utilities version...")
        hu_data = harvest_host_utilities()
        if hu_data.get("latestGA"):
            current = baselines.get("host_utilities", {}).get("latestGA")
            if version_greater(hu_data["latestGA"], current):
                changes["host_utilities.latestGA"] = {"old": current, "new": hu_data["latestGA"]}
                if "host_utilities" not in baselines:
                    baselines["host_utilities"] = {}
                baselines["host_utilities"]["latestGA"] = hu_data["latestGA"]

    # CVO
    if not spbmc_only:
        print("Harvesting Cloud Volumes ONTAP version...")
        cvo_data = harvest_cvo_version()
        if cvo_data.get("latestGA"):
            current = baselines.get("cvo", {}).get("latestGA")
            if version_greater(cvo_data["latestGA"], current):
                changes["cvo.latestGA"] = {"old": current, "new": cvo_data["latestGA"]}
                if "cvo" not in baselines:
                    baselines["cvo"] = {}
                baselines["cvo"]["latestGA"] = cvo_data["latestGA"]

    if ontap_only or spbmc_only:
        pass
    else:
        print("Harvesting SANtricity versions...")
        san_data = harvest_santricity()
        if san_data.get("latestGA") and version_greater(san_data["latestGA"], baselines.get("santricity", {}).get("latestGA")):
            changes["santricity.latestGA"] = {"old": baselines.get("santricity", {}).get("latestGA"), "new": san_data["latestGA"]}
            baselines["santricity"]["latestGA"] = san_data["latestGA"]

        print("Harvesting Switch versions...")
        switches_data = harvest_switches()
        for sw_type, sw_ver in switches_data.items():
            if sw_type in baselines.get("switches", {}):
                current_ver = baselines["switches"][sw_type].get("recommended")
                if version_greater(sw_ver, current_ver):
                    changes[f"switches.{sw_type}.recommended"] = {"old": current_ver, "new": sw_ver}
                    baselines["switches"][sw_type]["recommended"] = sw_ver

    if changes:
        baselines["_lastUpdated"] = datetime.now().strftime("%Y-%m-%d")
        for k, v in changes.items():
            print(f"Update found: {k} changed from {v['old']} to {v['new']}")
            
        if not dry_run:
            with open(baselines_path, 'w', encoding='utf-8') as f:
                json.dump(baselines, f, indent=2)
                f.write('\n')  # Ensure trailing newline
            print(f"Successfully updated {baselines_path}")
        else:
            print("Dry run: Changes not written to disk.")
    else:
        print("No new versions found.")

    return changes

def scheduled_harvest(data_dir):
    """
    Called from server.py in a background thread.
    Runs the harvest, updates baselines in memory if changed.
    """
    baselines_path = os.path.join(data_dir, 'firmware_baselines.json')
    changes = run_harvest(baselines_path=baselines_path, dry_run=False)
    return changes

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automated firmware baseline harvester (multi-source)")
    parser.add_argument("--dry-run", action="store_true", help="Report only, no writes")
    parser.add_argument("--ontap-only", action="store_true", help="Only check ONTAP versions")
    parser.add_argument("--spbmc-only", action="store_true", help="Only check SP/BMC versions")
    parser.add_argument("--all", action="store_true", help="Run all harvest sources")
    
    args = parser.parse_args()
    
    if args.all:
        args.ontap_only = False
        args.spbmc_only = False
        
    run_harvest(dry_run=args.dry_run, ontap_only=args.ontap_only, spbmc_only=args.spbmc_only)
