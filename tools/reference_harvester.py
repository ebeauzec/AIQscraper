#!/usr/bin/env python3
"""
Reference Library Harvester — Comprehensive multi-source knowledge discovery engine.

Automatically discovers, scrapes, and enriches the AIQscraper reference database
from all public NetApp data sources using fuzzy-logic matching and structured APIs.

Data Source Tiers:
  Tier 1: docs.netapp.com, github.com/NetAppDocs, kb.netapp.com,
          security.netapp.com, community.netapp.com, devnet.netapp.com
  Tier 2: github.com/NetApp, PyPI, Ansible Galaxy, Terraform Registry, Helm
  Tier 3: AWS FSx ONTAP, Azure NetApp Files, Google Cloud NetApp Volumes,
          Cisco FlexPod CVDs

Usage:
  python reference_harvester.py                  # full harvest
  python reference_harvester.py --dry-run        # report only
  python reference_harvester.py --eoa-only       # EOA data only
  python reference_harvester.py --imt-only       # IMT versions only
  python reference_harvester.py --advisory-only  # advisories only
  python reference_harvester.py --docs-only      # documentation discovery only
  python reference_harvester.py --ecosystem-only # PyPI/Galaxy/Terraform/Helm only
"""

import os
import sys
import json
import re
import time
import urllib.request
import urllib.error
import urllib.parse
import argparse
import logging
from datetime import datetime, date
from html.parser import HTMLParser

# ============================================================================
# Configuration & Logging
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
GITHUB_UA = "AIQscraper-ReferenceHarvester/1.0"

# GitHub Personal Access Token — raises API rate limit from 60 to 5,000 req/hr.
# Set via: (1) env var GITHUB_TOKEN, (2) aiq_config.json "githubToken" field,
#          (3) CLI --github-token, or (4) programmatic set_github_token().
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()

def set_github_token(token):
    """Set the GitHub PAT at runtime (called from server.py during enrichment)."""
    global GITHUB_TOKEN
    if token and token.strip():
        GITHUB_TOKEN = token.strip()

# Rate limiting — shared across all harvest functions
RATE_LIMIT_DELAY = 2.0  # seconds between requests
_LAST_REQUEST_TIME = 0.0

# ============================================================================
# Tier 1 Source Registry: docs.netapp.com doc-set roots
# ============================================================================
DOCS_NETAPP_DOCSETS = {
    # Core ONTAP
    'ontap':                     'ONTAP Administration',
    'ontap-cli':                 'ONTAP CLI Command Reference',
    'ontap-automation':          'ONTAP Automation',
    'ontap-restapi':             'ONTAP REST API (latest)',
    'ontap-systems':             'ONTAP Systems — Hardware Install/FRU',
    'ontap-systems-switches':    'Cluster/Storage/Mgmt Switch Config',
    'ontap-metrocluster':        'MetroCluster',
    'ontap-sanhost':             'SAN Host OS Config Guides',
    'ontap-apps-dbs':            'Oracle/SQL/SAP Best Practices',
    'ontap-security-hardening':  'Security Hardening Guide',
    'ontap-ems-reference':       'EMS Event Catalogue',
    # StorageGRID
    'storagegrid':               'StorageGRID (current)',
    'storagegrid-appliances':    'StorageGRID Appliances',
    # E-Series
    'e-series':                  'E-Series',
    'e-series-santricity':       'SANtricity + Web Services REST API',
    # SolidFire / Element
    'element-software':          'Element/SolidFire API Reference',
    # Trident / Kubernetes
    'trident':                   'Astra Trident CSI Driver',
    # BlueXP / Cloud
    'bluexp-setup-admin':        'BlueXP Setup & Admin',
    'bluexp-cloud-volumes-ontap':'BlueXP Cloud Volumes ONTAP',
    'bluexp-ransomware-protection':'BlueXP Ransomware Protection',
    'bluexp-backup-recovery':    'BlueXP Backup & Recovery',
    # Management & Monitoring
    'active-iq-unified-manager': 'AIQUM REST API',
    'data-infrastructure-insights':'Data Infrastructure Insights',
    # Integrations
    'snapcenter':                'SnapCenter',
    'ontap-tools-vmware-vsphere':'ONTAP Tools for VMware vSphere',
    # Solutions
    'netapp-solutions':          'NVAs, Reference Architectures',
    # IMT
    'interoperability-matrix-tool':'IMT Help Docs',
}

# Versioned ONTAP REST API doc-sets (for tracking API coverage across releases)
ONTAP_RESTAPI_VERSIONS = [
    'ontap-restapi-9191', 'ontap-restapi-9181', 'ontap-restapi-9171',
    'ontap-restapi-9161', 'ontap-restapi-9151', 'ontap-restapi-9141',
    'ontap-restapi-9131', 'ontap-restapi-9121', 'ontap-restapi-9111',
    'ontap-restapi-991',
]

# ============================================================================
# Tier 2 Source Registry: GitHub, PyPI, Ansible, Terraform
# ============================================================================
GITHUB_ORGS = {
    'NetApp':            'NetApp Core SDKs & Tools',
    'NetApp-Automation': 'Ansible/Terraform Reference Automation',
    'NetAppDocs':        'Documentation Source (AsciiDoc)',
}

PYPI_PACKAGES = {
    'netapp-ontap':          {'product': 'ONTAP Python SDK', 'signal': 'ontap_sdk'},
    'solidfire-sdk-python':  {'product': 'SolidFire Python SDK', 'signal': 'solidfire'},
}

ANSIBLE_COLLECTIONS = {
    'netapp.ontap':         {'product': 'ONTAP Ansible Collection'},
    'netapp.storagegrid':   {'product': 'StorageGRID Ansible Collection'},
    'netapp.um_info':       {'product': 'Unified Manager Ansible Collection'},
    'netapp.cloudmanager':  {'product': 'Cloud Manager Ansible Collection'},
}

TERRAFORM_PROVIDERS = {
    'NetApp/netapp-ontap':       {'product': 'ONTAP Terraform Provider'},
    'NetApp/netapp-cloudmanager':{'product': 'Cloud Manager Terraform Provider'},
}

# ============================================================================
# Tier 3 Source Registry: Cloud Provider Docs
# ============================================================================
CLOUD_DOCS = {
    'aws_fsx_ontap': {
        'name': 'Amazon FSx for NetApp ONTAP',
        'url': 'https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/',
        'pattern': r'FSx.*?ONTAP.*?(\d+\.\d+)',
    },
    'azure_anf': {
        'name': 'Azure NetApp Files',
        'url': 'https://learn.microsoft.com/en-us/azure/azure-netapp-files/',
        'pattern': r'Azure NetApp Files',
    },
    'gcp_gcnv': {
        'name': 'Google Cloud NetApp Volumes',
        'url': 'https://cloud.google.com/netapp/volumes/docs',
        'pattern': r'NetApp Volumes',
    },
}

# ============================================================================
# HTTP Utilities
# ============================================================================

def _rate_limit():
    """Enforce minimum delay between HTTP requests."""
    global _LAST_REQUEST_TIME
    now = time.time()
    elapsed = now - _LAST_REQUEST_TIME
    if elapsed < RATE_LIMIT_DELAY:
        time.sleep(RATE_LIMIT_DELAY - elapsed)
    _LAST_REQUEST_TIME = time.time()


def _fetch_url(url, is_json=False, timeout=15, ua=None):
    """Fetch URL content with rate limiting, error handling, and optional JSON parsing."""
    _rate_limit()
    logger.info(f"Fetching {url}")
    headers = {'User-Agent': ua or USER_AGENT}
    if is_json:
        headers['Accept'] = 'application/json'
    # Inject GitHub PAT for api.github.com requests (raises rate limit 60 → 5,000/hr)
    if GITHUB_TOKEN and 'api.github.com' in url:
        headers['Authorization'] = f'Bearer {GITHUB_TOKEN}'
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode('utf-8', errors='replace')
            if is_json:
                return json.loads(content)
            return content
    except urllib.error.HTTPError as e:
        logger.warning(f"HTTPError {e.code} for {url}")
    except urllib.error.URLError as e:
        logger.warning(f"URLError for {url}: {e.reason}")
    except Exception as e:
        logger.warning(f"Error fetching {url}: {e}")
    return {} if is_json else ""


class _LinkExtractor(HTMLParser):
    """Extract href links and their text from HTML."""
    def __init__(self):
        super().__init__()
        self.links = []  # list of (href, text)
        self._current_href = None
        self._current_text = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href')
            if href:
                self._current_href = href
                self._current_text = []

    def handle_data(self, data):
        if self._current_href is not None:
            self._current_text.append(data.strip())

    def handle_endtag(self, tag):
        if tag == 'a' and self._current_href is not None:
            text = ' '.join(self._current_text).strip()
            self.links.append((self._current_href, text))
            self._current_href = None
            self._current_text = []


def _extract_links(html):
    """Extract all (href, text) tuples from HTML."""
    parser = _LinkExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    return parser.links


# ============================================================================
# TIER 1 HARVESTERS
# ============================================================================

def harvest_eoa_announcements(existing_eoa):
    """Scrape docs.netapp.com/us-en/ontap-systems/endofavail/ for EOA data.

    Parses EOA index page and individual model pages for:
    - Model names, EOA dates, EOS dates, replacement platforms
    """
    logger.info("Starting EOA harvesting...")
    results = {"platforms": [], "dates": {}, "switches": [], "_changes": []}
    existing_platforms = set((p or '').upper() for p in (existing_eoa.get('platforms') or []))
    existing_dates = existing_eoa.get('dates') or {}

    base_url = "https://docs.netapp.com/us-en/ontap-systems/endofavail/"
    content = _fetch_url(base_url)
    if not content:
        return results

    links = _extract_links(content)
    eoa_links = []
    for href, text in links:
        if 'end-of-avail' in href.lower() or 'eoa' in href.lower():
            if href.endswith('.html'):
                full_url = href if href.startswith('http') else f"{base_url}{href}"
                eoa_links.append((full_url, text))

    # Parse each EOA page for structured data
    eoa_date_re = re.compile(
        r'end[\s-]*of[\s-]*availability.*?'
        r'(\d{4}[-/]\d{2}(?:[-/]\d{2})?|\w+\s+\d{4})',
        re.IGNORECASE
    )
    eos_date_re = re.compile(
        r'end[\s-]*of[\s-]*support.*?'
        r'(\d{4}[-/]\d{2}(?:[-/]\d{2})?|\w+\s+\d{4})',
        re.IGNORECASE
    )
    model_re = re.compile(
        r'(AFF\s*[A-Z]?\d+\w*|FAS\s*\d+\w*|ASA\s*[A-Z]?\d+\w*|AFX\s*\d+\w*)',
        re.IGNORECASE
    )
    replacement_re = re.compile(
        r'replacement.*?((?:AFF|FAS|ASA|AFX)\s+\w+(?:\s*/\s*(?:AFF|FAS|ASA|AFX)\s+\w+)*)',
        re.IGNORECASE
    )

    for eoa_url, link_text in eoa_links[:20]:  # limit to 20 pages
        try:
            page = _fetch_url(eoa_url, timeout=10)
            if not page:
                continue

            # Extract model from page title or link text
            models = model_re.findall(link_text + ' ' + page[:2000])
            eoa_dates = eoa_date_re.findall(page)
            eos_dates = eos_date_re.findall(page)
            replacements = replacement_re.findall(page)

            for model_raw in models:
                model = model_raw.strip().upper()
                if model not in existing_platforms:
                    results["platforms"].append(model)
                    results["_changes"].append(f"New EOA platform: {model}")

                if model not in existing_dates:
                    date_entry = {}
                    if eoa_dates:
                        date_entry['eoaDate'] = eoa_dates[0]
                    if eos_dates:
                        date_entry['eosDate'] = eos_dates[0]
                    if replacements:
                        date_entry['replacement'] = replacements[0]
                    if date_entry:
                        results["dates"][model] = date_entry
                        results["_changes"].append(
                            f"New EOA dates for {model}: "
                            f"EOA={date_entry.get('eoaDate','?')}, "
                            f"EOS={date_entry.get('eosDate','?')}"
                        )
        except Exception as e:
            logger.warning(f"Error parsing EOA page {eoa_url}: {e}")

    return results


def harvest_imt_versions(existing_imt):
    """Check latest versions of ALL integration products from official sources.

    Sources: GitHub API, PyPI, vendor documentation, fuzzy HTML scraping.
    """
    logger.info("Starting IMT version harvesting...")
    updates = {}

    # ---- GitHub API sources (structured JSON) ----

    github_products = {
        'trident': {
            'repo': 'NetApp/trident',
            'imt_key': 'trident',
            'strip_prefix': 'v',
        },
        'harvest': {
            'repo': 'NetApp/harvest',
            'imt_key': 'harvest',
            'strip_prefix': 'v',
            'skip_nightly': True,
        },
    }

    for prod_name, cfg in github_products.items():
        try:
            url = f"https://api.github.com/repos/{cfg['repo']}/releases?per_page=10"
            data = _fetch_url(url, is_json=True, ua=GITHUB_UA)
            if data and isinstance(data, list):
                for rel in data:
                    if rel.get('prerelease'):
                        continue
                    if cfg.get('skip_nightly') and 'nightly' in (rel.get('name') or '').lower():
                        continue
                    tag = (rel.get('tag_name') or '').lstrip(cfg.get('strip_prefix', ''))
                    if tag:
                        current = existing_imt.get(cfg['imt_key'], {}).get('currentRecommended')
                        if tag != current:
                            updates[cfg['imt_key']] = {
                                'currentRecommended': tag,
                                'source': f"github.com/{cfg['repo']}",
                                'published_at': rel.get('published_at', '')[:10],
                            }
                        break
        except Exception as e:
            logger.warning(f"GitHub harvest failed for {prod_name}: {e}")

    # ---- PyPI sources ----

    for pkg_name, pkg_info in PYPI_PACKAGES.items():
        try:
            data = _fetch_url(f"https://pypi.org/pypi/{pkg_name}/json", is_json=True)
            if data and 'info' in data:
                ver = data['info'].get('version')
                if ver:
                    current = existing_imt.get(pkg_name, {}).get('currentRecommended')
                    if ver != current:
                        updates[pkg_name] = {
                            'currentRecommended': ver,
                            'source': f"pypi.org/{pkg_name}",
                            'product': pkg_info['product'],
                        }
        except Exception as e:
            logger.warning(f"PyPI harvest failed for {pkg_name}: {e}")

    # ---- Vendor documentation (fuzzy HTML scraping) ----

    vendor_scrapes = [
        {
            'key': 'snapcenter',
            'url': 'https://docs.netapp.com/us-en/snapcenter/release-notes/release-notes.html',
            'pattern': r'SnapCenter\s+(?:Software\s+)?(\d+\.\d+(?:\.\d+)?)',
        },
        {
            'key': 'brocade_fos',
            'url': 'https://docs.netapp.com/us-en/ontap-systems-switches/',
            'pattern': r'Fabric\s*OS.*?(\d+\.\d+\.\d+)',
        },
        {
            'key': 'cisco_nxos',
            'url': 'https://docs.netapp.com/us-en/ontap-systems-switches/',
            'pattern': r'NX-OS.*?(\d+\.\d+(?:\(\d+\)|\.\d+)?)',
        },
        {
            'key': 'broadcom_efos',
            'url': 'https://docs.netapp.com/us-en/ontap-systems-switches/',
            'pattern': r'EFOS.*?(\d+\.\d+\.\d+\.\d+)',
        },
    ]

    # Cache fetched pages to avoid re-fetching the same URL
    _page_cache = {}
    for scrape in vendor_scrapes:
        try:
            url = scrape['url']
            if url not in _page_cache:
                _page_cache[url] = _fetch_url(url, timeout=12)
            html = _page_cache[url]
            if html:
                match = re.search(scrape['pattern'], html, re.IGNORECASE)
                if match:
                    ver = match.group(1)
                    current = existing_imt.get(scrape['key'], {}).get('currentRecommended')
                    if ver and ver != current:
                        updates[scrape['key']] = {
                            'currentRecommended': ver,
                            'source': url,
                        }
        except Exception as e:
            logger.warning(f"Vendor scrape failed for {scrape['key']}: {e}")

    # ---- Veeam (their own support matrix) ----
    try:
        veeam_urls = [
            'https://www.veeam.com/kb2930',
            'https://www.veeam.com/veeam_backup_12_3_release_notes_rn.html',
        ]
        for vurl in veeam_urls:
            html = _fetch_url(vurl, timeout=10)
            if html:
                m = re.search(r'Veeam.*?(\d+\.\d+(?:\.\d+)?)', html, re.IGNORECASE)
                if m:
                    ver = m.group(1)
                    current = existing_imt.get('veeam', {}).get('currentRecommended')
                    if ver and ver != current:
                        updates['veeam'] = {'currentRecommended': ver, 'source': vurl}
                    break
    except Exception:
        pass

    # ---- Commvault ----
    try:
        html = _fetch_url('https://documentation.commvault.com/', timeout=10)
        if html:
            m = re.search(r'Commvault.*?(\d{4}(?:\s*[eE]\d)?)', html, re.IGNORECASE)
            if m:
                ver = m.group(1).strip()
                current = existing_imt.get('commvault', {}).get('currentRecommended')
                if ver and ver != current:
                    updates['commvault'] = {'currentRecommended': ver, 'source': 'documentation.commvault.com'}
    except Exception:
        pass

    # ---- Veritas NetBackup ----
    try:
        url = 'https://www.veritas.com/support/en_US/article.100040093'
        html = _fetch_url(url, timeout=10)
        if html:
            m = re.search(r'NetBackup\s+(\d+\.\d+(?:\.\d+)?)', html, re.IGNORECASE)
            if m:
                ver = m.group(1).strip()
                current = existing_imt.get('veritas_netbackup', {}).get('currentRecommended')
                if ver and ver != current:
                    updates['veritas_netbackup'] = {'currentRecommended': ver, 'source': url}
    except Exception:
        pass

    # ---- Veritas Backup Exec ----
    try:
        url = 'https://www.veritas.com/support/en_US/article.100040088'
        html = _fetch_url(url, timeout=10)
        if html:
            m = re.search(r'Backup\s+Exec\s+(\d+(?:\.\d+)?)', html, re.IGNORECASE)
            if m:
                ver = m.group(1).strip()
                current = existing_imt.get('veritas_backupexec', {}).get('currentRecommended')
                if ver and ver != current:
                    updates['veritas_backupexec'] = {'currentRecommended': ver, 'source': url}
    except Exception:
        pass

    # ---- VMware vSphere ----
    try:
        url = 'https://docs.vmware.com/en/VMware-vSphere/index.html'
        html = _fetch_url(url, timeout=10)
        if html:
            m = re.search(r'vSphere\s+(\d+\.\d+(?:\s*[Uu]\d+)?)', html, re.IGNORECASE)
            if m:
                ver = m.group(1).strip()
                current = existing_imt.get('vmware_vsphere', {}).get('currentRecommended')
                if ver and ver != current:
                    updates['vmware_vsphere'] = {'currentRecommended': ver, 'source': url}
    except Exception:
        pass

    # ---- Microsoft Hyper-V / Windows Server ----
    try:
        url = 'https://learn.microsoft.com/en-us/windows-server/get-started/whats-new-in-windows-server'
        html = _fetch_url(url, timeout=10)
        if html:
            m = re.search(r'Windows Server\s+(20\d{2}(?:\s*R2)?)', html, re.IGNORECASE)
            if m:
                ver = m.group(1).strip()
                current = existing_imt.get('hyperv', {}).get('currentRecommended')
                if ver and ver != current:
                    updates['hyperv'] = {'currentRecommended': ver, 'source': url}
    except Exception:
        pass

    # ---- Red Hat Virtualization ----
    try:
        url = 'https://docs.redhat.com/en/documentation/red_hat_virtualization/'
        html = _fetch_url(url, timeout=10)
        if html:
            m = re.search(r'Red Hat Virtualization\s+(\d+\.\d+)', html, re.IGNORECASE)
            if m:
                ver = m.group(1).strip()
                current = existing_imt.get('rhev', {}).get('currentRecommended')
                if ver and ver != current:
                    updates['rhev'] = {'currentRecommended': ver, 'source': url}
    except Exception:
        pass

    # ---- OpenStack ----
    try:
        urls = [
            'https://docs.openstack.org/cinder/latest/',
            'https://docs.openstack.org/manila/latest/'
        ]
        for url in urls:
            html = _fetch_url(url, timeout=10)
            if html:
                m = re.search(r'(Dalmatian|Epoxy|Flamingo|20\d{2}\.\d+)', html, re.IGNORECASE)
                if m:
                    ver = m.group(1).strip()
                    current = existing_imt.get('openstack', {}).get('currentRecommended')
                    if ver and ver != current:
                        updates['openstack'] = {'currentRecommended': ver, 'source': url}
                    break
    except Exception:
        pass

    # ---- Citrix Hypervisor ----
    try:
        url = 'https://docs.citrix.com/en-us/citrix-hypervisor'
        html = _fetch_url(url, timeout=10)
        if html:
            m = re.search(r'(?:Citrix\s+Hypervisor|XenServer)\s+(\d+\.\d+(?:\s*CU\d+)?)', html, re.IGNORECASE)
            if m:
                ver = m.group(1).strip()
                current = existing_imt.get('citrix_hypervisor', {}).get('currentRecommended')
                if ver and ver != current:
                    updates['citrix_hypervisor'] = {'currentRecommended': ver, 'source': url}
    except Exception:
        pass

    # ---- Proxmox VE ----
    try:
        url = 'https://pve.proxmox.com/wiki/Roadmap'
        html = _fetch_url(url, timeout=10)
        if html:
            m = re.search(r'Proxmox VE\s+(\d+\.\d+)', html, re.IGNORECASE)
            if m:
                ver = m.group(1).strip()
                current = existing_imt.get('proxmox_ve', {}).get('currentRecommended')
                if ver and ver != current:
                    updates['proxmox_ve'] = {'currentRecommended': ver, 'source': url}
    except Exception:
        pass

    # ---- Nutanix AHV ----
    try:
        url = 'https://portal.nutanix.com/page/documents/compatibility-interoperability-matrix/guestos'
        html = _fetch_url(url, timeout=10)
        if html:
            m = re.search(r'AHV\s+(\d+\.\d+(?:\.\d+)?)', html, re.IGNORECASE)
            if m:
                ver = m.group(1).strip()
                current = existing_imt.get('nutanix_ahv', {}).get('currentRecommended')
                if ver and ver != current:
                    updates['nutanix_ahv'] = {'currentRecommended': ver, 'source': url}
    except Exception:
        pass

    return updates


def harvest_advisories_from_psirt(existing_bulletin_ids=None):
    """Scrape security.netapp.com for new PSIRT advisories.

    Parses the advisory index for NTAP-* advisory IDs, then fetches
    each new advisory page to extract CVE, CVSS, severity, and products.
    """
    logger.info("Starting PSIRT advisory harvesting...")
    if existing_bulletin_ids is None:
        existing_bulletin_ids = set()

    base_url = "https://security.netapp.com/advisory/"
    content = _fetch_url(base_url)
    if not content:
        return []

    # Extract all advisory IDs from the index page
    all_ids = set(re.findall(r'ntap-\d{8}-\d{4}', content, re.IGNORECASE))
    new_ids = [aid for aid in all_ids if aid.upper() not in existing_bulletin_ids
               and aid.lower() not in existing_bulletin_ids]

    if not new_ids:
        logger.info("No new PSIRT advisories found.")
        return []

    logger.info(f"Found {len(new_ids)} potentially new advisories, checking top 10...")
    advisories = []

    for adv_id in sorted(new_ids, reverse=True)[:10]:
        try:
            adv_url = f"{base_url}{adv_id}/"
            adv_html = _fetch_url(adv_url, timeout=12)
            if not adv_html:
                continue

            cves = re.findall(r'CVE-\d{4}-\d{4,}', adv_html)
            cvss_match = re.search(r'CVSS.*?(\d+\.\d+)', adv_html, re.IGNORECASE)
            severity_match = re.search(
                r'(?:severity|rating|risk)\s*[:=]?\s*(critical|high|medium|low)',
                adv_html, re.IGNORECASE
            )
            # Extract title from <title> tag or <h1>
            title_match = re.search(r'<(?:title|h1)[^>]*>(.*?)</(?:title|h1)>', adv_html, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else adv_id

            # Extract affected products
            products = re.findall(
                r'(ONTAP|StorageGRID|SnapCenter|Trident|BlueXP|Active\s*IQ|'
                r'E-Series|SolidFire|Element|Cloud\s*Volumes\s*ONTAP)',
                adv_html, re.IGNORECASE
            )

            advisory = {
                'id': adv_id.upper(),
                'url': adv_url,
                'title': re.sub(r'<[^>]+>', '', title)[:200],
                'cves': list(set(cves)),
                'cvss': float(cvss_match.group(1)) if cvss_match else None,
                'severity': severity_match.group(1).lower() if severity_match else 'unknown',
                'products': list(set(p.strip() for p in products)),
                'discovered_at': datetime.utcnow().isoformat()[:10],
            }
            advisories.append(advisory)
        except Exception as e:
            logger.warning(f"Error parsing advisory {adv_id}: {e}")

    return advisories


def harvest_docs_netapp_index():
    """Discover documentation pages from docs.netapp.com doc-set roots.

    Probes each known doc-set root and extracts sidebar/TOC links to build
    a comprehensive index of available documentation.
    """
    logger.info("Starting docs.netapp.com index harvesting...")
    discovered = []
    doc_base = "https://docs.netapp.com/us-en/"

    for docset, description in DOCS_NETAPP_DOCSETS.items():
        try:
            url = f"{doc_base}{docset}/"
            html = _fetch_url(url, timeout=10)
            if not html:
                continue

            # Extract title
            title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else description

            # Count documentation pages (links to .html within same docset)
            page_links = re.findall(
                rf'href="(?:\.\.?/)?({re.escape(docset)}/[^"]*\.html|[^"]*\.html)"',
                html, re.IGNORECASE
            )
            page_count = len(set(page_links))

            discovered.append({
                'docset': docset,
                'url': url,
                'title': re.sub(r'<[^>]+>', '', title)[:150],
                'description': description,
                'page_count_estimate': page_count,
                'accessible': True,
            })
        except Exception as e:
            discovered.append({
                'docset': docset,
                'url': f"{doc_base}{docset}/",
                'description': description,
                'accessible': False,
                'error': str(e)[:100],
            })

    # Also check versioned REST API docs
    for ver_docset in ONTAP_RESTAPI_VERSIONS[:3]:  # check latest 3
        try:
            url = f"{doc_base}{ver_docset}/"
            html = _fetch_url(url, timeout=8)
            if html:
                ver_match = re.search(r'ONTAP\s+(\d+\.\d+(?:\.\d+)?)', html)
                discovered.append({
                    'docset': ver_docset,
                    'url': url,
                    'title': f"ONTAP REST API {ver_match.group(1) if ver_match else ver_docset}",
                    'description': 'Versioned REST API Reference',
                    'accessible': True,
                })
        except Exception:
            pass

    return discovered


def harvest_netappdocs_github():
    """Discover and index repos from github.com/NetAppDocs.

    This is the AsciiDoc source for docs.netapp.com — the single best
    scraping target. ~2000 repos with clean .adoc files, per-file history,
    sidebar TOC, and no rate limits.
    """
    logger.info("Starting NetAppDocs GitHub discovery...")
    repos = []

    # Page through the org's repos (up to 3 pages = 300 repos of the most recent)
    for page in range(1, 4):
        try:
            url = (f"https://api.github.com/orgs/NetAppDocs/repos"
                   f"?type=public&sort=updated&per_page=100&page={page}")
            data = _fetch_url(url, is_json=True, ua=GITHUB_UA)
            if not data or not isinstance(data, list):
                break
            for repo in data:
                repos.append({
                    'name': repo.get('name', ''),
                    'url': repo.get('html_url', ''),
                    'description': (repo.get('description') or '')[:200],
                    'updated_at': (repo.get('updated_at') or '')[:10],
                    'default_branch': repo.get('default_branch', 'main'),
                    'size_kb': repo.get('size', 0),
                    'language': repo.get('language'),
                })
            if len(data) < 100:
                break  # last page
        except Exception as e:
            logger.warning(f"NetAppDocs page {page} failed: {e}")
            break

    # Classify repos by product area
    product_repos = {}
    for repo in repos:
        name = repo['name'].lower()
        # Skip localized variants (e.g., ontap-fr, ontap-de)
        if re.search(r'-(?:fr|de|ja|ko|zh-cn|zh-tw|pt-br|es-es)$', name):
            continue

        category = 'other'
        if 'ontap' in name and 'storagegrid' not in name:
            category = 'ontap'
        elif 'storagegrid' in name:
            category = 'storagegrid'
        elif 'trident' in name:
            category = 'trident'
        elif 'snapcenter' in name:
            category = 'snapcenter'
        elif 'bluexp' in name or 'cloud' in name:
            category = 'cloud'
        elif 'e-series' in name or 'santricity' in name:
            category = 'eseries'
        elif 'active-iq' in name:
            category = 'activeiq'
        elif 'element' in name or 'solidfire' in name:
            category = 'solidfire'
        elif 'solution' in name:
            category = 'solutions'

        if category not in product_repos:
            product_repos[category] = []
        product_repos[category].append(repo)

    return {
        'total_repos': len(repos),
        'english_repos': sum(1 for r in repos
                             if not re.search(r'-(?:fr|de|ja|ko|zh-cn|zh-tw|pt-br|es-es)$', r['name'].lower())),
        'categories': {k: len(v) for k, v in product_repos.items()},
        'recently_updated': [r for r in repos if r['updated_at'] >= (
            date.today().replace(day=1).isoformat())][:20],  # updated this month
    }


def harvest_security_netapp():
    """Comprehensive scrape of security.netapp.com advisory index.

    Extracts the full advisory catalog with structured metadata.
    """
    logger.info("Starting security.netapp.com catalog harvest...")
    content = _fetch_url("https://security.netapp.com/advisory/")
    if not content:
        return {'total': 0, 'advisories': []}

    # Extract all advisory links with their text
    links = _extract_links(content)
    advisory_entries = []
    for href, text in links:
        adv_match = re.search(r'(ntap-\d{8}-\d{4})', href, re.IGNORECASE)
        if adv_match:
            advisory_entries.append({
                'id': adv_match.group(1).upper(),
                'title': text.strip()[:200] if text.strip() else adv_match.group(1),
                'url': href if href.startswith('http') else f"https://security.netapp.com/advisory/{adv_match.group(1)}/",
            })

    return {
        'total': len(advisory_entries),
        'advisories': advisory_entries,
    }


def harvest_kb_netapp(categories=None):
    """Probe kb.netapp.com for public Knowledge Base articles.

    Scans category index pages to discover new public articles.
    MindTouch-style platform — @api/deki/pages endpoints work for public pages.
    """
    logger.info("Starting kb.netapp.com harvest...")
    if categories is None:
        categories = [
            'on-prem/ontap/da', 'on-prem/ontap/DP', 'on-prem/ontap/DM',
            'on-prem/ontap/mc', 'on-prem/ontap/da/NAS', 'on-prem/ontap/da/SAN',
            'on-prem/ontap/DP/SnapMirror', 'on-prem/ontap/DP/SnapLock',
            'Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS',
        ]

    all_articles = []
    for cat in categories[:6]:  # limit categories to avoid rate limiting
        try:
            url = f"https://kb.netapp.com/{cat}"
            html = _fetch_url(url, timeout=12)
            if not html:
                continue

            links = _extract_links(html)
            for href, text in links:
                if ('/on-prem/' in href or '/Advice_and_Troubleshooting/' in href) \
                        and len(text) > 10 and text.lower() not in ('index', 'home', 'back'):
                    full_url = href if href.startswith('http') else f"https://kb.netapp.com{href}"
                    all_articles.append({
                        'url': full_url,
                        'title': text.strip()[:200],
                        'category': cat.split('/')[-1],
                        'source': 'kb.netapp.com',
                    })
        except Exception as e:
            logger.warning(f"KB harvest failed for {cat}: {e}")

    # Deduplicate by URL
    seen = set()
    unique = []
    for a in all_articles:
        if a['url'] not in seen:
            seen.add(a['url'])
            unique.append(a)

    return {'count': len(unique), 'articles': unique}


# ============================================================================
# TIER 2 HARVESTERS
# ============================================================================

def harvest_github_org_repos(org='NetApp'):
    """Discover repositories and latest releases from a GitHub organization."""
    logger.info(f"Starting GitHub org harvest for {org}...")
    repos_with_releases = []

    try:
        url = f"https://api.github.com/orgs/{org}/repos?type=public&sort=updated&per_page=50"
        data = _fetch_url(url, is_json=True, ua=GITHUB_UA)
        if not data or not isinstance(data, list):
            return repos_with_releases

        for repo in data:
            name = repo.get('name', '')
            desc = (repo.get('description') or '')[:200]

            # Check for releases on repos that look relevant
            relevant_keywords = [
                'ontap', 'trident', 'harvest', 'ansible', 'terraform',
                'snapcenter', 'storagegrid', 'solidfire', 'astra',
            ]
            if any(kw in name.lower() or kw in desc.lower() for kw in relevant_keywords):
                try:
                    rel_url = f"https://api.github.com/repos/{org}/{name}/releases?per_page=3"
                    releases = _fetch_url(rel_url, is_json=True, ua=GITHUB_UA)
                    if releases and isinstance(releases, list) and releases:
                        latest = releases[0]
                        repos_with_releases.append({
                            'repo': f"{org}/{name}",
                            'description': desc,
                            'latest_release': {
                                'tag': latest.get('tag_name', ''),
                                'name': latest.get('name', ''),
                                'published': (latest.get('published_at') or '')[:10],
                                'prerelease': latest.get('prerelease', False),
                            },
                            'url': repo.get('html_url', ''),
                        })
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"GitHub org harvest failed for {org}: {e}")

    return repos_with_releases


def harvest_pypi_packages():
    """Check latest versions of all tracked PyPI packages."""
    logger.info("Starting PyPI package harvest...")
    results = {}

    for pkg_name, pkg_info in PYPI_PACKAGES.items():
        try:
            data = _fetch_url(f"https://pypi.org/pypi/{pkg_name}/json", is_json=True)
            if data and 'info' in data:
                info = data['info']
                results[pkg_name] = {
                    'version': info.get('version'),
                    'summary': (info.get('summary') or '')[:200],
                    'requires_python': info.get('requires_python'),
                    'project_url': info.get('project_url'),
                    'product': pkg_info['product'],
                }
        except Exception as e:
            logger.warning(f"PyPI harvest failed for {pkg_name}: {e}")

    return results


def harvest_ansible_galaxy():
    """Check latest versions of NetApp Ansible Galaxy collections."""
    logger.info("Starting Ansible Galaxy harvest...")
    results = {}

    for collection, info in ANSIBLE_COLLECTIONS.items():
        try:
            # Galaxy API v3
            namespace, name = collection.split('.')
            url = f"https://galaxy.ansible.com/api/v3/plugin/ansible/content/published/collections/index/{namespace}/{name}/"
            data = _fetch_url(url, is_json=True)
            if data:
                results[collection] = {
                    'version': data.get('highest_version', {}).get('version') if isinstance(data.get('highest_version'), dict)
                               else data.get('highest_version'),
                    'product': info['product'],
                    'source': 'galaxy.ansible.com',
                }
        except Exception as e:
            logger.warning(f"Galaxy harvest failed for {collection}: {e}")

    return results


def harvest_terraform_registry():
    """Check latest versions of NetApp Terraform providers."""
    logger.info("Starting Terraform Registry harvest...")
    results = {}

    for provider_path, info in TERRAFORM_PROVIDERS.items():
        try:
            namespace, name = provider_path.split('/')
            url = f"https://registry.terraform.io/v1/providers/{namespace}/{name}"
            data = _fetch_url(url, is_json=True)
            if data:
                results[provider_path] = {
                    'version': data.get('version'),
                    'product': info['product'],
                    'source': 'registry.terraform.io',
                }
        except Exception as e:
            logger.warning(f"Terraform harvest failed for {provider_path}: {e}")

    return results


# ============================================================================
# TIER 3 HARVESTERS
# ============================================================================

def harvest_cloud_provider_docs():
    """Check cloud provider documentation for NetApp service updates.

    Sources: AWS FSx for ONTAP, Azure NetApp Files, Google Cloud NetApp Volumes.
    """
    logger.info("Starting cloud provider docs harvest...")
    results = {}

    for key, cfg in CLOUD_DOCS.items():
        try:
            html = _fetch_url(cfg['url'], timeout=12)
            if html:
                # Extract what's-new or release notes links
                whatsnew_links = []
                links = _extract_links(html)
                for href, text in links:
                    text_lower = text.lower()
                    if any(kw in text_lower for kw in ['what\'s new', 'release note', 'changelog', 'new feature']):
                        whatsnew_links.append({'href': href, 'text': text.strip()[:150]})

                results[key] = {
                    'name': cfg['name'],
                    'url': cfg['url'],
                    'accessible': True,
                    'whatsnew_links': whatsnew_links[:5],
                }
            else:
                results[key] = {'name': cfg['name'], 'accessible': False}
        except Exception as e:
            results[key] = {'name': cfg['name'], 'accessible': False, 'error': str(e)[:100]}

    return results


def harvest_cisco_flexpad_cvds():
    """Probe Cisco.com for FlexPod Cisco Validated Designs."""
    logger.info("Starting FlexPod CVD harvest...")
    results = []
    try:
        # FlexPod design guides are typically at:
        url = "https://www.cisco.com/c/en/us/solutions/design-zone/data-center-design-guides/flexpod-design-guides.html"
        html = _fetch_url(url, timeout=12)
        if html:
            links = _extract_links(html)
            for href, text in links:
                if ('flexpod' in text.lower() or 'netapp' in text.lower()) and len(text) > 15:
                    full_url = href if href.startswith('http') else f"https://www.cisco.com{href}"
                    results.append({
                        'url': full_url,
                        'title': text.strip()[:200],
                        'source': 'cisco.com',
                    })
    except Exception as e:
        logger.warning(f"FlexPod CVD harvest failed: {e}")

    return results


# ============================================================================
# ORCHESTRATOR
# ============================================================================

def run_reference_harvest(data_dir=None, dry_run=False,
                          eoa_only=False, imt_only=False,
                          advisory_only=False, docs_only=False,
                          ecosystem_only=False):
    """Run all reference data harvesters and update data files.

    Args:
        data_dir: Path to the data/ directory containing JSON files
        dry_run: If True, don't write any files
        eoa_only, imt_only, advisory_only, docs_only, ecosystem_only:
            If any is True, only run that specific harvester
    """
    if not data_dir:
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')

    logger.info(f"Starting harvest. Directory: {data_dir}, Dry Run: {dry_run}")
    os.makedirs(data_dir, exist_ok=True)

    def load_json(filename, default=None):
        if default is None:
            default = {}
        filepath = os.path.join(data_dir, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error reading {filename}: {e}")
        return default

    def save_json(filename, data):
        if dry_run:
            logger.info(f"[DRY-RUN] Would save to {filename}")
            return
        filepath = os.path.join(data_dir, filename)
        try:
            tmp = filepath + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, filepath)
            logger.info(f"Saved {filename}")
        except Exception as e:
            logger.error(f"Error writing {filename}: {e}")

    changes = {}
    run_all = not (eoa_only or imt_only or advisory_only or docs_only or ecosystem_only)

    # ── EOA ──
    if run_all or eoa_only:
        eoa_db = load_json('eoa_database.json')
        eoa_results = harvest_eoa_announcements(eoa_db)
        if eoa_results.get('_changes'):
            changes['eoa'] = eoa_results['_changes']
            # Merge new platforms
            existing_platforms = set(eoa_db.get('platforms') or [])
            for p in eoa_results.get('platforms', []):
                if p not in existing_platforms:
                    eoa_db.setdefault('platforms', []).append(p)
            # Merge new dates
            existing_dates = eoa_db.get('dates') or {}
            for model, dates in eoa_results.get('dates', {}).items():
                if model not in existing_dates:
                    existing_dates[model] = dates
            eoa_db['dates'] = existing_dates
            eoa_db['_lastUpdated'] = date.today().isoformat()
            save_json('eoa_database.json', eoa_db)

    # ── IMT ──
    if run_all or imt_only:
        imt_db = load_json('imt_interop.json')
        imt_updates = harvest_imt_versions(imt_db)
        if imt_updates:
            changes['imt'] = list(imt_updates.keys())
            for k, v in imt_updates.items():
                if k not in imt_db:
                    imt_db[k] = {}
                imt_db[k].update(v)
            imt_db['_lastUpdated'] = date.today().isoformat()
            save_json('imt_interop.json', imt_db)

    # ── Advisories ──
    if run_all or advisory_only:
        sec_db = load_json('security_bulletins.json')
        bulletins = sec_db.get('bulletins', []) if isinstance(sec_db, dict) else sec_db
        existing_ids = set()
        for b in bulletins:
            if b.get('id'):
                existing_ids.add(b['id'].upper())
                existing_ids.add(b['id'].lower())
            if b.get('ntapId'):
                existing_ids.add(b['ntapId'].upper())
                existing_ids.add(b['ntapId'].lower())

        new_advisories = harvest_advisories_from_psirt(existing_ids)
        if new_advisories:
            changes['advisories'] = [a['id'] for a in new_advisories]
            # Persist new advisories to security_bulletins.json
            sec_db_list = sec_db if isinstance(sec_db, list) else sec_db.get('bulletins', [])
            existing_id_set = {b.get('id') for b in sec_db_list}
            added = 0
            for adv in new_advisories:
                if adv.get('id') and adv['id'] not in existing_id_set:
                    sec_db_list.append(adv)
                    existing_id_set.add(adv['id'])
                    added += 1
            if added > 0:
                out = {'version': 1, 'lastUpdated': date.today().isoformat(),
                       'source': 'Authoritative bulletin database', 'bulletinCount': len(sec_db_list),
                       'bulletins': sec_db_list}
                save_json('security_bulletins.json', out)
                logger.info(f"Advisories: +{added} new entries saved")

    # ── Documentation Discovery ──
    if run_all or docs_only:
        doc_discoveries = []

        # Probe docs.netapp.com doc-sets
        docs_results = harvest_docs_netapp_index()
        accessible = [d for d in docs_results if d.get('accessible')]
        if accessible:
            changes['docs_accessible'] = len(accessible)
            for d in accessible:
                doc_discoveries.append({
                    'url': d.get('url', ''),
                    'title': d.get('title', d.get('docSet', '')),
                    'source': 'docs.netapp.com',
                    'category': 'documentation',
                    'accessible': True,
                    'discoveredAt': date.today().isoformat(),
                })

        # Discover NetAppDocs GitHub repos
        try:
            gh_docs = harvest_netappdocs_github()
            if gh_docs.get('total_repos'):
                changes['netappdocs_repos'] = gh_docs['total_repos']
                changes['netappdocs_english'] = gh_docs.get('english_repos', 0)
                changes['netappdocs_recently_updated'] = len(gh_docs.get('recently_updated', []))
                for repo in gh_docs.get('recently_updated', []):
                    doc_discoveries.append({
                        'url': repo.get('html_url', ''),
                        'title': repo.get('name', ''),
                        'source': 'github.com/NetAppDocs',
                        'category': 'documentation',
                        'lastPush': repo.get('pushed_at', ''),
                        'discoveredAt': date.today().isoformat(),
                    })
        except Exception as e:
            logger.warning(f"NetAppDocs harvest failed: {e}")

        # KB discovery
        try:
            kb_results = harvest_kb_netapp()
            if kb_results.get('count'):
                changes['kb_articles'] = kb_results['count']
        except Exception as e:
            logger.warning(f"KB harvest failed: {e}")

        # Security catalog
        try:
            sec_catalog = harvest_security_netapp()
            if sec_catalog.get('total'):
                changes['security_catalog_total'] = sec_catalog['total']
        except Exception as e:
            logger.warning(f"Security catalog failed: {e}")

        # Persist doc discoveries to knowledge_base.json
        if doc_discoveries:
            kb_db = load_json('knowledge_base.json', {'version': 1, 'articles': []})
            kb_articles = kb_db.get('articles', [])
            existing_urls = {a.get('url') for a in kb_articles}
            added = 0
            for d in doc_discoveries:
                if d.get('url') and d['url'] not in existing_urls:
                    kb_articles.append(d)
                    existing_urls.add(d['url'])
                    added += 1
            if added > 0:
                kb_db['articles'] = kb_articles
                kb_db['articleCount'] = len(kb_articles)
                kb_db['lastUpdated'] = date.today().isoformat()
                save_json('knowledge_base.json', kb_db)
                changes['docs_persisted'] = added
                logger.info(f"Docs: +{added} new entries persisted to knowledge_base.json")

    # ── Ecosystem (Tier 2) ──
    if run_all or ecosystem_only:
        eco_db = load_json('ecosystem.json', {'version': 1, '_lastUpdated': '', 'sources': {}})
        eco_sources = eco_db.get('sources', {})
        eco_changed = False

        # GitHub org repos
        for org in ['NetApp', 'NetApp-Automation']:
            try:
                repos = harvest_github_org_repos(org)
                if repos:
                    changes[f'github_{org.lower()}_repos'] = len(repos)
                    eco_sources[f'github_{org.lower()}'] = {
                        'totalRepos': len(repos),
                        'lastChecked': date.today().isoformat(),
                        'repos': [{k: v for k, v in r.items()
                                   if k in ('name', 'html_url', 'description', 'pushed_at',
                                            'stargazers_count', 'language')}
                                  for r in repos[:50]],  # Cap at 50 repos
                    }
                    eco_changed = True
            except Exception as e:
                logger.warning(f"GitHub {org} harvest failed: {e}")

        # PyPI
        try:
            pypi = harvest_pypi_packages()
            if pypi:
                changes['pypi_packages'] = {k: v.get('version') for k, v in pypi.items()}
                eco_sources['pypi'] = {
                    'lastChecked': date.today().isoformat(),
                    'packages': {k: {'version': v.get('version'), 'summary': v.get('summary', '')}
                                 for k, v in pypi.items()},
                }
                eco_changed = True
        except Exception as e:
            logger.warning(f"PyPI harvest failed: {e}")

        # Ansible Galaxy
        try:
            galaxy = harvest_ansible_galaxy()
            if galaxy:
                changes['ansible_collections'] = {k: v.get('version') for k, v in galaxy.items()}
                eco_sources['ansible_galaxy'] = {
                    'lastChecked': date.today().isoformat(),
                    'collections': {k: {'version': v.get('version'), 'namespace': v.get('namespace', '')}
                                    for k, v in galaxy.items()},
                }
                eco_changed = True
        except Exception as e:
            logger.warning(f"Ansible Galaxy harvest failed: {e}")

        # Terraform Registry
        try:
            tf = harvest_terraform_registry()
            if tf:
                changes['terraform_providers'] = {k: v.get('version') for k, v in tf.items()}
                eco_sources['terraform'] = {
                    'lastChecked': date.today().isoformat(),
                    'providers': {k: {'version': v.get('version'), 'source': v.get('source', '')}
                                  for k, v in tf.items()},
                }
                eco_changed = True
        except Exception as e:
            logger.warning(f"Terraform Registry harvest failed: {e}")

        # Cloud provider docs
        try:
            cloud = harvest_cloud_provider_docs()
            if cloud:
                changes['cloud_docs'] = {k: v.get('accessible', False) for k, v in cloud.items()}
                eco_sources['cloud_providers'] = {
                    'lastChecked': date.today().isoformat(),
                    'providers': cloud,
                }
                eco_changed = True
        except Exception as e:
            logger.warning(f"Cloud docs harvest failed: {e}")

        # FlexPod CVDs
        try:
            cvds = harvest_cisco_flexpad_cvds()
            if cvds:
                changes['flexpod_cvds'] = len(cvds)
                eco_sources['flexpod'] = {
                    'lastChecked': date.today().isoformat(),
                    'cvds': cvds[:20],  # Cap at 20 entries
                }
                eco_changed = True
        except Exception as e:
            logger.warning(f"FlexPod CVD harvest failed: {e}")

        # Persist ecosystem data
        if eco_changed:
            eco_db['sources'] = eco_sources
            eco_db['_lastUpdated'] = date.today().isoformat()
            save_json('ecosystem.json', eco_db)
            logger.info(f"Ecosystem: {len(eco_sources)} sources persisted")

    logger.info(f"Harvest complete. Changes: {json.dumps(changes, default=str)}")
    return changes


def scheduled_reference_harvest(data_dir, github_token=None):
    """Called from server.py EnrichmentScheduler as Scanner 7."""
    if github_token:
        set_github_token(github_token)
    try:
        changes = run_reference_harvest(data_dir=data_dir, dry_run=False)
        return changes
    except Exception as e:
        logger.error(f"Scheduled harvest failed: {e}")
        return {"error": str(e)}


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Reference Library Harvester — Multi-source knowledge discovery engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Data Source Tiers:
  Tier 1: docs.netapp.com, github.com/NetAppDocs, kb.netapp.com,
          security.netapp.com
  Tier 2: github.com/NetApp, PyPI, Ansible Galaxy, Terraform Registry
  Tier 3: AWS FSx ONTAP, Azure NetApp Files, Google Cloud, Cisco FlexPod
        """
    )
    parser.add_argument("--data-dir", type=str,
                        help="Directory containing JSON data files",
                        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
    parser.add_argument("--dry-run", action="store_true", help="Report only, do not write files")
    parser.add_argument("--eoa-only", action="store_true", help="Harvest only EOA data")
    parser.add_argument("--imt-only", action="store_true", help="Harvest only IMT versions")
    parser.add_argument("--advisory-only", action="store_true", help="Harvest only advisories")
    parser.add_argument("--docs-only", action="store_true", help="Documentation discovery only")
    parser.add_argument("--ecosystem-only", action="store_true",
                        help="PyPI/Galaxy/Terraform/GitHub ecosystem only")
    parser.add_argument("--github-token", type=str, default="",
                        help="GitHub PAT for higher API rate limits (5,000 req/hr vs 60)")
    args = parser.parse_args()

    if args.github_token:
        set_github_token(args.github_token)

    run_reference_harvest(
        data_dir=args.data_dir,
        dry_run=args.dry_run,
        eoa_only=args.eoa_only,
        imt_only=args.imt_only,
        advisory_only=args.advisory_only,
        docs_only=args.docs_only,
        ecosystem_only=args.ecosystem_only,
    )
