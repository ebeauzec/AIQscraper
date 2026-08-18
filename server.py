"""
AIQ Proxy Server with SQLite Cache Layer
=========================================
Drop-in replacement for server.py. Adds a persistent SQLite cache
(aiq_cache.db) so that subsequent page loads serve cached data instantly
while a background thread re-syncs from the AIQ GraphQL API.

Endpoints:
  GET /api/harvest           — returns cached data if available, triggers background sync
  GET /api/harvest?force=1   — bypasses cache, full re-harvest from API
  GET /api/sync-status       — returns sync metadata (last sync time, counts, is_syncing)
  GET /api/bulletins         — returns dynamic security bulletin DB (data/security_bulletins.json)
  POST /api/bulletins        — add/update bulletin entries (called by daily scan agent)
  POST /api/asup/import      — import an ASUP bundle (multipart or raw bytes + X-Filename header)
  GET /api/asup/imports      — list all ASUP-imported systems
  DELETE /api/asup/imports   — remove an ASUP import by serial number
  GET /api/*                 — proxy to api.activeiq.netapp.com
  POST /api/*                — proxy to api.activeiq.netapp.com
  POST /api/app/update       — git pull
"""

import http.server
import urllib.request
import urllib.error
import sys

# ── Force UTF-8 output so Unicode chars in print() don't crash on Windows
# cp1252 consoles (e.g. when server is run directly without log redirection).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import json
import ssl
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
import time
import subprocess
import os
import re
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
import html
import urllib.parse


# ASUP offline import parser (stdlib-only core, py7zr optional)
try:
    import sys
    sys.path.insert(0, str(Path(__file__).parent / "tools"))
    import asup_parser
    _ASUP_AVAILABLE = True
except ImportError:
    _ASUP_AVAILABLE = False
    print("[ASUP] asup_parser.py not found — offline import disabled", flush=True)

PORT = 8080
SCRIPT_DIR = Path(__file__).parent
DB_PATH = SCRIPT_DIR / "aiq_cache.db"
CONFIG_PATH = SCRIPT_DIR / "aiq_config.json"
BULLETINS_PATH = SCRIPT_DIR / "data" / "security_bulletins.json"
GQL_URL = "https://gql.aiq.netapp.com/graphql"
REST_BASE = "https://api.activeiq.netapp.com"

# Global sync state
_sync_lock = threading.Lock()
_is_syncing = False
_last_sync_error = None
_current_token = None  # Last-used access token for debug probes

# ─────────────────────────────────────────────────────────────────────
# Multi-account (multi-customer) support
#
# aiq_config.json historically held exactly one refresh token at the top
# level ("refreshToken"). To support multiple customers each with their own
# separate Active IQ credential, the config now ALSO supports an "accounts"
# array: [{"id", "label", "refreshToken", "watchlistId", "enabled"}, ...].
#
# Backward compatibility: the legacy top-level "refreshToken"/"watchlistId"
# fields are left untouched and still work everywhere they're read directly
# (dozens of call sites across this file) — they're treated as account
# id="default" whenever no "accounts" array is present. Every account's
# harvest is cached separately (see harvest_cache_accounts table) and merged
# at read time in handle_harvest(), so no existing single-account code path
# needs to change to keep working.
# ─────────────────────────────────────────────────────────────────────

def _load_config():
    """Read aiq_config.json, creating a blank template if it doesn't exist."""
    if not CONFIG_PATH.exists():
        blank = {"accounts": [], "refreshToken": "", "watchlistId": "", "tamName": "", "tamEmail": ""}
        CONFIG_PATH.write_text(json.dumps(blank, indent=2), encoding="utf-8")
        return blank
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_accounts(cfg=None):
    """Return the list of enabled accounts to harvest.

    If cfg["accounts"] exists, use it (only entries with enabled != False).
    Otherwise, synthesize a single "default" account from the legacy flat
    refreshToken/watchlistId fields, so existing single-token configs work
    unchanged.
    """
    cfg = cfg if cfg is not None else _load_config()
    accounts = cfg.get("accounts")
    if accounts:
        return [
            {
                "id": a.get("id") or a.get("label") or f"account{i}",
                "label": a.get("label") or a.get("id") or f"Account {i+1}",
                "refreshToken": a.get("refreshToken") or a.get("refresh_token") or "",
                "watchlistId": a.get("watchlistId", ""),
                "enabled": a.get("enabled", True),
            }
            for i, a in enumerate(accounts)
            if a.get("enabled", True) and (a.get("refreshToken") or a.get("refresh_token"))
        ]
    legacy_token = cfg.get("refreshToken") or cfg.get("refresh_token")
    if legacy_token:
        return [{
            "id": "default",
            "label": cfg.get("tamName") or "Default Account",
            "refreshToken": legacy_token,
            "watchlistId": cfg.get("watchlistId", ""),
            "enabled": True,
        }]
    return []

# Enrichment scanner state
_enrichment_scheduler = None  # Set during server startup
# Guards concurrent read-modify-write access to BULLETINS_PATH — scanners 1-4
# (CISA KEV, PSIRT, NVD, EPSS) all upsert into the same security_bulletins.json
# and now run concurrently via a thread pool, so each must hold this lock for
# its own load→modify→write span to avoid clobbering another scanner's update.
_bulletins_lock = threading.Lock()
KEV_PATH = SCRIPT_DIR / "data" / "cisa_kev.json"
KNOWLEDGE_PATH = SCRIPT_DIR / "data" / "knowledge_base.json"
VERSION_CATALOG_PATH = SCRIPT_DIR / "data" / "version_catalog.json"
ECOSYSTEM_PATH = SCRIPT_DIR / "data" / "ecosystem.json"
DISCOVERED_PRODUCTS_PATH = SCRIPT_DIR / "data" / "discovered_products.json"


# ─────────────────────────────────────────────────────────────────────
# TLS Certificate Auto-Scraping
# Detects corporate SSL-inspection proxies (Zscaler, BlueCoat, etc.)
# by catching TLS handshake failures, scraping the Windows cert store
# and Firefox NSS database, injecting found CAs, and retrying.
# Requires zero third-party packages — uses certutil.exe (Windows
# built-in) and Firefox's own certutil.exe for NSS databases.
# ─────────────────────────────────────────────────────────────────────

_ssl_ctx_lock = threading.Lock()
_ssl_ctx_cache = None          # shared ssl.SSLContext, rebuilt on demand
_ssl_extra_certs = []          # list of PEM strings injected so far
_ssl_probe_done = False        # True once the startup probe has run

# Known corporate proxy CA patterns (CN/O substrings, case-insensitive)
_CORP_PROXY_HINTS = [
    "zscaler", "bluecoat", "netskope", "symantec web gateway",
    "cisco umbrella", "forcepoint", "palo alto", "checkpoint",
    "mcafee web gateway", "iboss", "menlo security", "contentkeeper",
    "broadcom", "websense"
]


def _scrape_win_certs():
    """Return list of PEM strings from the Windows Root + CA certificate stores.
    Uses ssl.enum_certificates() — built into Python's ssl module on Windows.
    This is the correct stdlib approach: reads the Windows cert store directly
    in DER format and converts each certificate to PEM. No certutil parsing needed."""
    pems = []
    if sys.platform != "win32":
        return pems

    import base64

    stores = ["ROOT", "CA", "AUTHROOT", "MY"]
    for store in stores:
        try:
            for cert_der, encoding, trust in ssl.enum_certificates(store):
                if encoding == "x509_asn":
                    # Convert DER → PEM
                    b64 = base64.encodebytes(cert_der).decode("ascii")
                    pem = f"-----BEGIN CERTIFICATE-----\n{b64}-----END CERTIFICATE-----\n"
                    pems.append(pem)
        except Exception as exc:
            print(f"  [TLS] ssl.enum_certificates store={store}: {exc}", flush=True)

    # Deduplicate by content
    seen = set()
    unique = []
    for p in pems:
        key = p.strip()
        if key not in seen:
            seen.add(key)
            unique.append(key)
    print(f"  [TLS] Windows cert store: found {len(unique)} certificates", flush=True)
    return unique



def _scrape_firefox_certs():
    """Return list of PEM strings from Firefox's NSS certificate database.
    Uses Firefox's bundled certutil.exe (NSS tool) to export from cert9.db.
    Falls back gracefully if Firefox is not installed."""
    pems = []
    if sys.platform != "win32":
        return pems

    # Find Firefox certutil.exe (NSS certutil, not Windows certutil)
    firefox_dirs = [
        r"C:\Program Files\Mozilla Firefox",
        r"C:\Program Files (x86)\Mozilla Firefox",
    ]
    nss_certutil = None
    for d in firefox_dirs:
        candidate = Path(d) / "certutil.exe"
        if candidate.exists():
            nss_certutil = str(candidate)
            break

    if not nss_certutil:
        return pems  # Firefox not installed

    # Find Firefox profile directory (cert9.db)
    appdata = os.environ.get("APPDATA", "")
    ff_profiles_root = Path(appdata) / "Mozilla" / "Firefox" / "Profiles"
    if not ff_profiles_root.exists():
        return pems

    profile_dirs = list(ff_profiles_root.glob("*.default*"))
    if not profile_dirs:
        profile_dirs = [d for d in ff_profiles_root.iterdir() if d.is_dir()]
    if not profile_dirs:
        return pems

    profile = profile_dirs[0]  # Use the first profile found
    print(f"  [TLS] Firefox profile: {profile.name}", flush=True)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # List all certs in the Firefox NSS DB
            list_result = subprocess.run(
                [nss_certutil, "-L", "-d", f"sql:{profile}", "-h", "all"],
                capture_output=True, text=True, timeout=20,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            # Each line: "Nickname                                         Trust Attributes"
            nicknames = []
            for line in list_result.stdout.splitlines():
                # Lines look like: "DigiCert Global Root CA                  CT,C,C"
                if line.strip() and not line.startswith("Certificate") and ',' in line:
                    # Nick is everything before the last whitespace-padded trust field
                    parts = line.rsplit(None, 1)
                    if len(parts) == 2:
                        nicknames.append(parts[0].strip())

            # Export each cert as PEM
            for nick in nicknames[:200]:  # cap at 200 to avoid slowness
                try:
                    exp = subprocess.run(
                        [nss_certutil, "-L", "-d", f"sql:{profile}",
                         "-n", nick, "-a"],
                        capture_output=True, text=True, timeout=10,
                        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                    )
                    found = re.findall(
                        r'(-----BEGIN CERTIFICATE-----[\s\S]+?-----END CERTIFICATE-----)',
                        exp.stdout
                    )
                    pems.extend(found)
                except Exception:
                    pass
    except Exception as exc:
        print(f"  [TLS] Firefox NSS export error: {exc}", flush=True)

    print(f"  [TLS] Firefox NSS store: found {len(pems)} certificates", flush=True)
    return pems


def _build_ssl_ctx(extra_pems=None):
    """Build a new ssl.SSLContext loaded with system defaults plus any extra PEM certs."""
    ctx = ssl.create_default_context()
    if extra_pems:
        for pem in extra_pems:
            try:
                ctx.load_verify_locations(cadata=pem)
            except Exception as e:
                pass  # Malformed cert — skip silently
    return ctx


def _ssl_ctx():
    """Return the current shared SSL context. Thread-safe."""
    global _ssl_ctx_cache
    with _ssl_ctx_lock:
        if _ssl_ctx_cache is None:
            _ssl_ctx_cache = _build_ssl_ctx(_ssl_extra_certs)
    return _ssl_ctx_cache


def _refresh_ssl_ctx():
    """Scrape Windows + Firefox cert stores, inject new CAs, rebuild SSL context.
    Logs a summary of any corporate proxy CAs detected."""
    global _ssl_ctx_cache, _ssl_extra_certs

    print("  [TLS] Scanning certificate stores for proxy/enterprise CAs...", flush=True)
    win_pems = _scrape_win_certs()
    ff_pems  = _scrape_firefox_certs()
    all_pems = win_pems + ff_pems

    # Log any corporate proxy CA hits
    corp_found = []
    for pem in all_pems:
        # Try to find CN/O in the pem text (certutil -store embeds subject info above the PEM block)
        pass  # Detection is done via the probe pattern — PEM itself is binary-encoded

    with _ssl_ctx_lock:
        _ssl_extra_certs = all_pems
        _ssl_ctx_cache = _build_ssl_ctx(all_pems)

    print(f"  [TLS] SSL context rebuilt with {len(all_pems)} extra CA certificates", flush=True)
    return _ssl_ctx_cache


def _tls_probe_and_refresh(host="api.activeiq.netapp.com", port=443):
    """Probe the target host for TLS errors at startup.
    If the default SSL context fails, auto-scrape cert stores and retry.
    This runs once at server startup and logs the result clearly."""
    global _ssl_probe_done
    if _ssl_probe_done:
        return
    _ssl_probe_done = True

    import socket
    print(f"  [TLS] Startup probe: {host}:{port}", flush=True)

    # Step 1: Try with default SSL context
    default_ok = False
    default_err = None
    try:
        default_ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=10) as sock:
            with default_ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                issuer = dict(x[0] for x in cert.get('issuer', []))
                subject = dict(x[0] for x in cert.get('subject', []))
                issuer_org = issuer.get('organizationName', '')
                issuer_cn  = issuer.get('commonName', '')
                subject_cn = subject.get('commonName', '')
                print(f"  [TLS] Direct TLS OK — cert issuer: {issuer_cn or issuer_org}", flush=True)

                # Check if issuer looks like a corporate proxy
                issuer_str = (issuer_cn + ' ' + issuer_org).lower()
                for hint in _CORP_PROXY_HINTS:
                    if hint in issuer_str:
                        print(f"  [TLS] WARN Corporate SSL inspection detected: '{issuer_cn}'", flush=True)
                        print(f"  [TLS]   Proxy is intercepting TLS for {host}", flush=True)
                        print(f"  [TLS]   Triggering cert store scrape to ensure full trust chain...", flush=True)
                        _refresh_ssl_ctx()
                        break
                else:
                    # Legitimate cert — still build ctx normally (no corporate proxy detected)
                    _refresh_ssl_ctx()  # builds ctx from stores without forcing it
                default_ok = True
    except ssl.SSLError as e:
        default_err = e
        print(f"  [TLS] Default context FAILED: {e}", flush=True)
    except Exception as e:
        default_err = e
        print(f"  [TLS] Probe connection FAILED: {e}", flush=True)

    if not default_ok:
        # Step 2: TLS failed — scrape stores and try again
        print("  [TLS] Attempting cert store scrape and retry...", flush=True)
        new_ctx = _refresh_ssl_ctx()
        retry_ok = False
        try:
            import socket
            with socket.create_connection((host, port), timeout=10) as sock:
                with new_ctx.wrap_socket(sock, server_hostname=host) as ssock:
                    print(f"  [TLS] OK Retry succeeded after injecting enterprise CAs", flush=True)
                    retry_ok = True
        except Exception as e2:
            print(f"  [TLS] FAIL Retry also failed: {e2}", flush=True)
            print(f"  [TLS]   If on a corporate network, ask IT to add '{host}' to SSL inspection bypass", flush=True)

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
        CREATE TABLE IF NOT EXISTS harvest_cache_accounts (
            account_id TEXT PRIMARY KEY,
            account_label TEXT DEFAULT '',
            result_json TEXT NOT NULL,
            harvested_at TEXT NOT NULL,
            duration_ms INTEGER DEFAULT 0,
            system_count INTEGER DEFAULT 0,
            cluster_count INTEGER DEFAULT 0,
            risk_count INTEGER DEFAULT 0,
            case_count INTEGER DEFAULT 0,
            risk_instance_count INTEGER DEFAULT 0
        );
        -- ── Normalized reporting tables ──────────────────────────────────
        -- The full harvest result is already stored as JSON in
        -- harvest_cache_accounts.result_json (nothing shown in the tool is
        -- browser-only), but a JSON blob is painful to query directly with
        -- SQL. These tables mirror the same data into real columns for
        -- direct reporting -- refreshed (DELETE+INSERT) on every harvest,
        -- so they always reflect current state. For point-in-time history,
        -- use system_snapshots instead (one dated row per system per day).
        CREATE TABLE IF NOT EXISTS reporting_systems (
            serial_number       TEXT NOT NULL,
            account_id          TEXT NOT NULL DEFAULT '',
            account_label       TEXT DEFAULT '',
            system_name         TEXT DEFAULT '',
            cluster_name        TEXT DEFAULT '',
            customer_name       TEXT DEFAULT '',
            site_name           TEXT DEFAULT '',
            site_city           TEXT DEFAULT '',
            site_country        TEXT DEFAULT '',
            platform            TEXT DEFAULT '',
            model               TEXT DEFAULT '',
            os_version          TEXT DEFAULT '',
            recommended_os_version TEXT DEFAULT '',
            system_state        TEXT DEFAULT '',
            is_ha_configured    INTEGER,
            is_arp_enabled      INTEGER,
            is_metrocluster     INTEGER,
            is_fabricpool       INTEGER,
            efficiency_ratio    TEXT DEFAULT '',
            snapmirror_count    INTEGER DEFAULT 0,
            capacity_used_kb    INTEGER,
            capacity_allocated_kb INTEGER,
            capacity_available_kb INTEGER,
            contract_active     INTEGER,
            contract_end_date   TEXT DEFAULT '',
            warranty_end_date   TEXT DEFAULT '',
            service_level       TEXT DEFAULT '',
            latest_asup_date    TEXT DEFAULT '',
            risk_critical       INTEGER DEFAULT 0,
            risk_high           INTEGER DEFAULT 0,
            risk_medium         INTEGER DEFAULT 0,
            risk_low            INTEGER DEFAULT 0,
            open_case_count     INTEGER DEFAULT 0,
            sales_rep_name      TEXT DEFAULT '',
            tam_name            TEXT DEFAULT '',
            sam_name            TEXT DEFAULT '',
            age_in_years        REAL,
            original_ship_date  TEXT DEFAULT '',
            updated_at          TEXT NOT NULL,
            PRIMARY KEY (serial_number, account_id)
        );
        CREATE TABLE IF NOT EXISTS reporting_risks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            serial_number   TEXT NOT NULL,
            system_name     TEXT DEFAULT '',
            account_id      TEXT DEFAULT '',
            risk_id         TEXT DEFAULT '',
            severity        TEXT DEFAULT '',
            category        TEXT DEFAULT '',
            short_name      TEXT DEFAULT '',
            risk_detail     TEXT DEFAULT '',
            cve_ids         TEXT DEFAULT '',
            acknowledged    INTEGER DEFAULT 0,
            updated_at      TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_reporting_risks_serial ON reporting_risks(serial_number);
        CREATE INDEX IF NOT EXISTS idx_reporting_risks_severity ON reporting_risks(severity);
        CREATE TABLE IF NOT EXISTS reporting_cases (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            serial_number   TEXT NOT NULL,
            system_name     TEXT DEFAULT '',
            account_id      TEXT DEFAULT '',
            case_id         TEXT DEFAULT '',
            status          TEXT DEFAULT '',
            priority        TEXT DEFAULT '',
            highest_priority TEXT DEFAULT '',
            created          TEXT DEFAULT '',
            last_updated     TEXT DEFAULT '',
            closed           TEXT DEFAULT '',
            symptom          TEXT DEFAULT '',
            updated_at       TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_reporting_cases_serial ON reporting_cases(serial_number);
        CREATE INDEX IF NOT EXISTS idx_reporting_cases_status ON reporting_cases(status);
        CREATE TABLE IF NOT EXISTS system_snapshots (
            serial_number   TEXT NOT NULL,
            snapshot_date   TEXT NOT NULL,
            customer_name   TEXT DEFAULT '',
            system_name     TEXT DEFAULT '',
            snapshot_json   TEXT NOT NULL,
            captured_at     TEXT NOT NULL,
            PRIMARY KEY (serial_number, snapshot_date)
        );
        CREATE INDEX IF NOT EXISTS idx_snapshots_serial ON system_snapshots(serial_number);
        CREATE TABLE IF NOT EXISTS asup_imports (
            serial_number TEXT PRIMARY KEY,
            system_json   TEXT NOT NULL,
            coverage_json TEXT NOT NULL,
            customer_name TEXT DEFAULT '',
            site_name     TEXT DEFAULT '',
            notes         TEXT DEFAULT '',
            filename      TEXT DEFAULT '',
            imported_at   TEXT NOT NULL,
            matched_serial TEXT DEFAULT '',
            match_type     TEXT DEFAULT 'new'
        );
    """)
    db.commit()
    # Migrate existing asup_imports rows that lack the new columns (safe no-op if cols exist)
    for col, default in [("site_name","''"), ("notes","''"), ("matched_serial","''"), ("match_type","'new'")]:
        try:
            db.execute(f"ALTER TABLE asup_imports ADD COLUMN {col} TEXT DEFAULT {default}")
            db.commit()
        except Exception:
            pass  # column already exists
    db.executescript("""
        CREATE TABLE IF NOT EXISTS enrich_cache (
            cache_key   TEXT PRIMARY KEY,
            result_json TEXT NOT NULL,
            fetched_at  TEXT NOT NULL,
            source      TEXT DEFAULT ''
        );
    """)
    # Purge: 24h for NVD CVEs, 7 days for everything else
    db.execute("""
        DELETE FROM enrich_cache WHERE
            (source = 'nvd' AND fetched_at < datetime('now', '-1 day')) OR
            (source != 'nvd' AND fetched_at < datetime('now', '-7 days'))
    """)
    db.commit()
    # One-time migration: copy the legacy singleton harvest (id=1) into the
    # new per-account table under account_id="default", so existing users
    # keep their cached fleet data after upgrading to multi-account support.
    try:
        has_default = db.execute(
            "SELECT 1 FROM harvest_cache_accounts WHERE account_id = 'default'"
        ).fetchone()
        if not has_default:
            legacy_row = db.execute(
                "SELECT result_json, harvested_at, duration_ms, system_count, cluster_count, "
                "risk_count, case_count, risk_instance_count FROM harvest_cache WHERE id = 1"
            ).fetchone()
            if legacy_row:
                db.execute("""
                    INSERT OR REPLACE INTO harvest_cache_accounts
                    (account_id, account_label, result_json, harvested_at, duration_ms,
                     system_count, cluster_count, risk_count, case_count, risk_instance_count)
                    VALUES ('default', 'Default Account', ?, ?, ?, ?, ?, ?, ?, ?)
                """, legacy_row)
                db.commit()
                print("  [DB] Migrated legacy singleton harvest cache into per-account table (account_id=default)", flush=True)
    except Exception as _mig_err:
        print(f"  [DB] Legacy harvest cache migration skipped: {_mig_err}", flush=True)
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
# Multi-account cache layer
# ─────────────────────────────────────────────────────────────────────

def _save_harvest_account(db, account_id, account_label, result, duration_ms=0):
    """Write one account's harvest result to its own cache row. Also mirrors
    the 'default' account into the legacy singleton harvest_cache table so
    every existing single-account code path (dozens of call sites reading
    `WHERE id = 1` directly) keeps working unchanged."""
    now = datetime.now(timezone.utc).isoformat()
    result_json = json.dumps(result, default=str)
    db.execute("""
        INSERT OR REPLACE INTO harvest_cache_accounts
        (account_id, account_label, result_json, harvested_at, duration_ms,
         system_count, cluster_count, risk_count, case_count, risk_instance_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        account_id, account_label, result_json, now, duration_ms,
        result.get("totalSystems", 0), result.get("totalClusters", 0),
        result.get("totalRisks", 0), result.get("totalCases", 0),
        result.get("totalRiskInstances", result.get("riskInstances", 0)),
    ))
    db.commit()
    print(f"  [CACHE] Saved harvest for account '{account_id}' ({len(result_json)} bytes, {result.get('totalSystems', 0)} systems)", flush=True)
    if account_id == "default":
        _save_harvest(db, result, duration_ms)


def _load_cached_account(db, account_id):
    """Load one account's cached harvest result. Returns (result, meta) or (None, None)."""
    row = db.execute(
        "SELECT result_json, account_label, harvested_at, duration_ms, system_count, "
        "cluster_count, risk_count, case_count, risk_instance_count "
        "FROM harvest_cache_accounts WHERE account_id = ?", (account_id,)
    ).fetchone()
    if not row:
        return None, None
    result = json.loads(row[0])
    meta = {
        "accountId": account_id, "accountLabel": row[1], "harvested_at": row[2],
        "duration_ms": row[3], "system_count": row[4], "cluster_count": row[5],
        "risk_count": row[6], "case_count": row[7], "risk_instance_count": row[8],
    }
    return result, meta


def _load_all_accounts_cached(db):
    """Load every account's cached harvest. Returns list of (account_id, result, meta)."""
    rows = db.execute(
        "SELECT account_id, account_label, result_json, harvested_at, duration_ms, "
        "system_count, cluster_count, risk_count, case_count, risk_instance_count "
        "FROM harvest_cache_accounts"
    ).fetchall()
    out = []
    for row in rows:
        try:
            result = json.loads(row[2])
        except Exception:
            continue
        meta = {
            "accountId": row[0], "accountLabel": row[1], "harvested_at": row[3],
            "duration_ms": row[4], "system_count": row[5], "cluster_count": row[6],
            "risk_count": row[7], "case_count": row[8], "risk_instance_count": row[9],
        }
        out.append((row[0], result, meta))
    return out


# ─────────────────────────────────────────────────────────────────────
# Historical trend snapshots
# ─────────────────────────────────────────────────────────────────────
# One row per (system, calendar day). Re-syncing multiple times in the same
# UTC day overwrites that day's row rather than accumulating noise — the
# point is week/month/quarter/year-over-year comparison, not intraday
# tracking. Retention is capped (see _SNAPSHOT_RETENTION_DAYS) so the table
# doesn't grow unbounded on a fleet that syncs daily for years.
_SNAPSHOT_RETENTION_DAYS = 400


def _capture_snapshots(db, result):
    """Extract a small per-system metrics record from a completed harvest and
    store it as today's dated snapshot, for later trend comparison (vs last
    week/month/quarter/year). Cheap and best-effort: never raises, since a
    snapshot-capture failure must not take down the harvest it's attached to.
    """
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        now_iso = datetime.now(timezone.utc).isoformat()
        systems = result.get("systems") or []
        rows = []
        for s in systems:
            serial = s.get("serialNumber")
            if not serial:
                continue
            risks = s.get("risks") or []
            cases = s.get("cases") or []
            risk_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            for r in risks:
                sev = str(r.get("severity") or "").lower()
                if sev in risk_counts:
                    risk_counts[sev] += 1
            open_critical_cases = sum(
                1 for c in cases
                if str(c.get("status") or "").upper() not in ("CLOSED", "CANCELLED")
                and str(c.get("highestPriority") or c.get("priority") or "").upper().startswith(("S1", "P1", "S2", "P2", "CRITICAL", "HIGH"))
            )
            snap = {
                "systemName": s.get("systemName", ""),
                "customerName": s.get("customerName", ""),
                "platform": s.get("platform", ""),
                "osVersion": s.get("osVersion", ""),
                "efficiencyRatio": s.get("efficiencyRatio"),
                "fabricPoolTieredTB": (s.get("efficiency") or {}).get("fabricPoolTieredTB") if isinstance(s.get("efficiency"), dict) else None,
                "riskCounts": risk_counts,
                "caseCount": len(cases),
                "openCriticalCases": open_critical_cases,
                "isHAConfigured": s.get("isHAConfigured"),
                "isARPEnabled": s.get("isARPEnabled"),
                "snapMirrorCount": s.get("snapMirrorCount"),
                "contractEndDate": s.get("contractEndDate", ""),
                "contractActive": s.get("contractActive"),
            }
            rows.append((serial, today, s.get("customerName", ""), s.get("systemName", ""), json.dumps(snap), now_iso))
        if not rows:
            return
        db.executemany("""
            INSERT OR REPLACE INTO system_snapshots
            (serial_number, snapshot_date, customer_name, system_name, snapshot_json, captured_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, rows)
        db.execute(
            "DELETE FROM system_snapshots WHERE snapshot_date < date('now', ?)",
            (f"-{_SNAPSHOT_RETENTION_DAYS} days",)
        )
        db.commit()
        print(f"  [SNAPSHOT] Captured {len(rows)} system snapshot(s) for {today}", flush=True)
    except Exception as e:
        print(f"  [SNAPSHOT] Capture failed (non-fatal): {e}", flush=True)


def _get_system_history(db, serial_number, days=400):
    """Return this system's dated snapshots, oldest first, each as
    {date, ...snapshot fields}. Used for week/month/quarter/year trend
    comparisons in the UI and in deliverables."""
    rows = db.execute("""
        SELECT snapshot_date, snapshot_json FROM system_snapshots
        WHERE serial_number = ? AND snapshot_date >= date('now', ?)
        ORDER BY snapshot_date ASC
    """, (serial_number, f"-{days} days")).fetchall()
    out = []
    for date_str, snap_json in rows:
        try:
            rec = json.loads(snap_json)
        except Exception:
            continue
        rec["date"] = date_str
        out.append(rec)
    return out


def _populate_reporting_tables(db, account_id, account_label, result):
    """Mirror one account's harvest result into the normalized reporting_*
    tables, so the SQLite database can be queried directly with plain SQL
    (SELECT/JOIN/GROUP BY) instead of requiring json_extract() on the
    harvest_cache_accounts blob. This is a mirror, not a second source of
    truth: result_json in harvest_cache_accounts remains authoritative,
    and every column here is copied straight from the same harvest result
    already used to render the live UI -- nothing computed differently.
    Fully replaces this account's rows on every call (DELETE+INSERT), so
    the tables always reflect current state; use system_snapshots for
    point-in-time history instead.
    """
    try:
        systems = result.get("systems") or []
        now_iso = datetime.now(timezone.utc).isoformat()

        db.execute("DELETE FROM reporting_systems WHERE account_id = ?", (account_id,))
        db.execute("DELETE FROM reporting_risks WHERE account_id = ?", (account_id,))
        db.execute("DELETE FROM reporting_cases WHERE account_id = ?", (account_id,))

        sys_rows, risk_rows, case_rows = [], [], []
        for s in systems:
            serial = s.get("serialNumber")
            if not serial:
                continue
            risks = s.get("risks") or []
            cases = s.get("cases") or []
            risk_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            for r in risks:
                sev = str(r.get("severity") or "").lower()
                if sev in risk_counts:
                    risk_counts[sev] += 1
                cve_ids = ",".join(
                    c.get("id", "") for c in (r.get("cves") or []) if isinstance(c, dict) and c.get("id")
                )
                risk_rows.append((
                    serial, s.get("systemName", ""), account_id,
                    r.get("riskId", ""), sev, r.get("category", ""),
                    r.get("shortName", ""), r.get("riskDetail", ""), cve_ids,
                    1 if r.get("acknowledgement") else 0, now_iso,
                ))
            open_cases = 0
            for c in cases:
                status = str(c.get("status") or "")
                if status.upper() not in ("CLOSED", "CANCELLED"):
                    open_cases += 1
                case_rows.append((
                    serial, s.get("systemName", ""), account_id,
                    c.get("caseId", ""), status, str(c.get("priority") or ""),
                    str(c.get("highestPriority") or ""), c.get("created", ""),
                    c.get("lastUpdated", ""), c.get("closed", ""), c.get("symptom", ""),
                    now_iso,
                ))
            sys_rows.append((
                serial, account_id, account_label,
                s.get("systemName", ""), s.get("clusterName", ""), s.get("customerName", ""),
                s.get("siteName", ""), s.get("siteCity", ""), s.get("siteCountry", ""),
                s.get("platform", ""), s.get("model", ""), s.get("osVersion", ""),
                s.get("recommendedOSVersion", ""), s.get("systemState", ""),
                s.get("isHAConfigured"), s.get("isARPEnabled"), s.get("isMetroCluster"),
                s.get("isFabricPool"), s.get("efficiencyRatio", ""), s.get("snapMirrorCount", 0),
                s.get("capacityUsedKB"), s.get("capacityAllocatedKB"), s.get("capacityAvailableKB"),
                s.get("contractActive"), s.get("contractEndDate", ""), s.get("warrantyEndDate", ""),
                s.get("serviceLevel", ""), s.get("latestAsupDate", ""),
                risk_counts["critical"], risk_counts["high"], risk_counts["medium"], risk_counts["low"],
                open_cases, s.get("salesRepName", ""), s.get("csmName", ""), s.get("samName", ""),
                s.get("ageInYears"), s.get("originalShipDate", ""), now_iso,
            ))

        if sys_rows:
            db.executemany("""
                INSERT INTO reporting_systems (
                    serial_number, account_id, account_label, system_name, cluster_name, customer_name,
                    site_name, site_city, site_country, platform, model, os_version, recommended_os_version,
                    system_state, is_ha_configured, is_arp_enabled, is_metrocluster, is_fabricpool,
                    efficiency_ratio, snapmirror_count, capacity_used_kb, capacity_allocated_kb,
                    capacity_available_kb, contract_active, contract_end_date, warranty_end_date,
                    service_level, latest_asup_date, risk_critical, risk_high, risk_medium, risk_low,
                    open_case_count, sales_rep_name, tam_name, sam_name, age_in_years, original_ship_date,
                    updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, sys_rows)
        if risk_rows:
            db.executemany("""
                INSERT INTO reporting_risks (
                    serial_number, system_name, account_id, risk_id, severity, category,
                    short_name, risk_detail, cve_ids, acknowledged, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, risk_rows)
        if case_rows:
            db.executemany("""
                INSERT INTO reporting_cases (
                    serial_number, system_name, account_id, case_id, status, priority,
                    highest_priority, created, last_updated, closed, symptom, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, case_rows)
        db.commit()
        print(f"  [REPORTING] Mirrored {len(sys_rows)} systems, {len(risk_rows)} risks, {len(case_rows)} cases into reporting_* tables for account '{account_id}'", flush=True)
    except Exception as e:
        print(f"  [REPORTING] Mirror failed (non-fatal): {e}", flush=True)


# List-valued fields concatenated across accounts when merging harvests.
# NOTE: "riskInstances" is deliberately excluded — despite the name, the
# harvest result stores it as an integer count (len(all_risk_instances)),
# not the actual list; the real per-risk-instance data lives inside each
# entry of "risks".
_MERGE_LIST_FIELDS = [
    "systems", "clusters", "risks", "cases",
    "tamSites", "tamRenewals", "acknowledgedRisksNowExploited",
]


def _merge_account_results(account_results):
    """Combine multiple accounts' harvest results into one unified fleet view.

    Each account's systems/clusters/risks/etc. are already tagged with
    accountId/accountLabel (see _do_full_harvest). List-valued fields are
    concatenated; scalar/summary fields (firmwareBaselines, tamOsVersions,
    etc.) are taken from the account with the most systems, since those are
    account-agnostic reference data, not per-customer telemetry.
    """
    if not account_results:
        return None
    if len(account_results) == 1:
        return account_results[0][1]

    account_results = sorted(account_results, key=lambda ar: len(ar[1].get("systems") or []), reverse=True)
    merged = dict(account_results[0][1])  # start from the largest account's result as the base

    for field in _MERGE_LIST_FIELDS:
        combined = []
        seen_keys = set()
        for _acct_id, result, _meta in account_results:
            for item in (result.get(field) or []):
                # Dedupe by serialNumber/id where present (NetApp serials are globally
                # unique, so this only guards against the same account appearing twice,
                # not against real cross-customer collisions).
                key = item.get("serialNumber") if isinstance(item, dict) else None
                key = key or (item.get("id") if isinstance(item, dict) else None)
                dedupe_key = (item.get("accountId"), key) if isinstance(item, dict) and key else None
                if dedupe_key and dedupe_key in seen_keys:
                    continue
                if dedupe_key:
                    seen_keys.add(dedupe_key)
                combined.append(item)
        merged[field] = combined

    merged["totalSystems"] = len(merged.get("systems") or [])
    merged["totalClusters"] = len(merged.get("clusters") or [])
    merged["totalRisks"] = len(merged.get("risks") or [])
    merged["totalCases"] = len(merged.get("cases") or [])
    merged["totalRiskInstances"] = sum((result.get("totalRiskInstances") or 0) for _acct_id, result, _meta in account_results)
    merged["riskInstances"] = merged["totalRiskInstances"]
    merged["accounts"] = [
        {"id": acct_id, "label": (result.get("accountLabel") or acct_id),
         "systemCount": len(result.get("systems") or [])}
        for acct_id, result, _meta in account_results
    ]
    return merged


# ─────────────────────────────────────────────────────────────────────
# API Harvest Logic (extracted from original handle_harvest)
# ─────────────────────────────────────────────────────────────────────

# ── Proxy-aware opener cache ──────────────────────────────────────────
# Built once per SSL context generation so we pick up both OS proxy
# settings (Zscaler/WPAD inside corp) and direct routing (outside corp).
_opener_lock  = threading.Lock()
_opener_cache = None
_opener_ssl_ctx_id = None  # tracks which ssl ctx the opener was built for

def _build_opener(ctx):
    """Build a urllib opener that honours OS/env proxy settings + the given SSL ctx."""
    proxies = urllib.request.getproxies()  # reads env vars + Windows registry/WPAD
    handlers = [urllib.request.HTTPSHandler(context=ctx)]
    if proxies:
        # ProxyHandler must come before HTTPSHandler
        handlers.insert(0, urllib.request.ProxyHandler(proxies))
        proxy_str = ", ".join(f"{k}={v}" for k, v in proxies.items() if k in ("http", "https"))
        if proxy_str:
            print(f"  [HTTP] Proxy detected: {proxy_str}", flush=True)
    else:
        # Explicit no-proxy handler — avoids urllib falling back to system defaults
        # that might inject an unwanted proxy when env vars are cleared outside corp.
        handlers.insert(0, urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(*handlers)


def _get_opener():
    """Return the cached opener, rebuilding if the SSL context changed."""
    global _opener_cache, _opener_ssl_ctx_id
    ctx = _ssl_ctx()
    ctx_id = id(ctx)
    with _opener_lock:
        if _opener_cache is None or _opener_ssl_ctx_id != ctx_id:
            _opener_cache = _build_opener(ctx)
            _opener_ssl_ctx_id = ctx_id
    return _opener_cache


def _http(method, url, headers=None, body=None, _retry=True):
    """Make an HTTP/HTTPS request using the shared SSL context.

    Works transparently inside and outside the corporate network:
    - Inside (Zscaler/proxy): urllib.request.getproxies() reads the OS proxy
      settings (env vars, Windows registry, WPAD) and routes via the proxy.
    - Outside (direct): getproxies() returns {} and requests go direct.
    - TLS: uses the shared ssl.SSLContext with corporate CA certs injected;
      on any TLS failure auto-scrapes cert stores and retries once.
    """
    global _opener_cache
    hdrs = headers or {}
    data = None
    if body is not None:
        if isinstance(body, dict):
            data = json.dumps(body).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        elif isinstance(body, str):
            data = body.encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    opener = _get_opener()
    try:
        with opener.open(req, timeout=120) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except ssl.SSLError as e:
        print(f"  [TLS] SSL error on {url}: {e}", flush=True)
        if _retry:
            print("  [TLS] Attempting cert store refresh and retry...", flush=True)
            _refresh_ssl_ctx()
            _opener_cache = None  # force rebuild
            return _http(method, url, headers=headers, body=body, _retry=False)
        return 0, f"SSL error: {e}".encode("utf-8")
    except Exception as e:
        err_str = str(e)
        if _retry and any(k in err_str for k in (
            'SSL', 'CERTIFICATE', 'certificate verify failed',
            'UNABLE_TO_VERIFY', 'DEPTH_ZERO', 'CERT_UNTRUSTED'
        )):
            print(f"  [TLS] TLS-related error on {url}: {e}", flush=True)
            print("  [TLS] Attempting cert store refresh and retry...", flush=True)
            _refresh_ssl_ctx()
            _opener_cache = None  # force rebuild
            return _http(method, url, headers=headers, body=body, _retry=False)
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
    raw_text = raw.decode("utf-8", errors="replace")
    # ActiveIQ's GraphQL API occasionally returns literal NaN or Infinity in
    # Float fields (e.g. qoqUtilizationPercentage, yoyUtilizationPercentage).
    # These are valid JavaScript but invalid JSON — json.loads will raise
    # JSONDecodeError. Sanitize before parsing.
    raw_text = re.sub(r'\bNaN\b', 'null', raw_text)
    raw_text = re.sub(r'\b-?Infinity\b', 'null', raw_text)
    try:
        parsed = json.loads(raw_text)
        # json.loads("null") returns None — treat as empty response
        if parsed is None:
            parsed = {}
        return status, parsed
    except json.JSONDecodeError:
        # Non-JSON body (e.g. HTML error page from proxy/Zscaler)
        snippet = raw_text[:300].strip()
        print(f"  [GQL] Non-JSON response (HTTP {status}): {snippet}", flush=True)
        return status, {"errors": [{"message": f"Non-JSON response (HTTP {status}): {snippet}"}]}


def _check_acknowledged_risks_vs_kev(risks_by_serial):
    """Cross-reference every acknowledged risk's CVE(s) against the CISA KEV
    (Known Exploited Vulnerabilities) catalog. Returns a list of
    {serialNumber, riskId, riskTitle, cveId, acknowledgedBy, acknowledgementDate,
     justification, kevDateAdded, kevDueDate, kevRequiredAction} for every match
    — i.e. every case where a TAM accepted/deferred a risk that has since been
    confirmed under active real-world exploitation. Returns [] if the KEV
    catalog hasn't been fetched yet or contains no entries."""
    flagged = []
    try:
        if not KEV_PATH.exists():
            return flagged
        kev_data = json.loads(KEV_PATH.read_text(encoding='utf-8'))
        kev_by_cve = {v.get('cveID'): v for v in kev_data.get('vulnerabilities', []) if v.get('cveID')}
        if not kev_by_cve:
            return flagged

        for serial, risks in risks_by_serial.items():
            for r in risks:
                ack = r.get('acknowledgement')
                if not ack:
                    continue
                for cve in (r.get('cves') or []):
                    cve_id = cve.get('id') if isinstance(cve, dict) else None
                    if cve_id and cve_id in kev_by_cve:
                        kev_entry = kev_by_cve[cve_id]
                        flagged.append({
                            'serialNumber': serial,
                            'riskId': r.get('riskId', ''),
                            'riskTitle': r.get('shortName') or r.get('riskDetail', ''),
                            'cveId': cve_id,
                            'acknowledgedBy': ack.get('acknowledgedBy', ''),
                            'acknowledgementDate': ack.get('acknowledgementDate', ''),
                            'justification': ack.get('justification', ''),
                            'kevDateAdded': kev_entry.get('dateAdded', ''),
                            'kevDueDate': kev_entry.get('dueDate', ''),
                            'kevRequiredAction': kev_entry.get('requiredAction', ''),
                        })
    except Exception as e:
        print(f'  [KEV-ACK] Cross-reference failed: {e}', flush=True)
    return flagged


def _do_full_harvest(watchlist_ids=None, account=None):
    """Execute the full AIQ GraphQL harvest. Returns the result dict.
    This is the core logic extracted from handle_harvest, now reusable
    for both synchronous and background calls.

    If watchlist_ids is provided (list of ID strings), only systems in those
    watchlists are fetched and merged (deduplicated by serialNumber).
    For backward compatibility, a bare string is also accepted.

    If `account` is provided (dict with id/label/refreshToken/watchlistId —
    see _get_accounts()), that account's credential is used instead of the
    top-level aiq_config.json fields, its watchlistId is merged into
    watchlist_ids, and every system/cluster/risk/case in the result is
    tagged with accountId/accountLabel before being cached under that
    account's own cache row (see _sync_all_accounts).
    """
    global _is_syncing, _last_sync_error

    with _sync_lock:
        if _is_syncing:
            raise Exception("Sync already in progress")
        _is_syncing = True
        _last_sync_error = None

    # Normalise: accept a bare string or a list of strings
    if isinstance(watchlist_ids, str):
        watchlist_ids = [w.strip() for w in watchlist_ids.split(",") if w.strip()]
    watchlist_ids = list(watchlist_ids or [])  # empty list == no filter (all systems)
    if account and account.get("watchlistId"):
        for _wl in str(account["watchlistId"]).split(","):
            _wl = _wl.strip()
            if _wl and _wl not in watchlist_ids:
                watchlist_ids.append(_wl)

    start_time = time.time()
    try:
        # 1. Read refresh token — from the account override if given, else the
        # legacy top-level aiq_config.json fields (unchanged single-account path).
        if account:
            refresh_token = account.get("refreshToken")
            if not refresh_token:
                raise Exception(f"setup_required: Account '{account.get('id')}' has no refresh token configured")
        else:
            if not CONFIG_PATH.exists():
                # Auto-create a blank template so the user can fill it in via Settings
                blank = {"refreshToken": "", "watchlistId": "", "tamName": "", "tamEmail": ""}
                CONFIG_PATH.write_text(json.dumps(blank, indent=2), encoding="utf-8")
                print("  [HARVEST] Created blank aiq_config.json template", flush=True)
                raise Exception("setup_required: No Active IQ credentials configured")
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            refresh_token = cfg.get("refreshToken") or cfg.get("refresh_token")
            if not refresh_token:
                raise Exception("setup_required: No refresh token configured — open Settings & Config to add your Active IQ refresh token")

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
        global _current_token
        _current_token = token
        print("  [HARVEST] Authenticated OK", flush=True)

        # 3. Fetch summary (best-effort — accounts without unfiltered_system_access
        #    privilege will get a GQL error here; we just skip it gracefully since
        #    these counts are only used for logging, not for downstream logic).
        total_sys = total_cl = total_sites = 0
        summary = {}  # initialise here so it's always defined even if summary query is skipped
        try:
            print("  [HARVEST] Fetching summary...", flush=True)
            # Use watchlist-scoped summary when watchlists are configured
            # (use only the first ID for the summary count — it's informational only)
            if watchlist_ids:
                sum_query = f'{{ summary(watchlistId: "{watchlist_ids[0]}") {{ system cluster site }} }}'
            else:
                sum_query = "{ summary { system cluster site } }"
            sum_status, summary_resp = _gql(token, sum_query)
            if isinstance(summary_resp, dict) and not summary_resp.get("errors") and sum_status in (200, 201):
                summary = (summary_resp.get("data") or {}).get("summary") or {}
                total_sys   = summary.get("system", 0)
                total_cl    = summary.get("cluster", 0)
                total_sites = summary.get("site", 0)
                print(f"  [HARVEST] Fleet: {total_sys} systems, {total_cl} clusters, {total_sites} sites", flush=True)
            else:
                err = (summary_resp.get("errors") or [{}])[0].get("message", "unknown") if isinstance(summary_resp, dict) else "non-dict response"
                print(f"  [HARVEST] Summary skipped (will count from fetched data): {err}", flush=True)
        except Exception as sum_err:
            print(f"  [HARVEST] Summary query failed (non-fatal): {sum_err}", flush=True)

        # 4. Fetch ALL systems with full details (pagination)
        #    Strategy: try the expanded TAM query first; if GraphQL rejects any
        #    field the whole response comes back with 0 systems.  In that case
        #    fall back to the proven minimal query.
        #
        #    IMPORTANT: Do NOT add "... on ESeriesSystem" inline fragments.
        #    The GQL schema does not support the ESeriesSystem type — including
        #    it causes a GRAPHQL_VALIDATION_FAILED error that silently fails the
        #    entire query, causing the harvest to fall through to MINIMAL tier
        #    (which has no capacity/efficiency data). See commit e106562.
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
                  softwareVersion { fullVersionString endOfVersionDetails { releaseDate endOfVersionFullSupport endOfVersionLimitedSupport endOfSelfServiceSupport } }
                  endOfSupport { earliestEndOfSupportDate earliestShelfEndOfSupportDate earliestDiskEndOfSupportDate latestPVRDate latestEndOfSupportDate }
                  swRecommendationDetails { minRecommendedVersion latestRecommendedVersion cqvDetails { qualifiedVersion } }
                  latestAsup { asupId generatedDate receivedDate subject type isManual }
                  latestAsupOfEachType { asupId generatedDate receivedDate subject type isManual }
                  autoSupports { asupId generatedDate receivedDate subject type isManual }"""

        # ── Extended: original + safe additional fields ──
        SYSTEMS_FIELDS_TAM = """
                  hostName systemId serialNumber osVersion recommendedOSVersion
                  type platformType productType ageInYears serviceTier
                  techRefreshStatus incumbentResellerCompany
                  isFabricPool hasPvr
                  systemState lastRebootTime originalShipDate marketingType storageConfiguration
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
                  softwareVersion { fullVersionString endOfVersionDetails { releaseDate endOfVersionFullSupport endOfVersionLimitedSupport endOfSelfServiceSupport } }
                  endOfSupport { earliestEndOfSupportDate earliestShelfEndOfSupportDate earliestDiskEndOfSupportDate latestPVRDate latestEndOfSupportDate }
                  swRecommendationDetails { minRecommendedVersion latestRecommendedVersion cqvDetails { qualifiedVersion } }
                  latestAsup { asupId generatedDate receivedDate subject type isManual }
                  latestAsupOfEachType { asupId generatedDate receivedDate subject type isManual }
                  autoSupports { asupId generatedDate receivedDate subject type isManual }
                  ... on ONTAPSystem {
                    isMetroCluster isAllFlashOptimized operatingMode
                    propensityCategory serviceProcessorIPAddress
                    isARPEnabled autoUpdateEnabled nextBestAction
                    lifecycleEvents { workflowCategory typeCode typeName criticalityCode daysToEvent talkingPoint }
                    systemFirmware { type currentVersion recommendedVersion }
                    motherboardFirmware { currentVersion recommendedVersion }
                    diskQualificationPackage { currentVersion recommendedVersion autoUpdateEligible }
                    shelves {
                      serialNumber shelfId
                      hardwareModel { name endOfAvailability endOfHwSupport }
                      moduleHardwareModel { name }
                      drives { totalCount drives { firmwareRevision vendor hardwareModel { name } } }
                    }
                    storageAggregates { totalCount }
                    storageVolumes { totalCount }
                    luns { totalCount }
                    autoUpdateSettings { storageFirmware spbmc systemFile securityFile }
                    sustainabilityScores { scorePercentage percentageChange changeFactors generatedDate }
                    vcenters { id name version }
                    licenses { licenseSerialNumber package type description name }
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
                    networkPorts {
                      totalCount
                      networkPorts { port role link type broadcastDomain ipspaceName speedOperationalMbps macAddress maxTransmissionUnitBytes interfaceGroupOwner }
                    }
                  }"""

        # ── Medium: efficiency data without problematic Float fields ──────────
        # The TAM query above fails outside corp with "Float cannot represent
        # non numeric value: null" for utilization percentages.  This query
        # strips the percentage fields and monthlyCapacity but keeps the
        # efficiency ratio/saved block — giving us dataReductionRatio and
        # deDuplicationSavedKiB for accurate donut chart savings.
        SYSTEMS_FIELDS_EFFICIENCY = """
                  hostName systemId serialNumber osVersion recommendedOSVersion
                  type platformType productType ageInYears serviceTier
                  techRefreshStatus incumbentResellerCompany
                  isFabricPool hasPvr
                  systemState lastRebootTime originalShipDate marketingType storageConfiguration
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
                  softwareVersion { fullVersionString endOfVersionDetails { releaseDate endOfVersionFullSupport endOfVersionLimitedSupport endOfSelfServiceSupport } }
                  endOfSupport { earliestEndOfSupportDate earliestShelfEndOfSupportDate earliestDiskEndOfSupportDate latestPVRDate latestEndOfSupportDate }
                  swRecommendationDetails { minRecommendedVersion latestRecommendedVersion cqvDetails { qualifiedVersion } }
                  latestAsup { asupId generatedDate receivedDate subject type isManual }
                  latestAsupOfEachType { asupId generatedDate receivedDate subject type isManual }
                  autoSupports { asupId generatedDate receivedDate subject type isManual }
                  ... on ONTAPSystem {
                    isMetroCluster isAllFlashOptimized operatingMode
                    propensityCategory serviceProcessorIPAddress
                    isARPEnabled autoUpdateEnabled nextBestAction
                    lifecycleEvents { workflowCategory typeCode typeName criticalityCode daysToEvent talkingPoint }
                    systemFirmware { type currentVersion recommendedVersion }
                    motherboardFirmware { currentVersion recommendedVersion }
                    diskQualificationPackage { currentVersion recommendedVersion autoUpdateEligible }
                    shelves {
                      serialNumber shelfId
                      hardwareModel { name endOfAvailability endOfHwSupport }
                      moduleHardwareModel { name }
                      drives { totalCount drives { firmwareRevision vendor hardwareModel { name } } }
                    }
                    capacity {
                      physical { rawMarketingKiB usedKiB usedWithoutSnapshotsKiB usablePerformanceTierKiB }
                      logical { usedKiB usedWithoutSnapshotsClonesKiB }
                      efficiency {
                        ratio { efficiencyRatio dataReductionRatio withSnapshotRatio }
                        saved { savedKiB deDuplicationSavedKiB compactionSavedKiB }
                      }
                      reportedOn
                    }
                    storageAggregates { totalCount }
                    storageVolumes { totalCount }
                    luns { totalCount }
                    autoUpdateSettings { storageFirmware spbmc systemFile securityFile }
                    sustainabilityScores { scorePercentage percentageChange changeFactors generatedDate }
                    vcenters { id name version }
                    licenses { licenseSerialNumber package type description name }
                    pvrs { id info validFrom validTo }
                    downtimeEvents { totalCount events { category code emsDate summary outageSeconds } }
                    networkPorts {
                      totalCount
                      networkPorts { port role link type broadcastDomain ipspaceName speedOperationalMbps macAddress maxTransmissionUnitBytes interfaceGroupOwner }
                    }
                  }"""

        # ── Early watchlist auto-discovery ──────────────────────────────────────
        # Fetch watchlists from REST *before* the systems query so we can use them
        # as a fallback scope when configured watchlists are stale or the account
        # lacks unfiltered_system_access.
        # Always runs — even when watchlist_ids is configured (they may be stale).
        _early_watchlists = []  # list of watchlist id strings
        # 1. Try REST paths first
        try:
            for wl_path in ["/v1/watchlists/list", "/v1/watchlist/all", "/v2/watchlist/action",
                             "/v1/watchlist", "/v1/watchlists"]:
                try:
                    wl_st, wl_raw = _http("GET", f"{REST_BASE}{wl_path}",
                        {"Authorization": f"Bearer {token}", "Accept": "application/json"})
                    if wl_st == 200:
                        wl_data = json.loads(wl_raw.decode("utf-8", errors="replace"))
                        wl_list = wl_data if isinstance(wl_data, list) else wl_data.get("results", wl_data.get("watchlists", wl_data.get("data", [])))
                        if isinstance(wl_list, list):
                            for wl in wl_list:
                                if isinstance(wl, dict):
                                    wid = wl.get("watchListId") or wl.get("watchlistId") or wl.get("id", "")
                                    if wid:
                                        _early_watchlists.append(wid)
                        if _early_watchlists:
                            print(f"  [HARVEST] Auto-discovered {len(_early_watchlists)} watchlist(s) via REST ({wl_path})", flush=True)
                            break
                except Exception:
                    pass
        except Exception as _wl_disc_err:
            print(f"  [HARVEST] Watchlist REST pre-discovery skipped: {_wl_disc_err}", flush=True)

        # 2. Fallback: try GraphQL watchlists query
        # NOTE: verified via live schema introspection (2026-08-10) that "watchlists"
        # does not exist as a Query field in the current GraphQL schema — this call
        # always returns a GRAPHQL_VALIDATION_FAILED error and falls through to the
        # except block below. Left in place (harmless, caught) in case NetApp adds
        # this field in a future API version; REST discovery above is the only
        # channel that has ever actually worked.
        if not _early_watchlists:
            try:
                _, wl_gql_resp = _gql(token, "{ watchlists { id name } }")
                wl_gql_list = ((wl_gql_resp.get("data") or {}).get("watchlists") or []) if isinstance(wl_gql_resp, dict) else []
                for wl in wl_gql_list:
                    if isinstance(wl, dict):
                        wid = wl.get("id", "")
                        if wid:
                            _early_watchlists.append(wid)
                if _early_watchlists:
                    print(f"  [HARVEST] Auto-discovered {len(_early_watchlists)} watchlist(s) via GraphQL", flush=True)
                else:
                    print("  [HARVEST] No watchlists found via REST or GraphQL — account may need a watchlist configured", flush=True)
            except Exception as _wl_gql_err:
                print(f"  [HARVEST] Watchlist GQL pre-discovery skipped: {_wl_gql_err}", flush=True)

        _PRIVILEGE_PHRASES = ("unfiltered_system_access", "mandatory argument", "privilege")

        def _fetch_systems_for_scope(fields, scope_wl_id=None):
            """Fetch all systems pages for a given fields set and optional watchlist scope."""
            systems = []
            cursor = None
            page = 0
            privilege_blocked = False
            while True:
                page += 1
                after_arg = f', after: "{cursor}"' if cursor else ""
                wl_arg = f', watchlistId: "{scope_wl_id}"' if scope_wl_id else ""
                query_text = """{
                  systems(pageSize: 100""" + after_arg + wl_arg + """) {
                    totalCount cursor
                    systems {""" + fields + """
                    }
                  }
                }"""
                if page == 1:
                    scope_label = scope_wl_id or "unfiltered"
                    print(f"  [HARVEST] Systems query (scope={scope_label}) attempt...", flush=True)
                _, sys_resp = _gql(token, query_text)
                # Guard: _gql may return None on network failure
                if not isinstance(sys_resp, dict):
                    print(f"  [HARVEST] Systems GQL: non-dict response (network error?), stopping pagination", flush=True)
                    break
                # Detect privilege block or watchlist-not-found errors
                if sys_resp.get("errors"):
                    err_msg = sys_resp["errors"][0].get("message", "")
                    if any(p in err_msg.lower() for p in _PRIVILEGE_PHRASES):
                        print(f"  [HARVEST] Privilege block detected: {err_msg[:120]}", flush=True)
                        privilege_blocked = True
                        break
                    elif "does not exist" in err_msg.lower() or "not found" in err_msg.lower():
                        print(f"  [HARVEST] Watchlist not found (stale ID?): {err_msg[:200]}", flush=True)
                        break
                    elif page == 1:
                        print(f"  [HARVEST] GraphQL errors: {err_msg[:200]}", flush=True)
                        break
                sys_data = (sys_resp.get("data") or {}).get("systems") or {}
                if not isinstance(sys_data, dict):
                    break
                page_systems = sys_data.get("systems") or []
                systems.extend(page_systems)
                new_cursor = sys_data.get("cursor")
                print(f"  [HARVEST] Page {page}: {len(page_systems)} systems (total so far: {len(systems)})", flush=True)
                if not page_systems or not new_cursor or new_cursor == cursor:
                    break
                cursor = new_cursor
            return systems, privilege_blocked

        # Try expanded first, fall back to efficiency-only, then minimal
        all_systems = []
        used_tam_query = False
        _QUERY_NAMES = ["TAM (full)", "Efficiency (medium)", "Minimal (bare)"]
        for attempt, fields in enumerate([SYSTEMS_FIELDS_TAM, SYSTEMS_FIELDS_EFFICIENCY, SYSTEMS_FIELDS_MINIMAL]):
            all_systems = []

            print(f"  [HARVEST] Attempting {_QUERY_NAMES[attempt]} query...", flush=True)

            # First: try with configured watchlist_ids (fetching + deduplicating across all)
            if watchlist_ids:
                print(f"  [HARVEST] Fetching systems across {len(watchlist_ids)} configured watchlist(s)...", flush=True)
                seen_serials = set()
                for wl_id_cfg in watchlist_ids:
                    wl_systems, wl_blocked = _fetch_systems_for_scope(fields, wl_id_cfg)
                    for s in wl_systems:
                        sn = s.get("serialNumber", "")
                        if sn not in seen_serials:
                            seen_serials.add(sn)
                            all_systems.append(s)
                    if wl_blocked:
                        print(f"  [HARVEST] Privilege block on watchlist {wl_id_cfg} (skipping)", flush=True)
                blocked = len(all_systems) == 0
                fetched = all_systems[:]
            else:
                fetched, blocked = _fetch_systems_for_scope(fields, None)
                # ── BUG FIX: assign the unfiltered result to all_systems ──────
                # Previously `fetched` was populated but `all_systems` stayed []
                # causing the server to always store 0 systems even when the API
                # returned hundreds of systems.
                all_systems = list(fetched)

            # If blocked by privilege OR returned 0 systems (outside corp network the API
            # returns success+empty instead of a privilege error), retry with auto-discovered watchlists.
            # Also retry if configured watchlist_ids produced 0 (they may be stale/invalid).
            if (blocked or len(all_systems) == 0) and _early_watchlists:
                already_tried = set(watchlist_ids or [])
                new_wls = [w for w in _early_watchlists if w not in already_tried]
                if new_wls:
                    print(f"  [HARVEST] Retrying with {len(new_wls)} auto-scoped watchlist(s) (reason: {'privilege block' if blocked else '0 systems from unfiltered/configured query'})...", flush=True)
                    seen_serials = {s.get('serialNumber', '') for s in all_systems}
                    for wl_id_auto in new_wls:
                        wl_systems, _ = _fetch_systems_for_scope(fields, wl_id_auto)
                        for s in wl_systems:
                            sn = s.get("serialNumber", "")
                            if sn not in seen_serials:
                                seen_serials.add(sn)
                                all_systems.append(s)
                    print(f"  [HARVEST] Combined from watchlists: {len(all_systems)} unique systems", flush=True)

            # Final fallback: try unfiltered query (no watchlist scope) when all
            # configured + auto-discovered watchlists returned 0 systems.
            if len(all_systems) == 0 and watchlist_ids:
                print("  [HARVEST] All watchlists returned 0 — trying unfiltered query...", flush=True)
                unfiltered, _uf_blocked = _fetch_systems_for_scope(fields, None)
                if unfiltered and not _uf_blocked:
                    all_systems = list(unfiltered)
                    print(f"  [HARVEST] Unfiltered query succeeded: {len(all_systems)} systems", flush=True)


            if len(all_systems) > 0:
                used_tam_query = attempt <= 1  # TAM or EFFICIENCY both include capacity/efficiency
                print(f"  [HARVEST] {_QUERY_NAMES[attempt]} query succeeded: {len(all_systems)} systems", flush=True)
                break
            else:
                print(f"  [HARVEST] WARNING: {_QUERY_NAMES[attempt]} query returned 0 systems — trying next tier...", flush=True)




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
                    serialNumber shelfId
                    hardwareModel { name endOfAvailability endOfHwSupport }
                    moduleHardwareModel { name }
                    drives { totalCount drives { firmwareRevision vendor hardwareModel { name } } }
                  }
                  vservers { id name type subType logicalInterfaces { name ipAddress worldWidePortName status { administrative operation } serviceConfiguration { servicePolicy dataProtocols } failoverConfiguration { homeNode { hostName serialNumber } homePort currentNode { hostName serialNumber } currentPort failoverPolicy } } }
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
            # Guard: privilege error or proxy block returns errors/null data
            if not isinstance(cl_resp, dict):
                print(f"  [HARVEST] Clusters: non-dict response, skipping", flush=True)
                break
            if cl_resp.get("errors"):
                err_msg = cl_resp["errors"][0].get("message", "")[:150]
                print(f"  [HARVEST] Clusters GQL error (skipping): {err_msg}", flush=True)
                break
            cl_data = (cl_resp.get("data") or {}).get("clusters") or {}
            clusters_page = cl_data.get("clusters") or [] if isinstance(cl_data, dict) else []
            all_clusters.extend(clusters_page)
            new_cursor = cl_data.get("cursor") if isinstance(cl_data, dict) else None
            if not clusters_page or not new_cursor or new_cursor == cursor:
                break
            cursor = new_cursor

        print(f"  [HARVEST] Clusters: {len(all_clusters)}", flush=True)

        # RC-3 Fix: if unscoped clusters returned 0 (privilege-restricted corp account)
        # retry scoped to each known watchlist to recover SnapMirror/HA/switch/shelf data.
        if len(all_clusters) == 0:
            _wl_ids_for_cl = list(watchlist_ids or [])
            for _w in _early_watchlists:
                if _w not in set(_wl_ids_for_cl):
                    _wl_ids_for_cl.append(_w)
            if _wl_ids_for_cl:
                print(f"  [HARVEST] Clusters=0 — retrying scoped to {len(_wl_ids_for_cl)} watchlist(s)...", flush=True)
                _seen_cl_ids: set = set()
                for _wl_cl_id in _wl_ids_for_cl[:10]:  # cap at 10 watchlists
                    _cl_wl_cursor = None
                    while True:
                        _cl_after_arg = f', after: "{_cl_wl_cursor}"' if _cl_wl_cursor else ""
                        _cl_wl_query = (
                            '{ clusters(pageSize: 100, watchlistId: "' + _wl_cl_id + '"' + _cl_after_arg + ') {'
                            ' cursor clusters {'
                            ' id name managementIPAddress osVersion isHAConfigured ageInYears'
                            ' osRecommendation { recommendedVersion }'
                            ' snapMirrorRelationships { totalCount }'
                            ' systems { serialNumber }'
                            ' switches { switchSerialNumber deviceName role vendor model ipAddress'
                            '   isDiscovered isMonitored versionInfo { fwVersion rcfVersion } }'
                            ' shelves { serialNumber shelfId hardwareModel { name endOfAvailability endOfHwSupport } moduleHardwareModel { name } drives { totalCount drives { firmwareRevision vendor hardwareModel { name } } } }'
                            ' vservers { id name type subType logicalInterfaces { name ipAddress worldWidePortName status { administrative operation } serviceConfiguration { servicePolicy dataProtocols } failoverConfiguration { homeNode { hostName serialNumber } homePort currentNode { hostName serialNumber } currentPort failoverPolicy } } }'
                            ' capacity {'
                            '   physical { usedKiB rawMarketingKiB usablePerformanceTierKiB'
                            '             qoqUtilizationPercentage yoyUtilizationPercentage }'
                            '   logical { usedKiB } reportedOn }'
                            ' monthlyCapacity { month'
                            '   physical { usedKiB rawMarketingKiB qoqUtilizationPercentage } }'
                            ' } } }'
                        )
                        _, _cl_r = _gql(token, _cl_wl_query)
                        if not isinstance(_cl_r, dict):
                            break
                        if _cl_r.get("errors"):
                            _cl_err = _cl_r["errors"][0].get("message", "")[:150]
                            print(f"  [HARVEST] Clusters watchlist retry error (skipping): {_cl_err}", flush=True)
                            break
                        _cl_wl_data = (_cl_r.get("data") or {}).get("clusters") or {}
                        _cl_wl_page = _cl_wl_data.get("clusters") or [] if isinstance(_cl_wl_data, dict) else []
                        for _cl in _cl_wl_page:
                            _cl_uid = _cl.get("id") or _cl.get("name")
                            if _cl_uid and _cl_uid not in _seen_cl_ids:
                                _seen_cl_ids.add(_cl_uid)
                                all_clusters.append(_cl)
                        _cl_new_cur = _cl_wl_data.get("cursor") if isinstance(_cl_wl_data, dict) else None
                        if not _cl_wl_page or not _cl_new_cur or _cl_new_cur == _cl_wl_cursor:
                            break
                        _cl_wl_cursor = _cl_new_cur
                print(f"  [HARVEST] Clusters (after watchlist retry): {len(all_clusters)}", flush=True)

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
                      cves { id cvssScore description summary lastUpdated }
                    }
                    system { serialNumber hostName }
                    systemRiskDetail
                    riskAcknowledgementInfo { acknowledgedBy acknowledgementDate justification comments acknowledgementExpiryDate }
                  }
                }
              }""")
            if not isinstance(ri_resp, dict) or ri_resp.get("errors"):
                err_msg = (ri_resp["errors"][0].get("message", "")[:120] if isinstance(ri_resp, dict) else "non-dict response")
                print(f"  [HARVEST] Risk instances GQL error (skipping): {err_msg}", flush=True)
                break
            ri_data = (ri_resp.get("data") or {}).get("riskInstances") or {}
            ri_page_items = ri_data.get("riskInstances") or [] if isinstance(ri_data, dict) else []
            all_risk_instances.extend(ri_page_items)
            new_cursor = ri_data.get("cursor") if isinstance(ri_data, dict) else None
            print(f"  [HARVEST] Risk instances page {ri_page}: {len(ri_page_items)} (total so far: {len(all_risk_instances)})", flush=True)
            if not ri_page_items or not new_cursor or new_cursor == cursor:
                break
            cursor = new_cursor
        print(f"  [HARVEST] Total risk instances: {len(all_risk_instances)}", flush=True)

        # 7. Fetch all support cases — paginated + fallback without productTypes if the
        #    corp-network GQL proxy rejects the enum value.
        print("  [HARVEST] Fetching support cases...", flush=True)
        all_cases = []

        def _fetch_cases_pages(with_product_types=True):
            """Paginate all cases. Returns list of case dicts, or None on GQL error."""
            cases_out = []
            c_cursor = None
            c_page = 0
            while True:
                c_page += 1
                c_after = f', after: "{c_cursor}"' if c_cursor else ""
                c_pt    = ', productTypes: [FILER, SWApp]' if with_product_types else ''
                _, cr = _gql(token, '{ cases(pageSize: 200' + c_after + c_pt + ''') {
                    totalCount cursor
                    cases {
                      caseId symptom description status priority highestPriority
                      created lastUpdated closed type category subCategory
                      caseReceivedVia
                      reporterContact { name }
                      system { serialNumber hostName }
                    }
                  } }''')
                if not isinstance(cr, dict):
                    print(f"  [HARVEST] Cases GQL: non-dict response (network/proxy error)", flush=True)
                    break
                if cr.get("errors"):
                    err_msg = cr["errors"][0].get("message", "")[:200]
                    print(f"  [HARVEST] Cases GQL error: {err_msg}", flush=True)
                    return None  # caller will retry without productTypes
                c_data  = (cr.get("data") or {}).get("cases") or {}
                c_items = c_data.get("cases") or [] if isinstance(c_data, dict) else []
                cases_out.extend(c_items)
                new_cur = c_data.get("cursor") if isinstance(c_data, dict) else None
                print(f"  [HARVEST] Cases page {c_page}: {len(c_items)} "
                      f"(total so far: {len(cases_out)}, totalCount={c_data.get('totalCount','?')})",
                      flush=True)
                if not c_items or not new_cur or new_cur == c_cursor:
                    break
                c_cursor = new_cur
            return cases_out

        # First attempt with productTypes filter; if corp proxy rejects enum, retry without
        _cases_result = _fetch_cases_pages(with_product_types=True)
        if _cases_result is None:
            print("  [HARVEST] Cases: retrying without productTypes filter...", flush=True)
            _cases_result = _fetch_cases_pages(with_product_types=False) or []
        all_cases = _cases_result or []
        print(f"  [HARVEST] Cases total: {len(all_cases)}", flush=True)

        # 8. Fetch customers (with sustainability)
        _, cust_resp = _gql(token, """{ customers(pageSize: 100) { customers {
            id cmatId name
            sustainabilityScorePercentage { overall }
        } } }""")
        customers = (((cust_resp.get("data") or {}).get("customers") or {}).get("customers")) or [] if isinstance(cust_resp, dict) else []

        # ── TAM: Recommendations ──
        tam_recommendations = []
        try:
            print("  [HARVEST] Fetching TAM recommendations...", flush=True)
            _, rec_resp = _gql(token, """{ recommendations(isTopKeyRecommendation: true, limit: 50) {
                recommendation rank category subCategory score
            } }""")
            tam_recommendations = (rec_resp.get("data") or {}).get("recommendations") or [] if isinstance(rec_resp, dict) else []
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
            tam_sites = (((sites_resp.get("data") or {}).get("sites") or {}).get("sites")) or []
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
            tam_sustainability = (((sust_resp.get("data") or {}).get("sustainabilityScore") or {}).get("sustainabilityScores")) or [] if isinstance(sust_resp, dict) else []
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
            tam_os_versions = ((osv_resp.get("data") or {}).get("osVersions", {}).get("osVersions")) or [] if isinstance(osv_resp, dict) else []
            print(f"  [HARVEST] OS versions: {len(tam_os_versions)}", flush=True)

            # ── Fill gaps: query specifically for fleet OS versions not in first page ──
            _cached_versions = set(v.get("osVersion", "") for v in tam_os_versions)
            _fleet_versions = set()
            for _s in all_systems:
                _osv_str = _s.get("osVersion") or ""
                if _osv_str:
                    _fleet_versions.add(_osv_str)
            _missing = sorted(_fleet_versions - _cached_versions)
            if _missing:
                # Query in batches of 50
                _extra_count = 0
                for _i in range(0, len(_missing), 50):
                    _batch = _missing[_i:_i+50]
                    _ver_list = json.dumps(_batch)
                    _, _extra_resp = _gql(token, f"""{{ osVersions(osVersions: {_ver_list}, pageSize: 500) {{ osVersions {{
                        osVersion majorOsVersion osType operatingMode
                        releaseDate endOfVersionFullSupport endOfVersionLimitedSupport endOfSelfServiceSupport
                        supportState progressionPath
                        bundledSystemFirmwares {{ type version biosVersion systemModel }}
                        bundledDriveFirmwares {{ driveModel version }}
                        bundledShelfFirmwares {{ shelfName shelfModuleName firmwareType shelfModuleFirmwareVersion sysShelfModuleFirmwareVersion }}
                        bundledSecurityFiles {{ fileType version }}
                    }} }} }}""")
                    _extra_versions = ((_extra_resp.get("data") or {}).get("osVersions", {}).get("osVersions")) or [] if isinstance(_extra_resp, dict) else []
                    tam_os_versions.extend(_extra_versions)
                    _extra_count += len(_extra_versions)
                if _extra_count:
                    print(f"  [HARVEST] OS versions (fleet-targeted): +{_extra_count} for {len(_missing)} fleet versions", flush=True)
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
            # .get("systemContractRenewals", {}) only applies its default when the key
            # is MISSING — GraphQL can return {"data": {"systemContractRenewals": null}}
            # (e.g. no privilege/no systems in scope), where the key exists with value
            # None, crashing the chained .get("systems") call. Use "or {}" instead.
            tam_renewals = (((ren_resp.get("data") or {}).get("systemContractRenewals") or {}).get("systems")) or [] if isinstance(ren_resp, dict) else []
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
                risk_entry["acknowledgement"] = ri.get("riskAcknowledgementInfo")
                risks_by_serial.setdefault(serial, []).append(risk_entry)

        # 9b. Cross-reference acknowledged risks against the CISA KEV catalog —
        # flags cases where a TAM acknowledged (accepted/deferred) a risk that
        # has since been added to CISA's Known Exploited Vulnerabilities list,
        # meaning it's now under active real-world exploitation. This is a
        # meaningful escalation signal no other view in the tool surfaces.
        acknowledged_risks_now_exploited = _check_acknowledged_risks_vs_kev(risks_by_serial)

        # 10. Build casesBySerial lookup from cases
        cases_by_serial = {}
        _cases_no_serial = 0
        for c in all_cases:
            c_sys = c.get("system") or {}
            serial = c_sys.get("serialNumber")
            if serial:
                cases_by_serial.setdefault(serial, []).append(c)
            else:
                _cases_no_serial += 1
        _cases_matched = sum(len(v) for v in cases_by_serial.values())
        print(f"  [HARVEST] Cases by serial: {len(cases_by_serial)} unique serials, "
              f"{_cases_matched} matched, {_cases_no_serial} without serial", flush=True)
        if cases_by_serial:
            _sample = list(cases_by_serial.items())[:3]
            for _sk, _sv in _sample:
                print(f"    Serial {_sk}: {len(_sv)} case(s)", flush=True)

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
        serial_to_cluster_vservers = {}  # serial → vservers list from cluster
        for cl in all_clusters:
            cl_id = cl.get("id") or cl.get("name")
            cl_name = cl.get("name", "")
            if cl_id:
                cluster_map[cl_id] = cl
            cl_systems = cl.get("systems") or []
            cap = cl.get("capacity") or {}
            phys = cap.get("physical") or {}
            logical = cap.get("logical") or {}
            # Note: ClusterCapacity GQL type does NOT support efficiency sub-fields.
            # Efficiency data is only available from the system-level ONTAP inline fragment.
            # Divide capacity by node count to produce per-node fallback values.
            _n_nodes = max(len(cl_systems), 1)
            cap_data = {
                "physicalUsedTB": round((phys.get("usedKiB") or 0) / (1024**3) / _n_nodes, 2),
                "rawCapacityTB": round((phys.get("rawMarketingKiB") or 0) / (1024**3) / _n_nodes, 2),
                "logicalUsedTB": round((logical.get("usedKiB") or 0) / (1024**3) / _n_nodes, 2),
                "physicalUsedNoSnapsTB": round((phys.get("usedWithoutSnapshotsKiB") or 0) / (1024**3) / _n_nodes, 2),
                "logicalUsedNoSnapsTB": round((logical.get("usedWithoutSnapshotsClonesKiB") or 0) / (1024**3) / _n_nodes, 2),
                "usableCapacityTB": round((phys.get("usablePerformanceTierKiB") or phys.get("rawMarketingKiB") or 0) / (1024**3) / _n_nodes, 2),
                "qoqUtilizationPct": phys.get("qoqUtilizationPercentage") or 0,
                "yoyUtilizationPct": phys.get("yoyUtilizationPercentage") or 0,
                "capacityReportedOn": (cap.get("reportedOn") or "")[:10],
                # Monthly history for chart: list of {month, usedKiB, rawKiB}
                "monthlyCapacity": [
                    {
                        "month": m.get("month", ""),
                        "usedTB": round(((m.get("physical") or {}).get("usedKiB") or 0) / (1024**3) / _n_nodes, 3),
                        "rawTB": round(((m.get("physical") or {}).get("rawMarketingKiB") or 0) / (1024**3) / _n_nodes, 2),
                        "qoqPct": (m.get("physical") or {}).get("qoqUtilizationPercentage") or None,
                    }
                    for m in (cl.get("monthlyCapacity") or [])
                ],
            }
            sm_count = ((cl.get("snapMirrorRelationships") or {}).get("totalCount")) or 0
            # isHAConfigured from the API is unreliable — it can return null/false
            # even for multi-node clusters. Any ONTAP cluster with 2+ nodes is
            # inherently an HA pair, so infer HA from node count as a fallback.
            is_ha = cl.get("isHAConfigured")
            if not is_ha and len(cl_systems) >= 2:
                is_ha = True
            cl_os = cl.get("osVersion", "")
            cl_rec = ((cl.get("osRecommendation") or {}).get("recommendedVersion")) or ""
            cl_switches = cl.get("switches") or []
            cl_shelves = cl.get("shelves") or []
            cl_vservers = cl.get("vservers") or []
            # Compute SVM counts from vservers type field
            _data_svm_count = sum(1 for v in cl_vservers if (v.get("type") or "").upper() == "DATA")
            _node_svm_count = sum(1 for v in cl_vservers if (v.get("type") or "").upper() == "NODE")
            for cs in cl_systems:
                cs_serial = cs.get("serialNumber")
                if cs_serial:
                    serial_to_cluster[cs_serial] = cl_name
                    serial_to_cluster_cap[cs_serial] = cap_data
                    serial_to_cluster_sm[cs_serial] = sm_count
                    serial_to_cluster_ha[cs_serial] = is_ha
                    serial_to_cluster_switches[cs_serial] = cl_switches
                    serial_to_cluster_shelves[cs_serial] = cl_shelves
                    serial_to_cluster_vservers[cs_serial] = cl_vservers
                    serial_to_cluster_cap[cs_serial]["dataSvmCount"] = _data_svm_count
                    serial_to_cluster_cap[cs_serial]["nodeSvmCount"] = _node_svm_count
        
        total_sw = sum(len(v) for v in serial_to_cluster_switches.values())
        print(f"  [HARVEST] Switch instances mapped: {total_sw // max(len(serial_to_cluster_switches), 1)} unique across clusters", flush=True)

        # ── Load external ground-truth firmware baselines ──
        _baselines_path = os.path.join(os.path.dirname(__file__), "data", "firmware_baselines.json")
        _ext_baselines = {}
        try:
            with open(_baselines_path, "r", encoding="utf-8") as _bl_f:
                _ext_baselines = json.load(_bl_f)
            print(f"  [HARVEST] Loaded firmware baselines from {os.path.basename(_baselines_path)} (updated: {_ext_baselines.get('_lastUpdated', '?')})", flush=True)
        except Exception as _bl_err:
            print(f"  [HARVEST] WARNING: Could not load firmware_baselines.json: {_bl_err}", flush=True)

        # ── Build firmware lookup from osVersions bundled firmware catalog ──
        # Maps (osVersion, modelPrefix) → {spVersion, biosVersion, dqpVersion}
        # Used to derive firmware currency when per-system GQL returns null.
        _fw_by_os_model = {}  # key: (osVersion, model) → {type, version, biosVersion}
        _latest_fw_by_model = {}  # key: model → {type, version, biosVersion} from latest ONTAP
        _dqp_by_os = {}  # key: osVersion → {currentVersion from bundled DQP}
        _drive_fw_by_os = {}  # key: osVersion → {driveModel: version}
        _latest_drive_fw = {}  # key: driveModel → latest recommended version
        _shelf_fw_by_os_module = {}  # key: (osVersion, shelfModuleName) → sysShelfModuleFirmwareVersion
        _latest_shelf_fw_by_module = {}  # key: shelfModuleName → latest recommended version
        for _osv in tam_os_versions:
            _os_ver = _osv.get("osVersion", "")
            if not _os_ver:
                continue
            for _bsf in (_osv.get("bundledSystemFirmwares") or []):
                _sys_model = _bsf.get("systemModel", "")
                _fw_type = _bsf.get("type", "SP")  # SP or BMC
                _fw_ver = _bsf.get("version", "")
                _bios_ver = _bsf.get("biosVersion", "")
                if _sys_model and _fw_ver:
                    _fw_by_os_model[(_os_ver, _sys_model)] = {
                        "type": _fw_type, "version": _fw_ver, "biosVersion": _bios_ver
                    }
                    # Track the latest (last entry wins since osVersions is typically sorted)
                    _latest_fw_by_model[_sys_model] = {
                        "type": _fw_type, "version": _fw_ver, "biosVersion": _bios_ver,
                        "osVersion": _os_ver,
                    }
            # Build bundled drive firmware lookup
            _bdf = _osv.get("bundledDriveFirmwares") or []
            if _bdf:
                _os_drives = {}
                for _d in _bdf:
                    _dm = _d.get("driveModel", "")
                    _dv = _d.get("version", "")
                    if _dm and _dv:
                        _os_drives[_dm] = _dv
                        _latest_drive_fw[_dm] = _dv  # last wins
                if _os_drives:
                    _drive_fw_by_os[_os_ver] = _os_drives
            # Build bundled shelf firmware lookup
            for _bshf in (_osv.get("bundledShelfFirmwares") or []):
                _smod = _bshf.get("shelfModuleName", "")
                _sver = _bshf.get("sysShelfModuleFirmwareVersion", "")
                if _smod and _sver:
                    _shelf_fw_by_os_module[(_os_ver, _smod)] = _sver
                    _latest_shelf_fw_by_module[_smod] = _sver  # last wins
        _fw_derived = 0

        # ── Override firmware baselines with external ground-truth ──
        # The GQL catalog only knows firmware bundled with ONTAP releases.
        # External baselines from firmware_baselines.json represent the actual
        # latest published firmware from NetApp support site / KBs.
        _ext_sp_families = ((_ext_baselines.get("spBmc") or {}).get("families") or [])
        _ext_sp_by_model = ((_ext_baselines.get("spBmc") or {}).get("byModel") or {})
        _ext_shelf_modules = _ext_baselines.get("shelfModules") or {}
        _ext_ontap = _ext_baselines.get("ontap") or {}
        _ext_ontap_by_branch = _ext_ontap.get("latestByBranch") or {}
        _ext_santricity = _ext_baselines.get("santricity") or {}

        def _resolve_ext_sp_bmc(model_name):
            """Resolve SP/BMC version from external baselines using keyword matching."""
            if not model_name:
                return None, None
            model_upper = model_name.upper().replace("-", "").replace(" ", "")
            # Direct lookup by model keyword
            for kw, ver in _ext_sp_by_model.items():
                if kw.startswith("_"):  # skip _comment keys
                    continue
                kw_norm = kw.upper().replace("-", "").replace(" ", "")
                if kw_norm in model_upper or model_upper.startswith(kw_norm):
                    return ver, "external_baseline"
            # Family keyword fallback
            for fam in _ext_sp_families:
                for kw in fam.get("modelKeywords", []):
                    kw_norm = kw.upper().replace("-", "").replace(" ", "")
                    if kw_norm in model_upper:
                        return fam.get("latestKnown", ""), "external_baseline_family"
            return None, None

        def _resolve_ext_ontap_branch(os_version):
            """Find the latest P-release for this system's ONTAP branch."""
            if not os_version or not _ext_ontap_by_branch:
                return None
            import re as _re_br
            # Extract branch: "9.16.1P11" → "9.16.1", "9.8P20" → "9.8"
            m = _re_br.match(r'(\d+\.\d+(?:\.\d+)?)', os_version)
            if m:
                branch = m.group(1)
                return _ext_ontap_by_branch.get(branch)
            return None

        # Override _latest_fw_by_model with external baselines
        _ext_override_count = 0
        for _model_key in list(_latest_fw_by_model.keys()):
            _ext_ver, _ext_src = _resolve_ext_sp_bmc(_model_key)
            if _ext_ver:
                _latest_fw_by_model[_model_key]["version"] = _ext_ver
                _latest_fw_by_model[_model_key]["_source"] = _ext_src
                _ext_override_count += 1
        # Also override shelf module baselines
        for _mod_name, _mod_data in _ext_shelf_modules.items():
            if not isinstance(_mod_data, dict):
                continue
            _rec = _mod_data.get("recommended", "")
            if _rec and _rec != "current":
                _latest_shelf_fw_by_module[_mod_name] = _rec
        if _ext_override_count > 0 or _ext_shelf_modules:
            print(f"  [HARVEST] Applied external baselines: {_ext_override_count} SP/BMC overrides, {len(_ext_shelf_modules)} shelf module baselines", flush=True)

        # Also override drive firmware baselines from external baselines JSON
        _ext_disk_fw = (_ext_baselines.get("diskFirmware") or {}).get("byModel") or {}
        _ext_drive_fw_count = 0
        for _dm, _dv in _ext_disk_fw.items():
            if _dm.startswith("_"):  # skip _comment keys
                continue
            if isinstance(_dv, str) and _dv:
                _latest_drive_fw[_dm] = _dv
                _ext_drive_fw_count += 1
        if _ext_drive_fw_count > 0:
            print(f"  [HARVEST] Applied external drive firmware baselines: {_ext_drive_fw_count} drive models", flush=True)

        # ── Override drive firmware baselines with DQP data (if available) ──
        # The DQP (Disk Qualification Package) contains per-drive-model qualified
        # firmware revisions. When qual_devices_v3.zip or qual_devices.xml is present
        # in the data/ directory, its data overrides the GQL-derived _latest_drive_fw.
        _dqp_override_count = 0
        try:
            import sys as _sys_mod
            _tools_dir = os.path.join(os.path.dirname(__file__), "tools")
            if _tools_dir not in _sys_mod.path:
                _sys_mod.path.insert(0, _tools_dir)
            from dqp_parser import load_dqp_drive_baselines
            _dqp_baselines = load_dqp_drive_baselines(
                data_dir=os.path.join(os.path.dirname(__file__), "data")
            )
            if _dqp_baselines:
                for _dm, _dv in _dqp_baselines.items():
                    _latest_drive_fw[_dm] = _dv
                    _dqp_override_count += 1
                print(f"  [HARVEST] Applied DQP drive firmware baselines: {_dqp_override_count} drive models", flush=True)
        except ImportError:
            pass  # dqp_parser not available — skip silently
        except Exception as _dqp_err:
            print(f"  [HARVEST] DQP load warning: {_dqp_err}", flush=True)

        # ── Auto-discover drive firmware baselines from the fleet itself ──
        # For any drive model not yet in _latest_drive_fw, use the highest firmware
        # version seen across the fleet as a best-effort recommendation.
        _fleet_drive_models = {}  # model → {fw_version: count}
        for s in all_systems:
            for _shelf in (s.get("shelves") or []):
                for _drv in ((_shelf.get("drives") or {}).get("drives") or []):
                    _dm = ((_drv.get("hardwareModel") or {}).get("name") or "").strip()
                    _dfw = (_drv.get("firmwareRevision") or "").strip()
                    if _dm and _dfw and _dfw != "Unknown":
                        if _dm not in _fleet_drive_models:
                            _fleet_drive_models[_dm] = {}
                        _fleet_drive_models[_dm][_dfw] = _fleet_drive_models[_dm].get(_dfw, 0) + 1
        _auto_discovered = 0
        for _dm, _fw_counts in _fleet_drive_models.items():
            if _dm not in _latest_drive_fw:
                # Use the most common firmware version (or highest if tied) as baseline
                _best_fw = max(_fw_counts.keys(), key=lambda v: (_fw_counts[v], v))
                _latest_drive_fw[_dm] = _best_fw
                _auto_discovered += 1
        if _auto_discovered > 0:
            print(f"  [HARVEST] Auto-discovered drive firmware baselines from fleet: {_auto_discovered} models", flush=True)

        # 13. Build final systems output (with full TAM enrichment)
        systems_out = []
        for s in all_systems:
            cust = s.get("customer") or {}
            site = s.get("site") or {}
            hw = s.get("hardwareModel") or {}
            contact = s.get("contactPerson") or {}
            contract = s.get("contract") or {}
            asup = s.get("latestAsup") or {}
            # Active IQ's `latestAsup` frequently has subject/type/isManual as null even
            # when receivedDate/asupId are populated — the same data (correctly filled in)
            # is present in the `autoSupports` history list. Fall back to the most recent
            # history entry (matched by asupId when possible) for those specific fields.
            if not asup.get("subject") or not asup.get("type") or asup.get("isManual") is None:
                _asup_hist = s.get("autoSupports") or []
                _asup_match = next((a for a in _asup_hist if a.get("asupId") == asup.get("asupId")), None) \
                    or (_asup_hist[0] if _asup_hist else None)
                if _asup_match:
                    asup = dict(asup)
                    for _k in ("subject", "type", "isManual"):
                        if asup.get(_k) is None or asup.get(_k) == "":
                            asup[_k] = _asup_match.get(_k)
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
            # Fallback: derive cluster name from hostname by stripping node suffix
            # e.g. "A150-CLUSTER-01" → "A150-CLUSTER", "FAS8300-node2" → "FAS8300"
            if not cl_name:
                _hn = s.get("hostName", "") or ""
                cl_name = re.sub(r'[-_](?:0[1-9]|node\d+|n\d+)$', '', _hn, flags=re.IGNORECASE)
            cl_cap = serial_to_cluster_cap.get(serial, {})

            # Extract switches from port connectivity (device names + port types)
            # _sys_is_mcc: real harvested isMetroCluster flag for the parent system —
            # used to flag which of this system's switches sit on a MetroCluster ISL
            # so the Switch Validation UI can apply MC-specific ISL requirement
            # context (TR-published distance/packet-loss/jitter/MTU limits) instead
            # of generic cluster-interconnect validation. This is NOT derived from a
            # guessed switch "role" enum value (unconfirmed against live Active IQ
            # data) — it only uses the confirmed-real per-system isMetroCluster field.
            _sys_is_mcc = bool(s.get("isMetroCluster"))
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
                        "mcContext": _sys_is_mcc,
                    })

            # Merge cluster-level switches (with model, firmware, validation data)
            cl_switches = serial_to_cluster_switches.get(serial, [])
            for csw in cl_switches:
                sw_serial = csw.get("switchSerialNumber", "") or ""
                vi = csw.get("versionInfo") or {}
                fw = vi.get("fwVersion", "") or ""
                rcf = vi.get("rcfVersion", "") or ""
                is_monitored  = csw.get("isMonitored", False)
                is_discovered = csw.get("isDiscovered", False)
                sw_model  = csw.get("model")  or ""
                sw_vendor = csw.get("vendor") or ""
                sw_name   = csw.get("deviceName") or ""
                sw_role   = csw.get("role") or "Cluster Interconnect"
                sw_ip     = csw.get("ipAddress") or ""

                # ── Infer model from device name when AIQ returns OTHER / blank ──
                # Typical names: "zaDEL-DC1-LEAF-1001(FDO22452V0T)", "Nexus3132Q-V"
                if not sw_model or sw_model.upper() == "OTHER":
                    dn_lower = sw_name.lower()
                    if any(x in dn_lower for x in ("nexus 9", "nexus9", "n9k", "93", "9336", "9364", "9332")):
                        sw_model = "Cisco Nexus 9k"
                    elif any(x in dn_lower for x in ("nexus 3", "nexus3", "n3k", "3132", "3064", "3548")):
                        sw_model = "Cisco Nexus 3k"
                    elif any(x in dn_lower for x in ("mds", "cisco mds")):
                        sw_model = "Cisco MDS"
                    elif any(x in dn_lower for x in ("sn2100", "nvidia", "cumulus")):
                        sw_model = "NVIDIA SN2100"
                    elif any(x in dn_lower for x in ("bes-53248", "bes53248", "efos", "broadcom")):
                        sw_model = "Broadcom BES-53248"
                    elif any(x in dn_lower for x in ("g620", "g630", "g720", "brocade", "fos")):
                        sw_model = "Brocade FC Switch"
                    elif sw_vendor:
                        sw_model = sw_vendor
                    # Still nothing — use the device name (already the most descriptive thing we have)
                    if not sw_model:
                        sw_model = sw_name or "Unknown Switch"

                # ── Status / validation ──────────────────────────────────────────
                status = "Optimal"
                if not is_monitored and not is_discovered:
                    status = "Unknown"
                    validation = (f"Switch '{sw_name}' (IP: {sw_ip}) was not discovered or monitored by Active IQ. "
                                  f"Verify CSHM is configured and the switch is reachable.")
                elif not is_monitored:
                    status = "Warning"
                    validation = (f"Switch '{sw_name}' is discovered but not actively monitored by CSHM. "
                                  f"Enable CSHM health monitoring for proactive alerting and firmware recommendations.")
                elif csw.get("model", "").upper() in ("OTHER", "") or not csw.get("model"):
                    status = "Warning"
                    validation = (f"Switch '{sw_name}' (IP: {sw_ip}) is monitored but its model is not recognized "
                                  f"by Active IQ. Verify IMT compatibility and confirm CSHM switch-type mapping.")
                else:
                    validation = f"Switch '{sw_name}' firmware validated by Active IQ CSHM."

                # ── targetFirmware: only use RCF if it differs from current fw ──
                # When rcf == fw (or rcf is blank) the API has no upgrade recommendation
                target_fw = rcf if (rcf and rcf != fw) else ""

                # ── RCF (Reference Configuration File) compliance ──────────────
                # rcfVersion is harvested and already used to compute target_fw
                # above, but was never surfaced as its own explicit signal — a
                # switch running the wrong RCF is a real compliance gap distinct
                # from "firmware is outdated". True = current fw matches the RCF
                # NetApp has on file; False = a mismatch was detected; None =
                # Active IQ hasn't reported an RCF version for this switch at all
                # (can't assess compliance, not the same as "non-compliant").
                if not rcf:
                    rcf_compliant = None
                else:
                    rcf_compliant = (rcf == fw)

                switches.append({
                    "type":              sw_role,
                    "model":             sw_model,
                    "serialNumber":      sw_serial if sw_serial else "Not available",
                    "firmware":          fw  if fw  else "Not reported",
                    "targetFirmware":    target_fw,   # "" → UI shows "N/A"
                    "rcfVersion":        rcf if rcf else "",
                    "rcfCompliant":      rcf_compliant,
                    "status":            status,
                    "ipAddress":         sw_ip,
                    "validationDetails": validation,
                    "deviceName":        sw_name,
                    "vendor":            sw_vendor,
                    "isMonitored":       is_monitored,
                    "isDiscovered":      is_discovered,
                    "mcContext":         _sys_is_mcc,
                })

            # Merge cluster-level shelves
            cl_shelves = serial_to_cluster_shelves.get(serial, [])
            shelves_out = s.get("shelves") or []
            seen_shelf_sns = {sh.get("serialNumber") for sh in shelves_out if sh.get("serialNumber")}
            for csh in cl_shelves:
                csh_sn = csh.get("serialNumber", "")
                if csh_sn in seen_shelf_sns:
                    continue  # don't duplicate per-system shelves
                seen_shelf_sns.add(csh_sn)
                hm = csh.get("hardwareModel") or {}
                mmhm = csh.get("moduleHardwareModel") or {}
                drives_raw = csh.get("drives") or {}
                shelves_out.append({
                    "serialNumber": csh_sn,
                    "shelfId": csh.get("shelfId", ""),
                    "model": hm.get("name", ""),
                    "hardwareModel": {"name": hm.get("name", ""), "endOfAvailability": hm.get("endOfAvailability", ""), "endOfHwSupport": hm.get("endOfHwSupport", "")},
                    "endOfAvailability": hm.get("endOfAvailability", ""),
                    "endOfHwSupport": hm.get("endOfHwSupport", ""),
                    "moduleHardwareModel": {"name": mmhm.get("name", "")},
                    "drives": drives_raw,
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
                    "utilPct": round(mutil, 1) if mutil else None,
                    "qoqPct":  mp.get("qoqUtilizationPercentage"),
                    "effRatio": mep.get("efficiencyRatio"),
                    "logUsedTB": round((ml.get("usedKiB") or 0) / (1024**3), 3),
                })
            # Per-month fallback: the API can populate rawMarketingKiB for a month
            # while leaving that month's usedKiB (and utilizationPercentage) null at
            # the system level even though the cluster-level monthlyCapacity has a
            # real usedTB for the same month — merge it in rather than showing "—".
            _cl_monthly_by_month = {m.get("month"): m for m in (cl_cap.get("monthlyCapacity") or []) if m.get("month")}
            for _sm in _sys_monthly:
                if not _sm.get("usedTB"):
                    _cl_m = _cl_monthly_by_month.get(_sm.get("month"))
                    if _cl_m and _cl_m.get("usedTB"):
                        _sm["usedTB"] = _cl_m["usedTB"]
            _raw_kib  = _sys_phys.get("rawMarketingKiB") or 0
            _used_kib = _sys_phys.get("usedKiB") or 0
            _used_no_snap_kib = _sys_phys.get("usedWithoutSnapshotsKiB") or 0
            _log_kib  = _sys_log.get("usedKiB") or 0
            _log_no_snap_kib = _sys_log.get("usedWithoutSnapshotsClonesKiB") or 0
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
                _used_no_snap_kib = cl_cap.get("physicalUsedNoSnapsTB", 0) * (1024**3)
                _log_no_snap_kib  = cl_cap.get("logicalUsedNoSnapsTB", 0) * (1024**3)
                _usbl_kib = cl_cap.get("usableCapacityTB", 0) * (1024**3)
                _qoq      = cl_cap.get("qoqUtilizationPct", 0)
                _yoy      = cl_cap.get("yoyUtilizationPct", 0)
            # Independent per-field fallback: the API can populate rawMarketingKiB/
            # usablePerformanceTierKiB at the system level while leaving usedKiB (and
            # logical usedKiB) null — the block above only fires when _raw_kib is ALSO
            # zero, so this case (raw/usable present, used genuinely missing) fell
            # through with a permanently-0.00 TB "Physical Used"/"Logical" display.
            if _used_kib == 0:
                _cl_used = cl_cap.get("physicalUsedTB", 0) * (1024**3)
                if _cl_used > 0:
                    _used_kib = _cl_used
            if _log_kib == 0:
                _cl_log = cl_cap.get("logicalUsedTB", 0) * (1024**3)
                if _cl_log > 0:
                    _log_kib = _cl_log

            # ── Derive firmware from osVersions catalog if per-system GQL returned null ──
            _raw_sfw = s.get("systemFirmware") or {}
            _raw_mbfw = s.get("motherboardFirmware") or {}
            _raw_dqp = s.get("diskQualificationPackage") or {}
            _sys_model = hw.get("name", "")
            _sys_os = s.get("osVersion", "") or ""
            _sys_platform = s.get("platformType", "") or s.get("_source_platform", "") or ""
            _sys_type_lower = (s.get("type") or "").lower()

            # ── E-Series: SANtricity OS version IS the firmware ──
            _is_eseries = (_sys_platform.upper() == "E-SERIES"
                           or _sys_type_lower == "efiler"
                           or _sys_type_lower == "e-series"
                           or (s.get("productType") or "").upper() in ("EFILER", "E-SERIES")
                           or (_sys_model[:2] in ("28", "48") and _sys_model[:4].isdigit()))
            if _is_eseries:
                _rec_os = s.get("recommendedOSVersion", "") or ""
                if _sys_os:
                    _raw_sfw = {
                        "type": "SANtricity",
                        "currentVersion": _sys_os,
                        "recommendedVersion": _rec_os or _sys_os,
                        "_derived": True,
                    }
                    # E-Series doesn't have separate MB firmware
                    _raw_mbfw = {}
                    _raw_dqp = {}
                    _fw_derived += 1
            elif (not _raw_sfw.get("currentVersion")) and _sys_model and _sys_os:
                # Try exact match first
                _bundled = _fw_by_os_model.get((_sys_os, _sys_model))
                if not _bundled:
                    # Progressive prefix fallback: 9.16.1P11 → 9.16.1P → 9.16.1 → 9.16 → 9.
                    import re as _re_fw
                    _prefixes = []
                    _m = _re_fw.match(r'(\d+\.\d+(?:\.\d+)?(?:P)?)(\d*)', _sys_os)
                    if _m:
                        _prefixes.append(_m.group(1))          # e.g. "9.16.1P"
                    _m2 = _re_fw.match(r'(\d+\.\d+\.\d+)', _sys_os)
                    if _m2:
                        _prefixes.append(_m2.group(1))         # e.g. "9.16.1"
                    _m3 = _re_fw.match(r'(\d+\.\d+)', _sys_os)
                    if _m3:
                        _prefixes.append(_m3.group(1))         # e.g. "9.16"
                    # De-duplicate while preserving order
                    _seen_pfx = set()
                    for _pfx in _prefixes:
                        if _pfx in _seen_pfx:
                            continue
                        _seen_pfx.add(_pfx)
                        _candidates = [(k[0], v) for k, v in _fw_by_os_model.items()
                                       if k[1] == _sys_model and k[0].startswith(_pfx)]
                        if _candidates:
                            _candidates.sort(key=lambda x: x[0])
                            _bundled = _candidates[-1][1]
                            break
                # Final fallback: use the latest known firmware for this model from ANY version
                if not _bundled:
                    _bundled = _latest_fw_by_model.get(_sys_model)
                _latest = _latest_fw_by_model.get(_sys_model)
                if _bundled:
                    _raw_sfw = {
                        "type": _bundled["type"],
                        "currentVersion": _bundled["version"],
                        "recommendedVersion": _latest["version"] if _latest else _bundled["version"],
                        "_derived": True,
                    }
                    _raw_mbfw = {
                        "currentVersion": _bundled.get("biosVersion", ""),
                        "recommendedVersion": _latest.get("biosVersion") if _latest else _bundled.get("biosVersion", ""),
                        "_derived": True,
                    }
                    _fw_derived += 1

            # ── Override SP/BMC recommendedVersion with external ground-truth ──
            if not _is_eseries:
                _ext_sp_ver, _ext_sp_src = _resolve_ext_sp_bmc(_sys_model)
                if _ext_sp_ver and _raw_sfw.get("currentVersion"):
                    _raw_sfw["recommendedVersion"] = _ext_sp_ver
                    _raw_sfw["_recommendedSource"] = _ext_sp_src

            # ── Derive DQP from bundled drive firmware catalog ──
            # DQP version = the ONTAP version that bundles the drive qualification package.
            # If a system's ONTAP version has bundled drive firmware entries, it ships with that DQP.
            # The "latest" recommended DQP is the one from the latest ONTAP P-release for same major.
            if (not _raw_dqp.get("currentVersion")) and _sys_os and not _is_eseries:
                # Current DQP = whatever ships with the system's current ONTAP version
                _cur_dqp = _drive_fw_by_os.get(_sys_os)
                if _cur_dqp:
                    # Find the recommended (latest) version for same major branch
                    import re as _re_dqp
                    _major_match = _re_dqp.match(r'(\d+\.\d+\.\d+)', _sys_os)
                    _rec_dqp_ver = _sys_os  # default: current version IS recommended
                    if _major_match:
                        _major = _major_match.group(1)
                        _branch_versions = sorted([v for v in _drive_fw_by_os.keys() if v.startswith(_major)])
                        if _branch_versions:
                            _rec_dqp_ver = _branch_versions[-1]
                    _raw_dqp = {
                        "currentVersion": _sys_os,
                        "recommendedVersion": _rec_dqp_ver,
                        "_derived": True,
                    }

            # ── Override ONTAP recommendedOSVersion with external branch baseline ──
            if not _is_eseries:
                _ext_branch_latest = _resolve_ext_ontap_branch(_sys_os)
                if _ext_branch_latest:
                    _existing_rec_os = s.get("recommendedOSVersion", "") or ""
                    # Use the external baseline if it's newer or if AIQ didn't provide one
                    if not _existing_rec_os or _ext_branch_latest > _existing_rec_os:
                        s["recommendedOSVersion"] = _ext_branch_latest
                        s["_recommendedOSSource"] = "external_baseline"

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
                "originalShipDate": s.get("originalShipDate") or "",
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
                "aspEndDate": asp.get("endDate") or "",
                "domesticParentName": dp.get("name", ""),
                # ── Contract ──
                "contractActive": contract.get("isContractActive"),
                "contractEndDate": contract.get("overallContractEndDate") or "",
                "contractHWEndDate": contract.get("hardwareContractEndDate") or "",
                "contractSWEndDate": contract.get("softwareContractEndDate") or "",
                "contractNRDEndDate": contract.get("nrdContractEndDate") or "",
                "contractExpiry": contract.get("expiryDate") or "",
                "warrantyEndDate": contract.get("hardwareWarrantyEndDate") or "",
                "warrantyStartDate": contract.get("hardwareWarrantyStartDate") or "",
                "serviceLevel": contract.get("hardwareServiceLevel", ""),
                "contractSWId": contract.get("softwareContractId", ""),
                "contractHWId": contract.get("hardwareContractId", ""),
                # ── Hardware lifecycle ──
                "hwEndOfAvailability": hw.get("endOfAvailability", ""),
                "hwEndOfSupport": hw.get("endOfSupport", ""),
                "eosEarliest": eos.get("earliestEndOfSupportDate") or "",
                "eosShelf": eos.get("earliestShelfEndOfSupportDate") or "",
                "eosDisk": eos.get("earliestDiskEndOfSupportDate") or "",
                "eosPVR": eos.get("latestPVRDate") or "",
                "eosLatest": eos.get("latestEndOfSupportDate") or "",
                # ── Software version details ──
                "softwareVersionFull": sv.get("fullVersionString", ""),
                "swReleaseDate": evd.get("releaseDate") or "",
                "swEndOfFullSupport": evd.get("endOfVersionFullSupport", ""),
                "swEndOfLimitedSupport": evd.get("endOfVersionLimitedSupport", ""),
                "swEndOfSelfService": evd.get("endOfSelfServiceSupport", ""),
                "swRecMin": srd.get("minRecommendedVersion", ""),
                "swRecLatest": srd.get("latestRecommendedVersion", ""),
                "swCQV": (srd.get("cqvDetails") or {}).get("qualifiedVersion", ""),
                # ── ONTAP flags ──
                "isMetroCluster": s.get("isMetroCluster"),
                "isAllFlashOptimized": s.get("isAllFlashOptimized"),
                "isARPEnabled": s.get("isARPEnabled"),
                "operatingMode": s.get("operatingMode", ""),
                "propensityCategory": s.get("propensityCategory", ""),
                "nextBestAction": s.get("nextBestAction", ""),
                "serviceProcessorIP": s.get("serviceProcessorIPAddress", ""),
                "autoUpdateEnabled": s.get("autoUpdateEnabled"),
                # ASA r2: SAZ-level capacity (no aggregates; pull from storageAvailabilityZone)
                "sazTotalRawKiB": 0,
                "sazUsedKiB": 0,
                "sazAvailableKiB": 0,
                # ── AutoSupport ──
                "latestAsupDate": asup.get("receivedDate") or asup.get("generatedDate") or "",
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
                "systemFirmware": _raw_sfw,
                "motherboardFirmware": _raw_mbfw,
                "diskQualificationPackage": _raw_dqp,
                # Note: "shelves" is set further down using shelves_out (merged per-system + cluster shelves)
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
                # TB-scale aliases that app.js enrichSystemTelemetry reads directly
                "clusterPhysicalUsedTB": round(_used_kib / (1024**3), 3) if _used_kib else 0,
                "clusterRawCapacityTB":  round(_raw_kib  / (1024**3), 3) if _raw_kib  else 0,
                "clusterUsableCapacityTB": round(_usbl_kib / (1024**3), 3) if _usbl_kib else 0,
                "clusterLogicalUsedTB": round(_log_kib / (1024**3), 3) if _log_kib else 0,
                "physicalUsedNoSnapsTB": round(_used_no_snap_kib / (1024**3), 3) if _used_no_snap_kib else 0,
                "logicalUsedNoSnapsTB": round(_log_no_snap_kib / (1024**3), 3) if _log_no_snap_kib else 0,
                "dataReductionRatio": _data_red or cap_eff.get("dataReductionRatio"),
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
                # ── Aggregate / Volume / SVM topology counts ──
                "localTierCount": (s.get("storageAggregates") or {}).get("totalCount", 0) or 0,
                "volumeCount": (s.get("storageVolumes") or {}).get("totalCount", 0) or 0,
                "lunCount": (s.get("luns") or {}).get("totalCount", 0) or 0,
                "dataSvmCount": sum(1 for v in serial_to_cluster_vservers.get(serial, []) if (v.get("type") or "").lower() == "data"),
                "nodeSvmCount": sum(1 for v in serial_to_cluster_vservers.get(serial, []) if (v.get("type") or "").lower() == "node"),
                # ── Shelves, drives, ports, switches ──
                "shelves": shelves_out,
                "recommendedDriveFirmwares": _latest_drive_fw if _latest_drive_fw else (_drive_fw_by_os.get(_sys_os) or _drive_fw_by_os.get(s.get("recommendedOSVersion", "")) or {}),
                # Filter shelf firmware to only modules actually installed on this system
                "recommendedShelfFirmwares": {mod: _shelf_fw_by_os_module.get((_sys_os, mod)) or _latest_shelf_fw_by_module.get(mod, "") for mod in _latest_shelf_fw_by_module if mod in {(_sh.get("moduleHardwareModel") or {}).get("name", "") for _sh in shelves_out if (_sh.get("moduleHardwareModel") or {}).get("name", "")}} if not _is_eseries else {},
                "portInterface": s.get("portInterface") or {},
                "networkPorts": s.get("networkPorts") or {},
                "switches": switches,
                "vservers": serial_to_cluster_vservers.get(serial, []),
                "vcenters": s.get("vcenters") or [],
                # ── Risks & cases ──
                "risks": risks_by_serial.get(serial, []),
                "cases": cases_by_serial.get(serial, []),
                "_source": "graphql",
            })

        if _fw_derived:
            print(f"  [HARVEST] Firmware derived from osVersions catalog for {_fw_derived}/{len(systems_out)} systems", flush=True)

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
                                    wid = wl.get("watchListId") or wl.get("watchlistId") or wl.get("id", "")
                                    wname = wl.get("watchListName") or wl.get("watchlistName") or wl.get("name", "Watchlist")
                                    if wid:
                                        watchlists_out.append({"id": wid, "name": wname, "systemSerials": []})
                            if watchlists_out:
                                print(f"  [HARVEST] Watchlists: {len(watchlists_out)} from {wl_path}", flush=True)
                                # Persist resolved names so fallback runs keep real names
                                try:
                                    _cfg_w = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
                                    _cfg_w["watchlistNames"] = {w["id"]: w["name"] for w in watchlists_out}
                                    CONFIG_PATH.write_text(json.dumps(_cfg_w, indent=2), encoding="utf-8")
                                except Exception:
                                    pass
                                break
                except Exception:
                    pass
        except Exception as e:
            print(f"  [HARVEST] Watchlist fetch skipped: {e}", flush=True)

        # 14a. Fallback: try GQL watchlists query if REST returned nothing
        # (see the matching NOTE above — this field does not exist in the current
        # schema, confirmed via live introspection; kept for forward-compatibility)
        if not watchlists_out:
            try:
                _, wl_gql_resp = _gql(token, "{ watchlists { id name } }")
                wl_gql_list = ((wl_gql_resp.get("data") or {}).get("watchlists") or []) if isinstance(wl_gql_resp, dict) else []
                for wl in wl_gql_list:
                    if isinstance(wl, dict):
                        wid = wl.get("id") or wl.get("watchListId") or wl.get("watchlistId") or ""
                        wname = wl.get("name") or wl.get("watchListName") or wl.get("watchlistName") or "Watchlist"
                        if wid:
                            watchlists_out.append({"id": wid, "name": wname, "systemSerials": []})
                if watchlists_out:
                    print(f"  [HARVEST] Watchlists: {len(watchlists_out)} from GQL", flush=True)
                    # Persist GQL-resolved names so fallback uses real names
                    try:
                        _cfg_w = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
                        _cfg_w["watchlistNames"] = {w["id"]: w["name"] for w in watchlists_out}
                        CONFIG_PATH.write_text(json.dumps(_cfg_w, indent=2), encoding="utf-8")
                    except Exception:
                        pass
            except Exception as _wl_gql_e:
                print(f"  [HARVEST] GQL watchlist discovery skipped: {_wl_gql_e}", flush=True)

        # 14b. Final fallback: use watchlist_ids from config — still re-resolve serials
        #      so membership changes in AIQ are always reflected, even outside network.
        if not watchlists_out and watchlist_ids:
            _cfg_names = {}
            try:
                _cfg_tmp = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
                _cfg_names = _cfg_tmp.get("watchlistNames", {})
            except Exception:
                pass
            for wid in watchlist_ids:
                watchlists_out.append({
                    "id": wid,
                    "name": _cfg_names.get(wid, f"Watchlist {wid[:8]}"),
                    "systemSerials": []
                })
            print(f"  [HARVEST] Watchlists: {len(watchlists_out)} from config (fallback)", flush=True)

        # 14c. Resolve system serial numbers for each watchlist via GraphQL
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
                        wl_sys_data = (wl_sys_resp.get("data") or {}).get("systems", {}) if isinstance(wl_sys_resp, dict) else {}
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
            "acknowledgedRisksNowExploited": acknowledged_risks_now_exploited,
            "tamRenewals": tam_renewals,
            # ── External firmware baselines (ground-truth) ──
            "firmwareBaselines": _ext_baselines,
        }

        # Tag every per-system/cluster/risk/case record with which account it
        # came from, so a merged multi-account view can still tell customers
        # apart (used by the sidebar Account filter and by _merge_account_results).
        if account:
            _acct_id = account.get("id") or "default"
            _acct_label = account.get("label") or _acct_id
            result["accountId"] = _acct_id
            result["accountLabel"] = _acct_label
            for _field in ("systems", "clusters", "risks", "cases", "tamSites", "tamRenewals"):
                for _item in (result.get(_field) or []):
                    if isinstance(_item, dict):
                        _item.setdefault("accountId", _acct_id)
                        _item.setdefault("accountLabel", _acct_label)

        print(f"  [HARVEST] Done in {duration_ms}ms: {len(systems_out)} systems, {len(all_clusters)} clusters, {len(all_risks)} unique risks, {len(all_risk_instances)} risk instances, {len(all_cases)} cases", flush=True)

        # ── Merge-back guard: preserve previous data on transient API failures ──
        # When the API times out, systems or clusters may return 0 even though the
        # data exists.  Rather than overwriting good cached data with empty arrays,
        # merge the previous harvest's systems/clusters back into the result.
        db = _init_db()
        try:
            if account:
                prev_result, _ = _load_cached_account(db, account.get("id") or "default")
            else:
                prev_result, _ = _load_cached(db)
            if prev_result:
                if len(systems_out) == 0 and len(prev_result.get("systems") or []) > 0:
                    prev_sys = prev_result["systems"]
                    print(f"  [HARVEST] Merge-back: keeping {len(prev_sys)} systems from previous harvest (current returned 0)", flush=True)
                    result["systems"] = prev_sys
                    result["totalSystems"] = len(prev_sys)
                if len(all_clusters) == 0 and len(prev_result.get("clusters") or []) > 0:
                    prev_cl = prev_result["clusters"]
                    print(f"  [HARVEST] Merge-back: keeping {len(prev_cl)} clusters from previous harvest (current returned 0)", flush=True)
                    result["clusters"] = prev_cl
                    result["totalClusters"] = len(prev_cl)

            _acct_id = account.get("id") if account else "default"
            _acct_label = (account.get("label") or account.get("id")) if account else "Default Account"
            if account:
                _save_harvest_account(db, _acct_id or "default", _acct_label or "default", result, duration_ms)
            else:
                _save_harvest(db, result, duration_ms)
            _capture_snapshots(db, result)
            _populate_reporting_tables(db, _acct_id or "default", _acct_label or "default", result)
        finally:
            db.close()

        # Trigger background enrichment for all versions found in this harvest
        # Non-blocking: runs in a separate daemon thread so it never delays the response
        try:
            t = threading.Thread(
                target=_enrich_all_versions,
                args=(result,),
                daemon=True
            )
            t.start()
            print("  [ENRICH] Post-harvest enrichment thread started.", flush=True)
        except Exception as _te:
            print(f"  [ENRICH] Could not start enrichment thread: {_te}", flush=True)

        return result

    except Exception as e:
        _last_sync_error = str(e)
        raise
    finally:
        with _sync_lock:
            _is_syncing = False


def _sync_all_accounts(extra_watchlist_ids=None):
    """Harvest every configured account, one at a time.

    Sequential (not parallel/threaded) on purpose: each account is a separate
    Active IQ credential/token exchange, and hammering NetApp's API with N
    concurrent OAuth exchanges + GraphQL queries is both impolite and more
    likely to trip rate limiting than doing them one after another. A failure
    on one account is logged and does not stop the remaining accounts from
    syncing — one customer's expired token shouldn't block everyone else's data.

    Returns {"succeeded": [account_id, ...], "failed": {account_id: error_str}}.
    """
    accounts = _get_accounts()
    if not accounts:
        raise Exception("setup_required: No Active IQ accounts configured — open Settings & Config to add at least one")

    succeeded, failed = [], {}
    for acct in accounts:
        acct_label = acct.get("label") or acct.get("id")
        print(f"  [MULTI-ACCOUNT] Syncing account '{acct_label}' ({acct.get('id')})...", flush=True)
        try:
            _do_full_harvest(watchlist_ids=extra_watchlist_ids, account=acct)
            succeeded.append(acct.get("id"))
        except Exception as e:
            print(f"  [MULTI-ACCOUNT] Account '{acct_label}' failed: {e}", flush=True)
            failed[acct.get("id")] = str(e)
    print(f"  [MULTI-ACCOUNT] Done: {len(succeeded)} succeeded, {len(failed)} failed", flush=True)
    return {"succeeded": succeeded, "failed": failed}


def _get_merged_harvest(db, account_id=None):
    """Read cached harvest data for the dashboard. With no account_id, merges
    every currently-configured account's cached result into one unified fleet
    view (this is the default — the whole point of multi-account support is
    not having to pick one). Pass account_id to scope to a single account
    instead.

    Cache rows are filtered down to accounts still present in aiq_config.json
    ("default" is always allowed, for the legacy single-token path) — an
    account removed from config stops appearing in the merged view instead of
    haunting it forever as an orphaned cache row that can never be refreshed
    or explained.
    """
    if account_id:
        result, meta = _load_cached_account(db, account_id)
        return result, [meta] if meta else []
    all_cached = _load_all_accounts_cached(db)
    configured_ids = {a["id"] for a in _get_accounts()} | {"default"}
    all_cached = [(acct_id, result, meta) for acct_id, result, meta in all_cached if acct_id in configured_ids]
    if not all_cached:
        # No per-account cache yet (fresh install, never synced) — fall back
        # to the legacy singleton table in case it has pre-migration data.
        result, meta = _load_cached(db)
        return result, [meta] if meta else []
    merged = _merge_account_results([(acct_id, result, meta) for acct_id, result, meta in all_cached])
    metas = [meta for _acct_id, _result, meta in all_cached]
    return merged, metas


def _enrich_all_versions(harvest_result):
    """
    Post-harvest enrichment pass.
    Extracts every unique software version string from the harvested systems
    and enriches it via the existing fetchers, writing results to enrich_cache.
    Skips any version that was already enriched within the last 6 days.
    Rate-limited to 1 request/second to be polite to public servers.
    """
    systems = harvest_result.get('systems', [])
    if not systems:
        return

    # Collect unique (version, platform_family) pairs
    to_enrich = {}  # key → (enrich_type, version_string)

    # ── Shared StorageGRID platform detector ──────────────────────────────────
    # Active IQ API returns platformType as raw codes (e.g. 'SG6160', 'SG5712',
    # 'SGF6112', 'SG100', 'SG1000') — NOT the human-readable prefix 'StorageGRID'.
    # We must test every known SG family prefix to avoid misclassifying these nodes
    # as ONTAP (which causes wrong enrichment type, wrong security bulletins, and
    # wrong version catalogue lookups — the corporate-network specific bug).
    def _is_storagegrid_platform(platform_str, system_type='', product_type=''):
        p = platform_str.lower()
        st = system_type.lower()
        pt = product_type.lower()
        return (
            'storagegrid' in p or 'webscale' in p or
            # SG6xxx family: SG6060, SG6160, SG6112, SG6024, SG6000-CN…
            'sg60' in p or 'sg61' in p or 'sg62' in p or 'sg6' in p or
            # SG5xxx family: SG5712, SG5760, SG5612…
            'sg5' in p or
            # SGF6xxx family: SGF6112, SGF6024, SGF6112-C…
            'sgf' in p or
            # SG100 / SG1000 admin nodes
            'sg100' in p or 'sg1000' in p or
            # Catch-all: any 'sg' prefix followed by digits (future SG families)
            (p.startswith('sg') and any(c.isdigit() for c in p[2:4])) or
            # systemType / productType fields
            st == 'storagegrid' or
            'storagegrid' in pt or 'object' in pt
        )

    for sys in systems:
        ver = sys.get('osVersion') or sys.get('ontapVersion') or sys.get('softwareVersion') or ''
        if not ver or len(ver) < 4:
            continue
        platform = sys.get('platform') or sys.get('platformModel') or sys.get('platformType') or ''
        sys_type = sys.get('systemType') or ''
        prod_type = sys.get('productType') or ''
        if _is_storagegrid_platform(platform, sys_type, prod_type):
            etype = 'sg-version'
        elif (any(k in platform.lower() for k in ('e-series', 'ef6', 'ef3', 'e5700', 'e2800', 'ef50', 'ef80', 'e4000'))
              or sys_type.lower() in ('eseries', 'e-series', 'e_series')
              or prod_type.lower() in ('eseries', 'e-series', 'e_series', 'santricity')):
            etype = 'santricity-version'
        else:
            etype = 'ontap-version'
        cache_key = f'{etype}:{ver}'
        to_enrich[cache_key] = (etype, ver)

    if not to_enrich:
        return

    print(f"  [ENRICH] Post-harvest: checking {len(to_enrich)} unique version(s)...", flush=True)
    db = _init_db()
    try:
        enriched_count = 0
        skipped_count = 0
        for cache_key, (etype, ver) in to_enrich.items():
            try:
                # Check if already cached and fresh (within 6 days)
                row = db.execute(
                    "SELECT fetched_at FROM enrich_cache WHERE cache_key = ?",
                    (cache_key,)
                ).fetchone()
                if row:
                    # Already cached — skip unless stale (> 6 days handled by purge on init)
                    skipped_count += 1
                    continue

                # Fetch from public source
                data = None
                if etype == 'ontap-version':
                    data = fetch_ontap_version_info(ver)
                elif etype == 'sg-version':
                    data = fetch_sg_version_info(ver)
                elif etype == 'santricity-version':
                    data = fetch_santricity_version_info(ver)

                if data:
                    fetched_at = datetime.now(timezone.utc).isoformat()
                    db.execute(
                        'INSERT OR REPLACE INTO enrich_cache (cache_key, result_json, fetched_at, source) VALUES (?, ?, ?, ?)',
                        (cache_key, json.dumps(data), fetched_at, 'docs.netapp.com')
                    )
                    db.commit()
                    enriched_count += 1
                    print(f"  [ENRICH] {cache_key} — OK", flush=True)

                # Rate limit: 1 req/sec to be polite
                time.sleep(1.0)

            except Exception as _e:
                print(f"  [ENRICH] {cache_key} failed: {_e}", flush=True)
                continue
        print(f"  [ENRICH] Post-harvest complete: {enriched_count} enriched, {skipped_count} already cached.", flush=True)

        print("  [ENRICH] Refreshing version catalog...", flush=True)
        try:
            catalog = fetch_latest_version_catalog()
            if catalog:
                db.execute(
                    'INSERT OR REPLACE INTO enrich_cache (cache_key, fetched_at, result_json, source) VALUES (?, ?, ?, ?)',
                    ('_catalog:versions', datetime.now(timezone.utc).isoformat(), json.dumps(catalog), 'docs.netapp.com')
                )
                db.commit()
        except Exception as e:
            print(f"  [ENRICH] Failed to refresh version catalog: {e}", flush=True)

    finally:
        db.close()


def _background_sync():
    """Run a full harvest in the background. Errors are logged, not raised."""
    try:
        # Read all watchlist IDs from config for background sync
        wl_ids = []
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
            # Support both new watchlistIds (comma-sep) and legacy watchlistId (single).
            # Only use watchlistId (legacy) if watchlistIds is empty; ignore placeholder 'wl_prod'.
            ids_str = cfg.get("watchlistIds") or cfg.get("watchlist_id") or ""
            if not ids_str:
                legacy = cfg.get("watchlistId") or ""
                if legacy and legacy != "wl_prod" and not legacy.startswith("wl_"):
                    ids_str = legacy
            wl_ids = [w.strip() for w in ids_str.split(",") if w.strip()]
        except Exception:
            pass
        scope_msg = f" ({len(wl_ids)} watchlist(s))" if wl_ids else " (all systems)"
        accounts = _get_accounts()
        print(f"  [BACKGROUND] Starting background re-sync{scope_msg} across {len(accounts)} account(s)...", flush=True)
        _sync_all_accounts(extra_watchlist_ids=wl_ids)
        print("  [BACKGROUND] Background re-sync complete.", flush=True)
        # Trigger enrichment scan after harvest — both groups. The fast group
        # (CVE/KEV/PSIRT/EPSS + OS version catalog) already ran on every
        # harvest; the slow-crawl group (firmware baselines, EOA/IMT, switch
        # firmware, and new-platform/hardware discovery) previously ONLY ran
        # on its own independent 7-day timer, so a fleet could go a full week
        # without a harvest ever refreshing platform/switch/firmware/drive/
        # card data even if the user was syncing constantly. Both calls are
        # cheap to make often: each sub-scanner inside _do_kb_scan checks its
        # own file's staleness first and no-ops in milliseconds if nothing is
        # actually due, so this does not mean re-hitting docs.netapp.com/
        # GitHub/PyPI on every single harvest — only when data has genuinely
        # gone stale.
        global _enrichment_scheduler
        if _enrichment_scheduler:
            if not _enrichment_scheduler._running:
                print('  [BACKGROUND] Triggering post-harvest fast enrichment scan...', flush=True)
                _enrichment_scheduler.run_now()
            if not _enrichment_scheduler._kb_running:
                print('  [BACKGROUND] Checking platform/switch/firmware/hardware freshness (staleness-gated)...', flush=True)
                _enrichment_scheduler.run_kb_now()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"  [BACKGROUND] Sync failed: {e}", flush=True)



# ─────────────────────────────────────────────────────────────────────
# Enrichment Engine — public-source data fetchers
# ─────────────────────────────────────────────────────────────────────

import re as _re
import html as _html
from html.parser import HTMLParser

_ENRICH_UA = 'AIQ-Advisor/1.0 (enrichment; public data only)'


def _enrich_fetch(url, timeout=12, extra_headers=None):
    """Fetch URL, return (text, error). Uses the shared proxy-aware opener so that
    on corporate networks (Zscaler/WPAD) the request is correctly routed through
    the system HTTP proxy — docs.netapp.com, nvd.nist.gov, security.netapp.com
    are all proxied on corporate networks and fail silently without this.
    Falls back to a cert-store refresh + opener rebuild on any TLS error.
    extra_headers: optional dict merged into the request (e.g. NVD's apiKey,
    which NVD API 2.0 only accepts as a header — passing it as a query string
    parameter silently 404s regardless of whether the key is valid)."""
    global _opener_cache
    headers = {'User-Agent': _ENRICH_UA}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    try:
        with _get_opener().open(req, timeout=timeout) as r:
            return r.read().decode('utf-8', errors='replace'), None
    except ssl.SSLError as e:
        # Auto-refresh cert store, rebuild opener, and retry once
        _refresh_ssl_ctx()
        _opener_cache = None  # force rebuild with refreshed SSL context
        try:
            with _get_opener().open(req, timeout=timeout) as r:
                return r.read().decode('utf-8', errors='replace'), None
        except Exception as e2:
            return None, str(e2)
    except Exception as e:
        err_str = str(e)
        # Also catch TLS errors wrapped inside urllib exceptions (e.g. from proxy)
        if any(k in err_str for k in ('SSL', 'CERTIFICATE', 'certificate verify failed',
                                       'UNABLE_TO_VERIFY', 'DEPTH_ZERO', 'CERT_UNTRUSTED')):
            _refresh_ssl_ctx()
            _opener_cache = None
            try:
                with _get_opener().open(req, timeout=timeout) as r:
                    return r.read().decode('utf-8', errors='replace'), None
            except Exception as e2:
                return None, str(e2)
        return None, err_str


def _strip_html_tags(text):
    """Remove HTML tags, decode entities, collapse whitespace. Skips <script>/<style> content."""
    class Stripper(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []
            self._skip = False
        def handle_starttag(self, tag, attrs):
            if tag.lower() in ('script', 'style', 'noscript', 'svg'):
                self._skip = True
        def handle_endtag(self, tag):
            if tag.lower() in ('script', 'style', 'noscript', 'svg'):
                self._skip = False
        def handle_data(self, data):
            if not self._skip:
                self.parts.append(data)
    s = Stripper()
    s.feed(text)
    cleaned = ' '.join(s.parts)
    cleaned = _re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def fetch_cve_nvd(cve_id, api_key=None):
    """
    Query NIST NVD API v2 for a CVE.
    Returns dict: {id, description, cvss, severity, publishedDate, references, affectedVersions}
    or None on failure.

    Rate-limited to respect NVD's 5 requests / 30 seconds (no API key) or
    50 requests / 30 seconds (with API key).
    """
    # ── Rate limiter: token bucket ─────────────────────────────────────────────
    if not hasattr(fetch_cve_nvd, '_timestamps'):
        fetch_cve_nvd._timestamps = []
    window = 30  # seconds
    max_calls = 50 if api_key else 5
    now = time.time()
    fetch_cve_nvd._timestamps = [t for t in fetch_cve_nvd._timestamps if now - t < window]
    if len(fetch_cve_nvd._timestamps) >= max_calls:
        sleep_time = window - (now - fetch_cve_nvd._timestamps[0]) + 0.5
        if sleep_time > 0:
            time.sleep(sleep_time)
        fetch_cve_nvd._timestamps = [t for t in fetch_cve_nvd._timestamps if time.time() - t < window]
    fetch_cve_nvd._timestamps.append(time.time())

    url = f'https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={urllib.parse.quote(cve_id)}'
    # NVD API 2.0 only accepts apiKey as an HTTP header — passing it as a query
    # string parameter silently 404s regardless of whether the key is valid.
    text, err = _enrich_fetch(url, extra_headers={'apiKey': api_key} if api_key else None)
    if err or not text:
        return None
    try:
        data = json.loads(text)
        items = data.get('vulnerabilities', [])
        if not items:
            return {'id': cve_id, 'status': 'not_found'}
        vuln = items[0].get('cve', {})
        # Description
        descs = vuln.get('descriptions', [])
        desc = next((d['value'] for d in descs if d.get('lang') == 'en'), '')
        # CVSS — prefer v3.1, fallback v3.0, v2
        metrics = vuln.get('metrics', {})
        cvss_score = None
        severity = None
        for key in ('cvssMetricV31', 'cvssMetricV30', 'cvssMetricV2'):
            if key in metrics and metrics[key]:
                m = metrics[key][0].get('cvssData', {})
                cvss_score = m.get('baseScore') or metrics[key][0].get('impactScore')
                severity = m.get('baseSeverity') or metrics[key][0].get('baseSeverity', '')
                break
        # Published date
        published = vuln.get('published', '')[:10]
        # References
        refs = [r.get('url', '') for r in vuln.get('references', [])[:5]]
        # Affected versions from CPE
        affected = []
        for cfg in vuln.get('configurations', []):
            for node in cfg.get('nodes', []):
                for cpe in node.get('cpeMatch', []):
                    if cpe.get('vulnerable'):
                        vi = cpe.get('versionStartIncluding', '')
                        ve = cpe.get('versionEndExcluding', '')
                        ve2 = cpe.get('versionEndIncluding', '')
                        if vi or ve or ve2:
                            affected.append(f">={vi}" if vi else '' + (f' <{ve}' if ve else '') + (f' <={ve2}' if ve2 else ''))
        return {
            'id': cve_id,
            'description': desc,
            'cvss': cvss_score,
            'severity': (severity or 'UNKNOWN').upper(),
            'publishedDate': published,
            'references': refs,
            'affectedVersions': '; '.join(affected[:3]) if affected else 'See NVD for affected versions'
        }
    except Exception as e:
        return {'id': cve_id, 'error': str(e)}


def fetch_netapp_psirt(advisory_id):
    """
    Fetch and parse a NetApp PSIRT advisory page.
    Returns dict: {id, title, description, severity, affectedProducts, publishedDate, link}
    """
    url = f'https://security.netapp.com/advisory/{urllib.parse.quote(advisory_id)}/'
    text, err = _enrich_fetch(url)
    if err or not text:
        return None
    try:
        # Extract title
        title_m = _re.search(r'<title>([^<]+)</title>', text, _re.IGNORECASE)
        title = _strip_html_tags(title_m.group(1)) if title_m else advisory_id
        # Extract severity from page content
        sev_m = _re.search(r'(?:severity|risk)[\s:]*<[^>]*>\s*([A-Za-z]+)', text, _re.IGNORECASE)
        severity = sev_m.group(1).upper() if sev_m else 'UNKNOWN'
        # Get first substantial paragraph of content as description
        content_m = _re.search(r'<div[^>]*class="[^"]*description[^"]*"[^>]*>(.*?)</div>', text, _re.IGNORECASE | _re.DOTALL)
        if not content_m:
            content_m = _re.search(r'<p>((?:(?!</p>).){80,500})</p>', text, _re.DOTALL)
        description = _strip_html_tags(content_m.group(1))[:800] if content_m else ''
        # Extract CVE IDs from page
        cves = list(dict.fromkeys(_re.findall(r'CVE-\d{4}-\d+', text)))[:10]
        # Extract published date
        date_m = _re.search(r'(?:published|date)[^>]*>\s*(\d{4}-\d{2}-\d{2})', text, _re.IGNORECASE)
        published = date_m.group(1) if date_m else ''
        return {
            'id': advisory_id,
            'title': title.replace(' | NetApp', '').strip(),
            'description': description,
            'severity': severity,
            'cve': cves,
            'published': published,
            'link': url
        }
    except Exception as e:
        return {'id': advisory_id, 'error': str(e)}


def scan_and_persist_advisories(nvd_api_key=None):
    """
    Full advisory scan pipeline:
    1. Fetch the NTAP advisory index from security.netapp.com
    2. Collect all advisory IDs (NTAP-YYYYMMDD-XXXX format)
    3. Load existing IDs from data/security_bulletins.json
    4. For each NEW advisory: fetch detail page + NVD CVSS data
    5. Upsert into data/security_bulletins.json (atomic write)
    Returns dict: {added, updated, total, scanned, errors, newIds}

    nvd_api_key: optional NVD API key for the CVSS lookup (50 req/30s instead
    of 5/30s). If not passed explicitly, read directly from aiq_config.json —
    lets callers that don't already have the key cached (HTTP handler, startup
    scan) still benefit without threading it through every call site.
    """
    import time
    added = updated = errors = 0
    new_ids = []

    if nvd_api_key is None:
        try:
            if CONFIG_PATH.exists():
                nvd_api_key = json.loads(CONFIG_PATH.read_text(encoding='utf-8')).get('nvdApiKey') or None
        except Exception:
            nvd_api_key = None

    # ── 1. Fetch PSIRT advisory index ──────────────────────────────────────────
    print('  [SCAN] Fetching NetApp PSIRT advisory index...', flush=True)
    index_entries = []  # list of {id, title, link}
    products = ['ONTAP', 'StorageGRID', 'SnapCenter', 'Trident', 'Active+IQ']
    seen_ids = set()
    for product in products:
        url = f'https://security.netapp.com/advisory/?q={urllib.parse.quote(product)}'
        text, err = _enrich_fetch(url, timeout=20)
        if err or not text:
            print(f'  [SCAN] Index fetch failed for {product}: {err}', flush=True)
            continue
        # Match advisory hrefs: /advisory/ntap-YYYYMMDD-XXXX/
        matches = _re.findall(
            r'href="(/advisory/(ntap-[\w-]+))/?"',
            text, _re.IGNORECASE
        )
        for path, adv_id in matches:
            adv_id_clean = adv_id.lower()
            if adv_id_clean not in seen_ids:
                seen_ids.add(adv_id_clean)
                index_entries.append({
                    'id': adv_id_clean,
                    'link': f'https://security.netapp.com{path}'
                })
        time.sleep(0.3)  # be polite

    print(f'  [SCAN] Found {len(index_entries)} unique advisories on index pages', flush=True)

    # ── 2. Load existing DB ────────────────────────────────────────────────────
    if BULLETINS_PATH.exists():
        try:
            existing_data = json.loads(BULLETINS_PATH.read_text(encoding='utf-8'))
            bulletins = existing_data.get('bulletins', [])
        except Exception:
            bulletins = []
    else:
        bulletins = []

    id_to_idx = {b['id']: i for i, b in enumerate(bulletins) if b.get('id')}
    today = datetime.now(timezone.utc).isoformat()[:10]

    # ── 3. Fetch detail for each new advisory ──────────────────────────────────
    for entry in index_entries:
        adv_id = entry['id']
        is_new = adv_id not in id_to_idx
        if not is_new:
            continue  # already in DB, skip detail fetch

        print(f'  [SCAN] Fetching new advisory: {adv_id}', flush=True)
        try:
            detail = fetch_netapp_psirt(adv_id) or {}
            if detail.get('error'):
                errors += 1
                continue

            # ── Augment with NVD CVSS if CVEs are present ──────────────────────
            cvss_score = None
            severity = (detail.get('severity') or 'UNKNOWN').upper()
            cves = detail.get('cve', [])
            if cves:
                nvd_url = f'https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={cves[0]}'
                nvd_text, nvd_err = _enrich_fetch(nvd_url, timeout=15,
                    extra_headers={'apiKey': nvd_api_key} if nvd_api_key else None)
                if not nvd_err and nvd_text:
                    try:
                        nvd_data = json.loads(nvd_text)
                        vuln = nvd_data.get('vulnerabilities', [{}])[0].get('cve', {})
                        metrics = vuln.get('metrics', {})
                        for key in ('cvssMetricV31', 'cvssMetricV30', 'cvssMetricV2'):
                            if key in metrics and metrics[key]:
                                m = metrics[key][0].get('cvssData', {})
                                cvss_score = m.get('baseScore')
                                severity = (m.get('baseSeverity') or severity).upper()
                                break
                    except Exception:
                        pass
                time.sleep(0.2)

            # ── Build bulletin entry ────────────────────────────────────────────
            bulletin = {
                'id':               adv_id,
                'cve':              cves,
                'cvss':             cvss_score,
                'severity':         severity.lower() if severity != 'UNKNOWN' else 'medium',
                'category':         'PSIRT',
                'title':            detail.get('title', adv_id),
                'description':      detail.get('description', ''),
                'affectedProducts': _infer_affected_products(adv_id, detail.get('title', '')),
                'affectedVersions': {},
                'fixedVersions':    {},
                'mitigation':       'Refer to the NetApp advisory for mitigation guidance.',
                'published':        detail.get('published', today),
                'link':             entry['link'],
                '_addedAt':         today,
                '_source':          'scan'
            }

            bulletins.append(bulletin)
            id_to_idx[adv_id] = len(bulletins) - 1
            added += 1
            new_ids.append(adv_id)
            time.sleep(0.25)  # rate limit

        except Exception as ex:
            print(f'  [SCAN] Error processing {adv_id}: {ex}', flush=True)
            errors += 1

    # ── 4. Persist atomically ──────────────────────────────────────────────────
    if added > 0:
        out = {
            'version': 1,
            'lastUpdated': today,
            'lastScanned': today,
            'source': 'dynamic — authoritative store, updated by scan',
            'bulletinCount': len(bulletins),
            'bulletins': bulletins
        }
        payload = json.dumps(out, indent=2, ensure_ascii=False)
        tmp_path = BULLETINS_PATH.with_suffix('.tmp')
        bak_path = BULLETINS_PATH.with_suffix('.bak')
        tmp_path.write_text(payload, encoding='utf-8')
        if BULLETINS_PATH.exists():
            import shutil
            shutil.copy2(str(BULLETINS_PATH), str(bak_path))
        tmp_path.replace(BULLETINS_PATH)
        print(f'  [SCAN] Wrote {len(bulletins)} advisories to database (+{added} new)', flush=True)
    else:
        print(f'  [SCAN] No new advisories found (DB already has {len(bulletins)} entries)', flush=True)

    return {
        'added':   added,
        'updated': updated,
        'total':   len(bulletins),
        'scanned': len(index_entries),
        'errors':  errors,
        'newIds':  new_ids
    }

# ─────────────────────────────────────────────────────────────────────
# Enrichment Scanner — Scheduled Background Auto-Enrichment
# Scans 6 free public sources on a configurable interval:
#   1. CISA KEV (Known Exploited Vulnerabilities catalog)
#   2. NetApp PSIRT (security.netapp.com advisories)
#   3. NVD API 2.0 (NetApp CVEs with CVSS scores)
#   4. EPSS (Exploit Prediction Scoring System)
#   5. docs.netapp.com (version catalog + EOA platforms)
#   6. KB / Best Practices / Integration Docs
# ─────────────────────────────────────────────────────────────────────

class EnrichmentScheduler:
    """Background scheduler that periodically scans external sources for enrichment data."""

    # Files scanner 6 (KB crawl) reads/writes — kept separate from the main
    # bulletins.json/version_catalog.json group so its own staleness check
    # doesn't accidentally gate the fast scanners.
    _KB_STALENESS_FILE = KNOWLEDGE_PATH

    def __init__(self, interval_hours=12, nvd_api_key=None, kb_interval_hours=168):
        self._interval = max(1, interval_hours) * 3600
        # Scanner 6 (KB/doc crawl) is the long pole of the old 7-scanner cycle —
        # potentially 80-150+ sequential HTTP requests. Running it on the same
        # cadence as the fast security scanners means a closed desktop app can
        # lose an entire cycle's results for every scanner queued after it, and
        # forces the fast scanners to wait behind it needlessly. It now runs on
        # its own, much longer timer (default 7 days) — configurable separately.
        self._kb_interval = max(1, kb_interval_hours) * 3600
        self._nvd_api_key = nvd_api_key
        self._timer = None
        self._kb_timer = None
        self._running = False
        self._kb_running = False
        self._last_scan = None
        self._last_kb_scan = None
        self._last_results = {}
        self._last_kb_results = {}
        self._lock = threading.Lock()
        self._kb_lock = threading.Lock()

    def start(self):
        """Start both recurring timers. First scan of each after a short delay
        (staggered so they don't both hit the network in the same instant)."""
        self._timer = threading.Timer(60, self._do_scan)
        self._timer.daemon = True
        self._timer.start()
        self._kb_timer = threading.Timer(90, self._do_kb_scan)
        self._kb_timer.daemon = True
        self._kb_timer.start()
        print(f'  [ENRICH] Scheduler started (fast scanners: {self._interval // 3600}h, '
              f'KB crawl: {self._kb_interval // 3600}h)', flush=True)

    def stop(self):
        """Cancel pending timers."""
        if self._timer:
            self._timer.cancel()
            self._timer = None
        if self._kb_timer:
            self._kb_timer.cancel()
            self._kb_timer = None

    def update_config(self, interval_hours=None, nvd_api_key=None, kb_interval_hours=None):
        """Update scheduler configuration. Restarts the relevant timer if its interval changed."""
        if nvd_api_key is not None:
            self._nvd_api_key = nvd_api_key
        if interval_hours is not None:
            new_interval = max(1, interval_hours) * 3600
            if new_interval != self._interval:
                self._interval = new_interval
                if self._timer:
                    self._timer.cancel()
                self._schedule_next()
                print(f'  [ENRICH] Fast-scanner interval updated to {interval_hours}h', flush=True)
        if kb_interval_hours is not None:
            new_kb_interval = max(1, kb_interval_hours) * 3600
            if new_kb_interval != self._kb_interval:
                self._kb_interval = new_kb_interval
                if self._kb_timer:
                    self._kb_timer.cancel()
                self._schedule_next_kb()
                print(f'  [ENRICH] KB-crawl interval updated to {kb_interval_hours}h', flush=True)

    def run_now(self):
        """Manual trigger (from /api/enrich/scan POST) — runs the fast scanner group only."""
        if self._running:
            return {'status': 'already_running'}
        threading.Thread(target=self._do_scan, daemon=True, name='enrich-manual').start()
        return {'status': 'started'}

    def run_kb_now(self):
        """Manual trigger for the slow KB crawl specifically."""
        if self._kb_running:
            return {'status': 'already_running'}
        threading.Thread(target=self._do_kb_scan, daemon=True, name='enrich-kb-manual').start()
        return {'status': 'started'}

    def status(self):
        """Return current scheduler status for both timers."""
        return {
            'enabled': True,
            'intervalHours': self._interval // 3600,
            'lastScan': self._last_scan,
            'isRunning': self._running,
            'results': self._last_results,
            'hasNvdKey': bool(self._nvd_api_key),
            'kbIntervalHours': self._kb_interval // 3600,
            'lastKbScan': self._last_kb_scan,
            'isKbRunning': self._kb_running,
            'kbResults': self._last_kb_results,
        }

    def _schedule_next(self):
        self._timer = threading.Timer(self._interval, self._do_scan)
        self._timer.daemon = True
        self._timer.start()

    def _schedule_next_kb(self):
        self._kb_timer = threading.Timer(self._kb_interval, self._do_kb_scan)
        self._kb_timer.daemon = True
        self._kb_timer.start()

    @staticmethod
    def _file_age_hours(path):
        """Return hours since path's lastUpdated field (or mtime as fallback),
        or None if the file doesn't exist / can't be read."""
        try:
            if not path.exists():
                return None
            mtime = path.stat().st_mtime
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                last_updated = data.get('lastUpdated') or data.get('_lastUpdated')
                if last_updated:
                    parsed = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    return (datetime.now(timezone.utc) - parsed).total_seconds() / 3600
            except Exception:
                pass
            return (time.time() - mtime) / 3600
        except Exception:
            return None

    def _do_scan(self):
        """Run the fast scanner group (1-4). Each scanner is skipped if its
        target file was already refreshed more recently than the configured
        interval — avoids redundant re-scanning when the desktop app is
        opened/closed frequently within a single interval window.
        Scanner 5 (version catalog, writes only version_catalog.json) runs
        concurrently with the bulletins.json-writing group (1,2,3,4) since
        they touch disjoint files. Scanner 7 (reference library) turned out to
        be its own multi-minute crawl (docs.netapp.com/GitHub/PyPI harvesting
        inside reference_harvester.py) — moved to run alongside scanner 6 on
        the long KB-crawl timer instead of blocking this fast group.
        Each bulletin-touching scanner call is wrapped in _bulletins_lock so
        it can't race with scanner 7 running concurrently on the other timer."""
        with self._lock:
            if self._running:
                return
            self._running = True

        scan_start = time.time()
        print(f'  [ENRICH] ══════════════════════════════════════════════════════', flush=True)
        print(f'  [ENRICH] Starting scheduled enrichment scan (fast group)...', flush=True)
        results = {}
        try:
            interval_h = self._interval / 3600

            def _bulletins_group():
                out = {}
                age = self._file_age_hours(BULLETINS_PATH)
                if age is not None and age < interval_h:
                    print(f'  [ENRICH] [1-4] security_bulletins.json is {age:.1f}h old '
                          f'(< {interval_h:.0f}h interval) — skipping bulletin scanners', flush=True)
                    out['cisa_kev'] = {'skipped': 'fresh'}
                    out['netapp_psirt'] = {'skipped': 'fresh'}
                    out['nvd_netapp'] = {'skipped': 'fresh'}
                    out['epss'] = {'skipped': 'fresh'}
                    return out
                with _bulletins_lock:
                    out['cisa_kev'] = self._scan_cisa_kev()
                    out['netapp_psirt'] = self._scan_netapp_psirt()
                    out['nvd_netapp'] = self._scan_nvd_netapp()
                    out['epss'] = self._scan_epss()
                return out

            def _version_catalog_group():
                age = self._file_age_hours(VERSION_CATALOG_PATH)
                if age is not None and age < interval_h:
                    print(f'  [ENRICH] [5] version_catalog.json is {age:.1f}h old '
                          f'(< {interval_h:.0f}h interval) — skipping', flush=True)
                    return {'skipped': 'fresh'}
                return self._scan_version_catalog()

            with ThreadPoolExecutor(max_workers=2, thread_name_prefix='enrich-fast') as pool:
                fut_bulletins = pool.submit(_bulletins_group)
                fut_version = pool.submit(_version_catalog_group)
                bulletins_results = fut_bulletins.result()
                results['version_catalog'] = fut_version.result()
            results.update(bulletins_results)

            elapsed = round(time.time() - scan_start, 1)
            results['_elapsed'] = elapsed
            self._last_scan = datetime.now(timezone.utc).isoformat()[:19] + 'Z'
            self._last_results = results
            print(f'  [ENRICH] Fast scan complete in {elapsed}s', flush=True)
            print(f'  [ENRICH] ══════════════════════════════════════════════════════', flush=True)
        except Exception as e:
            import traceback
            traceback.print_exc()
            results['_error'] = str(e)
            self._last_results = results
            print(f'  [ENRICH] Fast scan failed: {e}', flush=True)
        finally:
            self._running = False
            self._schedule_next()
            # Every fast-scan completion also checks whether the slow-crawl
            # group (platform/switch/firmware/drive/card/new-hardware data —
            # scanners 6-8) has gone stale, instead of that only ever being
            # driven by its own independent 7-day timer. _do_kb_scan's own
            # per-sub-scanner staleness checks make this cheap to call often —
            # it no-ops in milliseconds when nothing is actually due.
            if not self._kb_running:
                threading.Thread(target=self._do_kb_scan, daemon=True, name='enrich-kb-after-fast').start()

    def _do_kb_scan(self):
        """Run the two slow, long-running crawls (scanner 6: KB/doc crawl, and
        scanner 7: reference library — EOA/IMT/firmware, also touches
        security_bulletins.json) on their own long interval, independent of
        the fast scanner group above. Each is independently skipped if its
        own target file is already fresher than the configured interval.
        Scanner 7's bulletins.json access is wrapped in _bulletins_lock since
        the fast group can run concurrently on its own (much shorter) timer."""
        with self._kb_lock:
            if self._kb_running:
                return
            self._kb_running = True

        scan_start = time.time()
        results = {}
        try:
            interval_h = self._kb_interval / 3600

            kb_age = self._file_age_hours(self._KB_STALENESS_FILE)
            if kb_age is not None and kb_age < interval_h:
                print(f'  [ENRICH] [KB] knowledge_base.json is {kb_age:.1f}h old '
                      f'(< {interval_h:.0f}h interval) — skipping crawl', flush=True)
                results['knowledge_base'] = {'skipped': 'fresh'}
            else:
                print('  [ENRICH] Starting knowledge-base crawl (long-running)...', flush=True)
                results['knowledge_base'] = self._scan_knowledge_base()

            ref_age = self._file_age_hours(BULLETINS_PATH)
            if ref_age is not None and ref_age < interval_h:
                print(f'  [ENRICH] [7] security_bulletins.json is {ref_age:.1f}h old '
                      f'(< {interval_h:.0f}h interval) — skipping reference library scan', flush=True)
                results['reference_library'] = {'skipped': 'fresh'}
            else:
                print('  [ENRICH] Starting reference library scan (long-running)...', flush=True)
                with _bulletins_lock:
                    results['reference_library'] = self._scan_reference_library()

            discovery_age = self._file_age_hours(DISCOVERED_PRODUCTS_PATH)
            if discovery_age is not None and discovery_age < interval_h:
                print(f'  [ENRICH] [8] discovered_products.json is {discovery_age:.1f}h old '
                      f'(< {interval_h:.0f}h interval) — skipping sitemap discovery', flush=True)
                results['sitemap_discovery'] = {'skipped': 'fresh'}
            else:
                results['sitemap_discovery'] = self._scan_sitemap_discovery()

            elapsed = round(time.time() - scan_start, 1)
            results['_elapsed'] = elapsed
            self._last_kb_results = results
            print(f'  [ENRICH] Slow-crawl cycle complete in {elapsed}s', flush=True)
            self._last_kb_scan = datetime.now(timezone.utc).isoformat()[:19] + 'Z'
        except Exception as e:
            import traceback
            traceback.print_exc()
            results['_error'] = str(e)
            self._last_kb_results = results
            print(f'  [ENRICH] Slow-crawl cycle failed: {e}', flush=True)
        finally:
            self._kb_running = False
            self._schedule_next_kb()

    # ── Scanner 8: Sitemap-Based Product/Integration Auto-Discovery ──────────
    def _scan_sitemap_discovery(self):
        """Intelligent extensibility: automatically discover NEW NetApp products,
        integrations, and documentation sections as NetApp adds them — rather
        than relying solely on the hardcoded seed URL lists in _scan_knowledge_base
        and reference_harvester.py, which only cover what was known at the time
        this tool was written.

        Uses docs.netapp.com/sitemap.xml — a real, sanctioned sitemap index
        (confirmed present in robots.txt, not disallowed for crawling) that
        enumerates every top-level product/documentation section NetApp
        publishes. Each run:
          1. Fetches the sitemap index, extracts en-US top-level section slugs
             (skips other locales per robots.txt guidance).
          2. Diffs against the persisted set of previously-seen slugs.
          3. For any genuinely NEW section (bounded to 10 per run to stay
             polite and keep each cycle fast), fetches that section's own
             sitemap and adds a sample of its pages to knowledge_base.json,
             tagged with source 'sitemap-discovery' and the new section name
             as category — so a newly-acquired product (e.g. NetApp's real
             August 2026 JetStream Software acquisition) gets picked up
             automatically on the next scheduled run once NetApp publishes
             its docs, with zero code changes required here.
        """
        print('  [ENRICH] [8] Sitemap-based product/integration discovery...', flush=True)
        try:
            text, err = _enrich_fetch('https://docs.netapp.com/sitemap.xml', timeout=20)
            if err or not text:
                print(f'  [ENRICH]   Sitemap discovery: index fetch failed: {err}', flush=True)
                return {'error': str(err), 'newSections': 0}

            # Extract en-US top-level section sitemap URLs, e.g.
            # https://docs.netapp.com/us-en/<slug>/sitemap.xml
            section_urls = sorted(set(_re.findall(
                r'https://docs\.netapp\.com/us-en/([a-z0-9][a-z0-9_-]*)/sitemap\.xml', text)))
            print(f'  [ENRICH]   Sitemap index: {len(section_urls)} us-en product sections found', flush=True)

            # Load previously-seen sections
            if DISCOVERED_PRODUCTS_PATH.exists():
                try:
                    known = json.loads(DISCOVERED_PRODUCTS_PATH.read_text(encoding='utf-8'))
                    known_slugs = set(known.get('knownSlugs', []))
                except Exception:
                    known_slugs = set()
            else:
                known_slugs = set()

            new_slugs = [s for s in section_urls if s not in known_slugs]
            print(f'  [ENRICH]   {len(new_slugs)} newly-discovered section(s) since last run', flush=True)

            # Bound how many new sections we deep-crawl per run — stay polite,
            # keep each enrichment cycle fast. Remaining new slugs are still
            # marked "known" (so we don't refetch the index-match every run)
            # but their content isn't crawled until a future run if the cap
            # is hit — logged, not silently dropped, per the "no silent caps"
            # principle.
            MAX_NEW_PER_RUN = 10
            to_crawl = new_slugs[:MAX_NEW_PER_RUN]
            if len(new_slugs) > MAX_NEW_PER_RUN:
                print(f'  [ENRICH]   Capping deep-crawl to {MAX_NEW_PER_RUN} of {len(new_slugs)} new sections this run '
                      f'(remaining {len(new_slugs) - MAX_NEW_PER_RUN} will be crawled in a future cycle)', flush=True)

            new_articles = []
            if KNOWLEDGE_PATH.exists():
                try:
                    kb_data = json.loads(KNOWLEDGE_PATH.read_text(encoding='utf-8'))
                except Exception:
                    kb_data = {'version': 1, 'articles': []}
            else:
                kb_data = {'version': 1, 'articles': []}
            existing_urls = {a.get('url') for a in kb_data.get('articles', [])}

            for slug in to_crawl:
                try:
                    sec_url = f'https://docs.netapp.com/us-en/{slug}/sitemap.xml'
                    sec_text, sec_err = _enrich_fetch(sec_url, timeout=15)
                    if sec_err or not sec_text:
                        continue
                    page_urls = _re.findall(r'<loc>(https://docs\.netapp\.com/us-en/[^<]+)</loc>', sec_text)
                    # Sample the first 15 pages of a newly-discovered section —
                    # enough to seed useful KB coverage without over-fetching an
                    # entire product's doc tree in one enrichment cycle.
                    for page_url in page_urls[:15]:
                        if page_url in existing_urls:
                            continue
                        title = page_url.rstrip('/').split('/')[-1].replace('-', ' ').replace('.html', '').title() or slug.replace('-', ' ').title()
                        new_articles.append({
                            'url': page_url,
                            'title': title,
                            'source': 'sitemap-discovery',
                            'category': slug,
                            'discoveredAt': datetime.now(timezone.utc).isoformat()[:10],
                        })
                        existing_urls.add(page_url)
                    print(f'  [ENRICH]     New section "{slug}": +{min(len(page_urls), 15)} pages seeded', flush=True)
                    time.sleep(0.5)  # be polite between section sitemap fetches
                except Exception as sec_ex:
                    print(f'  [ENRICH]     Section "{slug}" crawl failed: {sec_ex}', flush=True)

            if new_articles:
                kb_data['articles'] = kb_data.get('articles', []) + new_articles
                kb_data['lastUpdated'] = datetime.now(timezone.utc).isoformat()[:10]
                payload = json.dumps(kb_data, indent=2, ensure_ascii=False)
                tmp_path = KNOWLEDGE_PATH.with_suffix('.tmp')
                tmp_path.write_text(payload, encoding='utf-8')
                tmp_path.replace(KNOWLEDGE_PATH)

            # Persist ALL section slugs seen (not just the crawled ones) so next
            # run's diff is accurate even for sections we didn't have budget to
            # deep-crawl this time.
            DISCOVERED_PRODUCTS_PATH.parent.mkdir(parents=True, exist_ok=True)
            all_known = sorted(set(section_urls) | known_slugs)
            DISCOVERED_PRODUCTS_PATH.write_text(json.dumps({
                'lastUpdated': datetime.now(timezone.utc).isoformat()[:10],
                'knownSlugs': all_known,
                'lastNewSlugs': new_slugs,
            }, indent=2), encoding='utf-8')

            print(f'  [ENRICH]   Sitemap discovery: {len(new_articles)} new KB article(s) from {len(to_crawl)} newly-discovered section(s)', flush=True)
            return {'totalSections': len(section_urls), 'newSections': len(new_slugs), 'crawledSections': to_crawl, 'newArticles': len(new_articles)}
        except Exception as e:
            print(f'  [ENRICH]   Sitemap discovery failed: {e}', flush=True)
            return {'error': str(e)}

    # ── Scanner 1: CISA KEV ──────────────────────────────────────────
    def _scan_cisa_kev(self):
        """Download CISA Known Exploited Vulnerabilities catalog and cross-reference."""
        print('  [ENRICH] [1/7] Scanning CISA KEV catalog...', flush=True)
        url = 'https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json'
        text, err = _enrich_fetch(url, timeout=30)
        if err or not text:
            print(f'  [ENRICH]   CISA KEV fetch failed: {err}', flush=True)
            return {'error': str(err), 'matched': 0}

        try:
            kev_data = json.loads(text)
            kev_cves = {v.get('cveID'): v for v in kev_data.get('vulnerabilities', [])}
            print(f'  [ENRICH]   CISA KEV catalog: {len(kev_cves)} entries', flush=True)

            # Cross-reference with existing bulletins
            matched = 0
            updated_bulletins = False
            if BULLETINS_PATH.exists():
                bdata = json.loads(BULLETINS_PATH.read_text(encoding='utf-8'))
                bulletins = bdata.get('bulletins', [])
                for b in bulletins:
                    for cve_id in (b.get('cve') or []):
                        if cve_id in kev_cves:
                            kev_entry = kev_cves[cve_id]
                            if not b.get('cisaKev'):
                                b['cisaKev'] = True
                                b['cisaKevDateAdded'] = kev_entry.get('dateAdded', '')
                                b['cisaKevDueDate'] = kev_entry.get('dueDate', '')
                                b['cisaKevAction'] = kev_entry.get('requiredAction', '')
                                updated_bulletins = True
                            matched += 1
                if updated_bulletins:
                    bdata['lastUpdated'] = datetime.now(timezone.utc).isoformat()[:10]
                    payload = json.dumps(bdata, indent=2, ensure_ascii=False)
                    tmp_path = BULLETINS_PATH.with_suffix('.tmp')
                    bak_path = BULLETINS_PATH.with_suffix('.bak')
                    tmp_path.write_text(payload, encoding='utf-8')
                    if BULLETINS_PATH.exists():
                        import shutil
                        shutil.copy2(str(BULLETINS_PATH), str(bak_path))
                    tmp_path.replace(BULLETINS_PATH)
                    print(f'  [ENRICH]   Updated bulletins with {matched} KEV cross-references', flush=True)

            # Save full KEV catalog for local reference and offline access
            kev_out = {
                'version': 1,
                'lastUpdated': datetime.now(timezone.utc).isoformat()[:10],
                'catalogVersion': kev_data.get('catalogVersion', ''),
                'totalKevEntries': len(kev_cves),
                'matchedToFleet': matched,
                'vulnerabilities': [{k: v for k, v in entry.items()
                                     if k in ('cveID', 'vendorProject', 'product',
                                              'dateAdded', 'dueDate', 'requiredAction',
                                              'knownRansomwareCampaignUse')}
                                    for entry in kev_cves.values()],
            }
            KEV_PATH.parent.mkdir(parents=True, exist_ok=True)
            KEV_PATH.write_text(json.dumps(kev_out, indent=2), encoding='utf-8')
            print(f'  [ENRICH]   CISA KEV: {matched} matched to fleet advisories', flush=True)
            return {'total': len(kev_cves), 'matched': matched}
        except Exception as e:
            print(f'  [ENRICH]   CISA KEV parse error: {e}', flush=True)
            return {'error': str(e), 'matched': 0}

    # ── Scanner 2: NetApp PSIRT ──────────────────────────────────────
    def _scan_netapp_psirt(self):
        """Run the existing NetApp PSIRT advisory scanner."""
        print('  [ENRICH] [2/7] Scanning NetApp PSIRT advisories...', flush=True)
        try:
            result = scan_and_persist_advisories(nvd_api_key=self._nvd_api_key)
            print(f'  [ENRICH]   PSIRT: +{result.get("added", 0)} new, {result.get("total", 0)} total', flush=True)
            return result
        except Exception as e:
            print(f'  [ENRICH]   PSIRT scan failed: {e}', flush=True)
            return {'error': str(e), 'added': 0}

    # ── Scanner 3: NVD API (NetApp CVEs) ─────────────────────────────
    def _scan_nvd_netapp(self):
        """Query NVD API 2.0 for new NetApp-related CVEs."""
        print('  [ENRICH] [3/7] Scanning NVD for NetApp CVEs...', flush=True)
        base_url = 'https://services.nvd.nist.gov/rest/json/cves/2.0'

        # Get CVEs published in the last 30 days for NetApp
        from_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime('%Y-%m-%dT00:00:00.000')
        to_date = datetime.now(timezone.utc).strftime('%Y-%m-%dT23:59:59.999')
        url = f'{base_url}?keywordSearch=netapp&pubStartDate={from_date}&pubEndDate={to_date}'

        # NVD API 2.0 only accepts apiKey as an HTTP header — passing it as a
        # query string parameter silently 404s regardless of whether the key
        # is valid, which was previously breaking every scan when a key was
        # configured (silently falling back to no results, not to the slower
        # unauthenticated tier).
        extra_headers = {'apiKey': self._nvd_api_key} if self._nvd_api_key else None
        text, err = _enrich_fetch(url, timeout=30, extra_headers=extra_headers)
        if err or not text:
            print(f'  [ENRICH]   NVD fetch failed: {err}', flush=True)
            return {'error': str(err), 'new': 0}

        try:
            nvd_data = json.loads(text)
            cves = nvd_data.get('vulnerabilities', [])
            print(f'  [ENRICH]   NVD returned {len(cves)} CVEs (last 30 days)', flush=True)

            # Load existing bulletin IDs for dedup
            existing_cves = set()
            if BULLETINS_PATH.exists():
                bdata = json.loads(BULLETINS_PATH.read_text(encoding='utf-8'))
                for b in bdata.get('bulletins', []):
                    for c in (b.get('cve') or []):
                        existing_cves.add(c)

            new_cves = []
            for vuln in cves:
                cve_item = vuln.get('cve', {})
                cve_id = cve_item.get('id', '')
                if cve_id in existing_cves:
                    continue

                # Extract CVSS score
                metrics = cve_item.get('metrics', {})
                cvss_score = 0.0
                severity = 'medium'
                for metric_key in ['cvssMetricV31', 'cvssMetricV30', 'cvssMetricV2']:
                    metric_list = metrics.get(metric_key, [])
                    if metric_list:
                        cvss_data = metric_list[0].get('cvssData', {})
                        cvss_score = cvss_data.get('baseScore', 0.0)
                        severity = cvss_data.get('baseSeverity', 'MEDIUM').lower()
                        break

                # Extract description
                descriptions = cve_item.get('descriptions', [])
                desc = ''
                for d in descriptions:
                    if d.get('lang') == 'en':
                        desc = d.get('value', '')
                        break

                # Only include if it seems NetApp-related based on description
                desc_lower = desc.lower()
                if not any(kw in desc_lower for kw in ['netapp', 'ontap', 'storagegrid', 'snapcenter', 'trident', 'active iq', 'santricity']):
                    continue

                new_cves.append({
                    'id': f'NVD-{cve_id}',
                    'cve': [cve_id],
                    'cvss': cvss_score,
                    'severity': severity,
                    'title': f'{cve_id}: {desc[:120]}...' if len(desc) > 120 else f'{cve_id}: {desc}',
                    'description': desc,
                    'affectedProducts': _infer_affected_products(cve_id, desc),
                    'mitigation': 'Review NVD advisory and apply vendor patches.',
                    'published': cve_item.get('published', '')[:10],
                    'link': f'https://nvd.nist.gov/vuln/detail/{cve_id}',
                    '_source': 'nvd_auto_scan',
                    '_addedAt': datetime.now(timezone.utc).isoformat()[:10],
                })

            if new_cves:
                # POST to existing bulletin pipeline
                if BULLETINS_PATH.exists():
                    bdata = json.loads(BULLETINS_PATH.read_text(encoding='utf-8'))
                    bulletins = bdata.get('bulletins', [])
                else:
                    bulletins = []
                    bdata = {'version': 1, 'source': 'dynamic', 'bulletins': []}

                id_set = {b.get('id') for b in bulletins}
                added = 0
                for entry in new_cves:
                    if entry['id'] not in id_set:
                        bulletins.append(entry)
                        id_set.add(entry['id'])
                        added += 1

                if added > 0:
                    bdata['lastUpdated'] = datetime.now(timezone.utc).isoformat()[:10]
                    bdata['bulletinCount'] = len(bulletins)
                    bdata['bulletins'] = bulletins
                    payload = json.dumps(bdata, indent=2, ensure_ascii=False)
                    tmp_path = BULLETINS_PATH.with_suffix('.tmp')
                    bak_path = BULLETINS_PATH.with_suffix('.bak')
                    tmp_path.write_text(payload, encoding='utf-8')
                    if BULLETINS_PATH.exists():
                        import shutil
                        shutil.copy2(str(BULLETINS_PATH), str(bak_path))
                    tmp_path.replace(BULLETINS_PATH)
                    print(f'  [ENRICH]   NVD: Added {added} new CVEs to bulletin DB', flush=True)

            print(f'  [ENRICH]   NVD: {len(new_cves)} new NetApp CVEs found', flush=True)
            return {'scanned': len(cves), 'new': len(new_cves)}
        except Exception as e:
            print(f'  [ENRICH]   NVD parse error: {e}', flush=True)
            return {'error': str(e), 'new': 0}

    # ── Scanner 4: EPSS Scores ───────────────────────────────────────
    def _scan_epss(self):
        """Enrich existing CVEs with EPSS exploit prediction scores."""
        print('  [ENRICH] [4/7] Enriching CVEs with EPSS scores...', flush=True)
        if not BULLETINS_PATH.exists():
            return {'enriched': 0}

        try:
            bdata = json.loads(BULLETINS_PATH.read_text(encoding='utf-8'))
            bulletins = bdata.get('bulletins', [])

            # Collect all CVE IDs that don't yet have EPSS scores
            cves_needing_epss = []
            for b in bulletins:
                if b.get('epssScore') is not None:
                    continue
                for cve_id in (b.get('cve') or []):
                    if cve_id.startswith('CVE-'):
                        cves_needing_epss.append((cve_id, b))

            if not cves_needing_epss:
                print('  [ENRICH]   EPSS: All CVEs already have scores', flush=True)
                return {'enriched': 0, 'total': len(bulletins)}

            # Batch query EPSS (up to 100 CVEs per request)
            enriched = 0
            batch_size = 30
            for i in range(0, len(cves_needing_epss), batch_size):
                batch = cves_needing_epss[i:i + batch_size]
                cve_ids = ','.join(c[0] for c in batch)
                url = f'https://api.first.org/data/v1/epss?cve={cve_ids}'
                text, err = _enrich_fetch(url, timeout=15)
                if err or not text:
                    continue

                try:
                    epss_data = json.loads(text)
                    epss_map = {d['cve']: d for d in epss_data.get('data', [])}
                    for cve_id, bulletin in batch:
                        if cve_id in epss_map:
                            bulletin['epssScore'] = float(epss_map[cve_id].get('epss', 0))
                            bulletin['epssPercentile'] = float(epss_map[cve_id].get('percentile', 0))
                            enriched += 1
                except Exception:
                    pass

                # Rate limiting: small pause between batches
                time.sleep(1)

            if enriched > 0:
                bdata['lastUpdated'] = datetime.now(timezone.utc).isoformat()[:10]
                payload = json.dumps(bdata, indent=2, ensure_ascii=False)
                tmp_path = BULLETINS_PATH.with_suffix('.tmp')
                bak_path = BULLETINS_PATH.with_suffix('.bak')
                tmp_path.write_text(payload, encoding='utf-8')
                if BULLETINS_PATH.exists():
                    import shutil
                    shutil.copy2(str(BULLETINS_PATH), str(bak_path))
                tmp_path.replace(BULLETINS_PATH)

            print(f'  [ENRICH]   EPSS: Enriched {enriched}/{len(cves_needing_epss)} CVEs', flush=True)
            return {'enriched': enriched, 'total': len(bulletins)}
        except Exception as e:
            print(f'  [ENRICH]   EPSS error: {e}', flush=True)
            return {'error': str(e), 'enriched': 0}

    # ── Scanner 5: Version Catalog + EOA ─────────────────────────────
    def _scan_version_catalog(self):
        """Refresh ONTAP/StorageGRID/SANtricity version catalog from docs.netapp.com."""
        print('  [ENRICH] [5/7] Refreshing version catalog from docs.netapp.com...', flush=True)
        try:
            catalog = fetch_latest_version_catalog()
            total = sum(len(v) for v in catalog.values() if isinstance(v, list))
            # Persist version catalog to local file
            catalog['_lastUpdated'] = datetime.now(timezone.utc).isoformat()[:10]
            VERSION_CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = VERSION_CATALOG_PATH.with_suffix('.tmp')
            tmp_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding='utf-8')
            tmp_path.replace(VERSION_CATALOG_PATH)
            print(f'  [ENRICH]   Version catalog: {total} versions across {len(catalog)} products', flush=True)
            return {'products': list(catalog.keys()), 'totalVersions': total}
        except Exception as e:
            print(f'  [ENRICH]   Version catalog error: {e}', flush=True)
            return {'error': str(e)}

    # ── Scanner 6: KB / Best Practices / Integration Docs ────────────
    def _scan_knowledge_base(self):
        """Scan NetApp KB, docs.netapp.com, and integration sources for new articles."""
        print('  [ENRICH] [6/7] Scanning knowledge base sources...', flush=True)

        # Load existing knowledge base
        if KNOWLEDGE_PATH.exists():
            try:
                kb_data = json.loads(KNOWLEDGE_PATH.read_text(encoding='utf-8'))
            except Exception:
                kb_data = {'version': 1, 'articles': []}
        else:
            kb_data = {'version': 1, 'articles': []}

        existing_urls = {a.get('url') for a in kb_data.get('articles', [])}
        new_articles = []

        # ── 6a. NetApp KB articles (best practices, troubleshooting) ──
        import json as _json_mod

        def _fetch_kb_jsonld(url):
            found_urls = []
            try:
                text, err = _enrich_fetch(url, timeout=15)
                if err or not text:
                    return found_urls
                ld_blocks = _re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', text, _re.DOTALL)
                for block in ld_blocks:
                    try:
                        data = _json_mod.loads(block)
                        if 'mainEntity' in data:
                            for item in data['mainEntity'].get('itemListElement', []):
                                name = item.get('name', '')
                                iurl = item.get('url', '')
                                if iurl:
                                    found_urls.append((iurl, name))
                    except: pass
                time.sleep(1)
            except: pass
            return found_urls

        kb_root_urls = _fetch_kb_jsonld('https://kb.netapp.com/')
        kb_level1 = []
        for curl, cname in kb_root_urls:
            kb_level1.extend(_fetch_kb_jsonld(curl))
            
        ontap_urls = [u for u in kb_level1 if 'ontap' in u[0].lower()]
        kb_level2 = []
        for curl, cname in ontap_urls:
            kb_level2.extend(_fetch_kb_jsonld(curl))

        for curl, cname in kb_root_urls + kb_level1 + kb_level2:
            if curl not in existing_urls:
                cat = 'knowledge_base'
                lower_url = curl.lower()
                if 'troubleshoot' in lower_url: cat = 'troubleshooting'
                elif 'best-practice' in lower_url: cat = 'best_practices'
                elif 'security' in lower_url: cat = 'security'
                
                new_articles.append({
                    'url': curl,
                    'title': html.unescape(cname).strip() if cname else curl.split('/')[-1].replace('-', ' ').title(),
                    'source': 'kb.netapp.com',
                    'category': cat,
                    'discoveredAt': datetime.now(timezone.utc).isoformat()[:10],
                })
                existing_urls.add(curl)

        # ── 6b. Technical Reports (TRs) from docs.netapp.com ──
        docs_indexes = [
            'https://docs.netapp.com/us-en/ontap/',
            'https://docs.netapp.com/us-en/ontap-systems/',
            'https://docs.netapp.com/us-en/ontap/nas-management/index.html',
            'https://docs.netapp.com/us-en/ontap/san-management/index.html',
            'https://docs.netapp.com/us-en/ontap/upgrade/index.html',
        ]
        for url in docs_indexes:
            try:
                text, err = _enrich_fetch(url, timeout=15)
                if not err and text:
                    links = _re.findall(r'href="([^"]+)"[^>]*>([^<]{5,})</a>', text)
                    for href, title in links:
                        if href.startswith('http') and not href.startswith('https://docs.netapp.com/'):
                            continue
                        if href.startswith('#') or href.startswith('javascript:'):
                            continue
                        full_url = href if href.startswith('http') else urllib.parse.urljoin(url, href)
                        if full_url in existing_urls:
                            continue
                        title_clean = html.unescape(title).strip()
                        lower_url = full_url.lower()
                        cat = 'reference'
                        if '/security/' in lower_url: cat = 'security'
                        elif '/upgrade/' in lower_url: cat = 'upgrade'
                        elif '/performance/' in lower_url: cat = 'performance'
                        elif '/san' in lower_url: cat = 'operations'
                        elif '/nas' in lower_url: cat = 'operations'
                        elif '/fabricpool/' in lower_url: cat = 'configuration'
                        
                        new_articles.append({
                            'url': full_url,
                            'title': title_clean,
                            'source': 'docs.netapp.com',
                            'category': cat,
                            'discoveredAt': datetime.now(timezone.utc).isoformat()[:10],
                        })
                        existing_urls.add(full_url)
                time.sleep(2)
            except Exception:
                pass

        # ── 6c. 3rd-party integration docs — DYNAMIC DISCOVERY ──
        integration_seeds = [
            ('https://docs.netapp.com/us-en/ontap/release-notes/index.html', 'reference', 'Release Notes'),
            ('https://docs.netapp.com/us-en/ontap/quick-start.html', 'reference', 'Quick Start'),
            ('https://docs.netapp.com/us-en/ontap/software_setup/workflow-summary.html', 'reference', 'Software Setup Workflow'),
            ('https://docs.netapp.com/us-en/ontap-cli/index.html', 'automation', 'ONTAP CLI Reference'),
            ('https://docs.netapp.com/us-en/ontap/setup-upgrade/index.html', 'upgrade', 'Setup and Upgrade'),
            ('https://docs.netapp.com/us-en/ontap/disks-aggregates/index.html', 'operations', 'Disks and Aggregates Management'),
            ('https://docs.netapp.com/us-en/ontap/fabricpool/index.html', 'configuration', 'FabricPool Configuration'),
            ('https://docs.netapp.com/us-en/ontap/flexgroup/index.html', 'operations', 'FlexGroup Volumes'),
            ('https://docs.netapp.com/us-en/ontap/flexcache/index.html', 'operations', 'FlexCache Volumes'),
            ('https://docs.netapp.com/us-en/ontap/nfs-config/index.html', 'configuration', 'NFS Configuration'),
            ('https://docs.netapp.com/us-en/ontap/nfs-admin/index.html', 'operations', 'NFS Administration'),
            ('https://docs.netapp.com/us-en/ontap/smb-config/index.html', 'configuration', 'SMB Configuration'),
            ('https://docs.netapp.com/us-en/ontap/smb-admin/index.html', 'operations', 'SMB Administration'),
            ('https://docs.netapp.com/us-en/ontap/smb-hyper-v-sql/index.html', 'integration', 'SMB for Hyper-V and SQL Server'),
            ('https://docs.netapp.com/us-en/ontap/san-admin/index.html', 'operations', 'SAN Administration'),
            ('https://docs.netapp.com/us-en/ontap/san-config/index.html', 'configuration', 'SAN Configuration'),
            ('https://docs.netapp.com/us-en/ontap-sanhost/', 'integration', 'SAN Host Utilities'),
            ('https://docs.netapp.com/us-en/ontap/s3-config/workflow-concept.html', 'configuration', 'S3 Configuration Workflow'),
            ('https://docs.netapp.com/us-en/ontap/s3-snapmirror/index.html', 'data_protection', 'S3 SnapMirror'),
            ('https://docs.netapp.com/us-en/ontap/authentication/workflow-concept.html', 'security', 'Authentication and RBAC Workflow'),
            ('https://docs.netapp.com/us-en/ontap/multi-admin-verify/index.html', 'security', 'Multi-Admin Verification'),
            ('https://docs.netapp.com/us-en/ontap/authentication/overview-oauth2.html', 'security', 'OAuth2 Authentication'),
            ('https://docs.netapp.com/us-en/ontap/nas-audit/index.html', 'security', 'NAS Auditing'),
            ('https://docs.netapp.com/us-en/ontap/antivirus/index.html', 'security', 'Antivirus Configuration'),
            ('https://docs.netapp.com/us-en/ontap/snaplock/index.html', 'compliance', 'SnapLock Compliance'),
            ('https://docs.netapp.com/us-en/ontap/snapmirror-active-sync/index.html', 'data_protection', 'SnapMirror Active Sync'),
            ('https://docs.netapp.com/us-en/ontap/tape-backup/index.html', 'integration', 'Tape Backup Integration'),
            ('https://docs.netapp.com/us-en/ontap/ndmp/index.html', 'integration', 'NDMP Backup Integration'),
            ('https://docs.netapp.com/us-en/ontap/performance-config/index.html', 'performance', 'Performance Configuration'),
            ('https://docs.netapp.com/us-en/ontap/performance-admin/index.html', 'performance', 'Performance Administration'),
            ('https://docs.netapp.com/us-en/ontap/concept_nas_file_system_analytics_overview.html', 'performance', 'File System Analytics'),
            ('https://docs.netapp.com/us-en/ontap/error-messages/index.html', 'troubleshooting', 'EMS Error Messages'),
            ('https://docs.netapp.com/us-en/ai-data-engine/index.html', 'integration', 'AI Data Engine'),
            ('https://docs.netapp.com/us-en/ontap-technical-reports/ransomware-solutions/ransomware-overview.html', 'security', 'Ransomware Solutions Overview'),
            ('https://docs.netapp.com/us-en/ontap-7mode-transition/index.html', 'migration', '7-Mode to ONTAP Transition'),
            ('https://docs.netapp.com/us-en/ontap-fli/', 'migration', 'Foreign LUN Import'),
            ('https://docs.netapp.com/us-en/ontap-select/', 'integration', 'ONTAP Select'),
            
            # VMware Integration
            ('https://docs.netapp.com/us-en/ontap-tools-vmware-vsphere-10/index.html', 'integration', 'ONTAP tools for VMware vSphere'),
            ('https://docs.netapp.com/us-en/sc-plugin-vmware-vsphere/index.html', 'integration', 'SnapCenter Plug-in for VMware'),
            ('https://docs.netapp.com/us-en/ontap-apps-dbs/vmware/vmware-vsphere-overview.html', 'integration', 'ONTAP for VMware vSphere Administrators'),
            ('https://docs.netapp.com/us-en/ontap-apps-dbs/vmware/vmware-otv-hardening-overview.html', 'best_practices', 'VMware vSphere with ONTAP Best Practices'),
            ('https://docs.netapp.com/us-en/ontap-apps-dbs/vmware/vmware-srm-overview.html', 'integration', 'VMware SRM with ONTAP'),
            ('https://docs.netapp.com/us-en/ontap-apps-dbs/vmware/vmware-vvols-overview.html', 'integration', 'VMware vVols with ONTAP'),
            ('https://docs.netapp.com/us-en/netapp-solutions-cloud/vmware/vmw-azure-avs-dr-jetstream.html', 'data_protection', 'JetStream DR for VMware on Azure NetApp Files (NetApp acquisition, Aug 2026)'),

            # Kubernetes/Containers
            ('https://docs.netapp.com/us-en/trident/index.html', 'integration', 'Astra Trident (Kubernetes CSI)'),
            ('https://docs.netapp.com/us-en/astra-control-center/index.html', 'integration', 'Astra Control Center'),

            # Database Integration
            ('https://docs.netapp.com/us-en/ontap-apps-dbs/oracle/oracle-overview.html', 'integration', 'Oracle on ONTAP'),
            ('https://docs.netapp.com/us-en/ontap-apps-dbs/mssql/mssql-overview.html', 'integration', 'Microsoft SQL Server on ONTAP'),
            ('https://docs.netapp.com/us-en/ontap-apps-dbs/sap-hana/sap-hana-overview.html', 'integration', 'SAP HANA on ONTAP'),
            ('https://docs.netapp.com/us-en/ontap-apps-dbs/postgres/postgres-overview.html', 'integration', 'PostgreSQL on ONTAP'),
            ('https://docs.netapp.com/us-en/ontap-apps-dbs/mysql/mysql-overview.html', 'integration', 'MySQL on ONTAP'),
            ('https://docs.netapp.com/us-en/ontap-apps-dbs/mongodb/mongodb-overview.html', 'integration', 'MongoDB on ONTAP'),
            ('https://docs.netapp.com/us-en/ontap-apps-dbs/epic/epic-overview.html', 'integration', 'Epic EHR on ONTAP'),

            # Automation/DevOps
            ('https://docs.netapp.com/us-en/ontap-automation/index.html', 'automation', 'ONTAP REST API'),
            ('https://docs.netapp.com/us-en/ontap/task_configure_ontap.html', 'automation', 'Ansible Automation'),
            ('https://netapp.github.io/harvest/', 'automation', 'NetApp Harvest (Prometheus/Grafana)'),

            # Backup & Recovery
            ('https://docs.netapp.com/us-en/snapcenter/index.html', 'data_protection', 'SnapCenter Software'),
            ('https://docs.netapp.com/us-en/bluexp-backup-recovery/index.html', 'data_protection', 'BlueXP Backup and Recovery'),
            ('https://docs.netapp.com/us-en/bluexp-backup-recovery/concept-backup-to-cloud.html', 'cloud', 'Cloud Backup'),

            # Cloud Integration
            ('https://docs.netapp.com/us-en/bluexp-cloud-volumes-ontap/index.html', 'cloud', 'Cloud Volumes ONTAP'),
            ('https://docs.netapp.com/us-en/bluexp-fsx-ontap/index.html', 'cloud', 'Amazon FSx for ONTAP'),
            ('https://docs.netapp.com/us-en/bluexp-azure-netapp-files/index.html', 'cloud', 'Azure NetApp Files'),
            ('https://docs.netapp.com/us-en/bluexp-google-cloud-netapp-volumes/index.html', 'cloud', 'Google Cloud NetApp Volumes'),
            ('https://docs.netapp.com/us-en/bluexp-tiering/index.html', 'cloud', 'FabricPool Cloud Tiering'),
            ('https://docs.netapp.com/us-en/bluexp-classification/index.html', 'compliance', 'BlueXP Classification (Data Sense)'),

            # Monitoring & Observability
            ('https://docs.netapp.com/us-en/active-iq-unified-manager/index.html', 'monitoring', 'Active IQ Unified Manager'),
            ('https://docs.netapp.com/us-en/active-iq/index.html', 'monitoring', 'Active IQ Digital Advisor'),
            ('https://docs.netapp.com/us-en/bluexp-digital-wallet/index.html', 'monitoring', 'BlueXP Digital Wallet'),
            ('https://docs.netapp.com/us-en/storagegrid-enable/technical-reports/monitor-storagegrid-app-splunk.html', 'monitoring', 'Splunk Add-on for StorageGRID'),
            ('https://docs.netapp.com/us-en/netapp-solutions-ai/data-analytics/stgr-splunkss-introduction.html', 'monitoring', 'Splunk SmartStore on StorageGRID S3'),
            ('https://docs.netapp.com/us-en/storagegrid-enable/tools-apps-guides/use-datadog-snmp.html', 'monitoring', 'Datadog SNMP Monitoring for StorageGRID'),
            ('https://docs.netapp.com/us-en/data-infrastructure-insights/task_dc_na_cdot.html', 'monitoring', 'Data Infrastructure Insights ONTAP Collector'),

            # ITSM / SIEM / SOAR Integration
            ('https://docs.netapp.com/us-en/data-services-ransomware-resilience/reference-soar.html', 'security', 'Ransomware Resilience SOAR Integration (Sentinel/Splunk)'),
            ('https://docs.netapp.com/us-en/oncommand-insight/howto/servicenow-integration-set-up-user.html', 'automation', 'ServiceNow CMDB Integration for OnCommand Insight'),
            ('https://docs.netapp.com/us-en/oncommand-insight/howto/servicenow-integration-install-update-set.html', 'automation', 'ServiceNow Update Set Installation'),

            # Container Platforms — Red Hat OpenShift
            ('https://docs.netapp.com/us-en/netapp-solutions/containers/rh-os-n_solution_overview.html', 'integration', 'Red Hat OpenShift on NetApp (NVA-1160)'),
            ('https://docs.netapp.com/us-en/netapp-solutions-virtualization/openshift/osv-vm-dr-using-tp.html', 'data_protection', 'OpenShift Virtualization DR with Trident Protect'),
            ('https://docs.netapp.com/us-en/netapp-solutions/rhhc/rhhc-op-data-protection.html', 'data_protection', 'OpenShift Container Data Protection (Astra/Trident Protect)'),

            # Additional Database Integration
            ('https://docs.netapp.com/us-en/snapcenter/protect-db2/snapcenter-plug-in-for-ibm-db2-overview.html', 'integration', 'SnapCenter Plug-in for IBM Db2'),
            ('https://docs.netapp.com/us-en/netapp-solutions-sap/backup/snapcenter-ibm-db2.html', 'integration', 'SnapCenter for IBM Db2 on SAP'),

            # Security & Compliance
            ('https://docs.netapp.com/us-en/ontap/security/index.html', 'security', 'ONTAP Security Hardening Guide'),
            ('https://docs.netapp.com/us-en/ontap/anti-ransomware/index.html', 'security', 'Autonomous Ransomware Protection'),
            ('https://docs.netapp.com/us-en/ontap/encryption-at-rest/index.html', 'security', 'ONTAP Encryption at Rest (NVE/NAE)'),
            ('https://docs.netapp.com/us-en/ontap/zero-trust/zero-trust-overview.html', 'security', 'Zero Trust with ONTAP'),

            # Data Protection & DR
            ('https://docs.netapp.com/us-en/ontap-metrocluster/index.html', 'data_protection', 'MetroCluster Configuration'),
            ('https://docs.netapp.com/us-en/ontap/mediator/index.html', 'data_protection', 'ONTAP Mediator'),
            ('https://docs.netapp.com/us-en/ontap/volumes/flexclone-efficient-copies-concept.html', 'data_protection', 'FlexClone'),

            # Storage Efficiency
            ('https://docs.netapp.com/us-en/ontap/volumes/deduplication-data-compression-efficiency-concept.html', 'performance', 'Storage Efficiency Overview'),
        ]
        for doc_url, category, title in integration_seeds:
            if doc_url not in existing_urls:
                new_articles.append({
                    'url': doc_url,
                    'title': title,
                    'source': 'docs.netapp.com',
                    'category': category,
                    'relevance': f'Fleet-relevant {category} documentation',
                    'discoveredAt': datetime.now(timezone.utc).isoformat()[:10],
                })
                existing_urls.add(doc_url)

        # ── 6c-auto. Dynamic discovery: crawl docs.netapp.com product index ──
        _discovery_urls = [
            'https://docs.netapp.com/us-en/',
            'https://docs.netapp.com/us-en/netapp-solutions/',
        ]
        for catalog_url in _discovery_urls:
            try:
                text, err = _enrich_fetch(catalog_url, timeout=20)
                if err or not text:
                    continue
                links = _re.findall(
                    r'href="((?:https://docs\.netapp\.com)?/us-en/([a-z0-9][a-z0-9_-]{3,60})(?:/[^"]{0,80})?\.html)"[^>]*>([^<]{5,120})</a>',
                    text, _re.IGNORECASE
                )
                for href, repo_slug, link_title in links:
                    full_url = href if href.startswith('http') else f'https://docs.netapp.com{href}'
                    if full_url in existing_urls:
                        continue
                    if any(x in full_url for x in ['#', '.png', '.jpg', '.svg', 'mailto:', 'javascript:']):
                        continue
                    title_clean = html.unescape(link_title).strip()
                    if len(title_clean) < 8 or title_clean.lower() in ('index', 'home', 'back', 'next', 'previous'):
                        continue
                    slug_lower = repo_slug.lower()
                    title_lower = title_clean.lower()
                    cat = 'reference'
                    if any(k in slug_lower or k in title_lower for k in ['vmware', 'vsphere', 'vcenter', 'vvol']):
                        cat = 'integration'
                    elif any(k in slug_lower or k in title_lower for k in ['trident', 'kubernetes', 'k8s', 'astra', 'openshift', 'container', 'docker', 'rancher']):
                        cat = 'integration'
                    elif any(k in slug_lower or k in title_lower for k in ['oracle', 'sql', 'sap', 'hana', 'db2', 'mysql', 'postgres', 'mongo', 'database', 'epic']):
                        cat = 'integration'
                    elif any(k in slug_lower or k in title_lower for k in ['ansible', 'terraform', 'automation', 'rest-api', 'powershell']):
                        cat = 'automation'
                    elif any(k in slug_lower or k in title_lower for k in ['aws', 'azure', 'gcp', 'cloud', 'fsx', 'bluexp', 'occm']):
                        cat = 'cloud'
                    elif any(k in slug_lower or k in title_lower for k in ['backup', 'commvault', 'veeam', 'veritas', 'ndmp', 'snapcenter']):
                        cat = 'integration'
                    elif any(k in slug_lower or k in title_lower for k in ['splunk', 'kafka', 'spark', 'hadoop', 'analytics', 'ai', 'gpu', 'nvidia', 'ml']):
                        cat = 'integration'
                    elif any(k in slug_lower or k in title_lower for k in ['migrate', 'transition', 'import', 'xcp']):
                        cat = 'migration'
                    elif any(k in slug_lower or k in title_lower for k in ['security', 'ransomware', 'encrypt', 'zero-trust']):
                        cat = 'security'
                    elif any(k in slug_lower or k in title_lower for k in ['san', 'nvme', 'iscsi', 'fc', 'host']):
                        cat = 'integration'
                    elif any(k in slug_lower or k in title_lower for k in ['storagegrid', 's3', 'object']):
                        cat = 'integration'
                    elif any(k in slug_lower or k in title_lower for k in ['solution', 'best-practice', 'validated', 'design']):
                        cat = 'best_practices'

                    new_articles.append({
                        'url': full_url,
                        'title': title_clean,
                        'source': 'docs.netapp.com',
                        'category': cat,
                        'discoveredAt': datetime.now(timezone.utc).isoformat()[:10],
                        '_autoDiscovered': True,
                    })
                    existing_urls.add(full_url)
                time.sleep(2)
            except Exception:
                pass

        # ── 6d. Scan for new EOA announcements ──
        try:
            eoa_url = 'https://docs.netapp.com/us-en/ontap-systems/endofavail/'
            text, err = _enrich_fetch(eoa_url, timeout=15)
            if text and not err:
                eoa_links = _re.findall(r'href="([^"]*end-of-avail[^"]*\.html)"', text)
                for link in eoa_links:
                    full_url = f'https://docs.netapp.com/us-en/ontap-systems/endofavail/{link}' if not link.startswith('http') else link
                    if full_url not in existing_urls:
                        new_articles.append({
                            'url': full_url,
                            'title': f'EOA Notice: {link.replace(".html", "").replace("-", " ").title()}',
                            'source': 'docs.netapp.com',
                            'category': 'lifecycle',
                            'discoveredAt': datetime.now(timezone.utc).isoformat()[:10],
                        })
                        existing_urls.add(full_url)
        except Exception:
            pass

        # ── 6e. Fleet-aware operational / troubleshooting / remediation docs ──
        fleet_articles_added = 0
        try:
            db = _init_db()
            cached_result, _ = _load_cached(db)
            db.close()
        except Exception:
            cached_result = None

        if cached_result:
            fleet_systems = cached_result.get('systems', [])
            fleet_versions = set()
            fleet_major_versions = set()
            fleet_platforms = set()
            fleet_products = set()
            fleet_models = set()
            for sys in fleet_systems:
                ver = sys.get('osVersion') or ''
                if ver:
                    fleet_versions.add(ver)
                    m = _re.match(r'(\d+\.\d+)', ver)
                    if m:
                        fleet_major_versions.add(m.group(1))
                plat = (sys.get('platform') or sys.get('platformType') or '').lower()
                if plat:
                    fleet_platforms.add(plat)
                prod = (sys.get('productType') or sys.get('systemType') or '').lower()
                if prod:
                    fleet_products.add(prod)
                model = (sys.get('model') or '').upper()
                if model:
                    model_family = _re.sub(r'\s+', '-', model.strip())
                    fleet_models.add(model_family)

            print(f'  [ENRICH]   Fleet profile: {len(fleet_systems)} systems, '
                  f'{len(fleet_major_versions)} ONTAP versions, '
                  f'{len(fleet_models)} model families', flush=True)

            # ── 6e-i. Version-specific ONTAP documentation ──
            for major_ver in sorted(fleet_major_versions):
                ver_docs = [
                    ('https://docs.netapp.com/us-en/ontap/release-notes/index.html', 'operations', f'ONTAP Release Notes'),
                    ('https://docs.netapp.com/us-en/ontap/upgrade/index.html', 'upgrade', f'ONTAP Upgrade Guide'),
                    ('https://docs.netapp.com/us-en/ontap/revert/index.html', 'operations', f'ONTAP Revert Procedures'),
                    ('https://docs.netapp.com/us-en/ontap/system-admin/index.html', 'operations', f'ONTAP System Administration'),
                    ('https://docs.netapp.com/us-en/ontap-cli/index.html', 'operations', f'ONTAP CLI Reference'),
                    ('https://docs.netapp.com/us-en/ontap/networking/index.html', 'operations', f'ONTAP Network Management'),
                    ('https://docs.netapp.com/us-en/ontap/security/index.html', 'security', f'ONTAP Security Hardening'),
                    ('https://docs.netapp.com/us-en/ontap/anti-ransomware/index.html', 'security', f'ONTAP Anti-Ransomware'),
                    ('https://docs.netapp.com/us-en/ontap/data-protection/index.html', 'data_protection', f'ONTAP Data Protection'),
                    ('https://docs.netapp.com/us-en/ontap/performance-admin/index.html', 'performance', f'ONTAP Performance Monitoring'),
                    ('https://docs.netapp.com/us-en/ontap/error-messages/index.html', 'troubleshooting', f'ONTAP Error Messages & Remediation'),
                    ('https://docs.netapp.com/us-en/ontap/volumes/index.html', 'operations', f'ONTAP Volume Management'),
                    ('https://docs.netapp.com/us-en/ontap/san-admin/index.html', 'operations', f'ONTAP SAN Administration'),
                    ('https://docs.netapp.com/us-en/ontap/nas-audit/index.html', 'operations', f'ONTAP NAS Audit & Tracking'),
                    ('https://docs.netapp.com/us-en/ontap/fabricpool/index.html', 'configuration', f'ONTAP FabricPool Configuration'),
                    ('https://docs.netapp.com/us-en/ontap/peering/index.html', 'data_protection', f'ONTAP Cluster Peering'),
                    ('https://docs.netapp.com/us-en/ontap/mediator/index.html', 'data_protection', f'ONTAP Mediator for MetroCluster/SMBC'),
                    ('https://docs.netapp.com/us-en/ontap/encryption-at-rest/index.html', 'security', f'ONTAP Encryption at Rest'),
                ]
                
                for doc_url, category, title in ver_docs:
                    if doc_url not in existing_urls:
                        new_articles.append({
                            'url': doc_url,
                            'title': title,
                            'source': 'docs.netapp.com',
                            'category': category,
                            'relevance': f'ONTAP {major_ver} deployed in fleet',
                            'discoveredAt': datetime.now(timezone.utc).isoformat()[:10],
                            '_fleetRelevant': True,
                        })
                        existing_urls.add(doc_url)
                        fleet_articles_added += 1

            # ── 6e-ii. Platform-specific hardware & maintenance docs ──
            platform_doc_map = {
                'aff': [
                    ('https://docs.netapp.com/us-en/ontap-systems/index.html', 'operations', 'AFF/FAS Hardware Installation & Maintenance'),
                    ('https://docs.netapp.com/us-en/ontap-systems/aff-aseries/index.html', 'operations', 'AFF A-Series Systems Installation'),
                    ('https://docs.netapp.com/us-en/ontap-systems/aff-cseries/index.html', 'operations', 'AFF C-Series Systems Installation'),
                ],
                'fas': [
                    ('https://docs.netapp.com/us-en/ontap-systems/index.html', 'operations', 'AFF/FAS Hardware Installation & Maintenance'),
                    ('https://docs.netapp.com/us-en/ontap-systems/fas/index.html', 'operations', 'FAS Systems Installation'),
                ],
                'asa': [
                    ('https://docs.netapp.com/us-en/ontap-systems/index.html', 'operations', 'AFF/FAS Hardware Installation & Maintenance'),
                    ('https://docs.netapp.com/us-en/ontap/san-admin/index.html', 'operations', 'ASA — SAN Administration (Block-Optimised)'),
                    ('https://docs.netapp.com/us-en/ontap-systems/allsan-landing/index.html', 'operations', 'ASA Systems Documentation'),
                    ('https://docs.netapp.com/us-en/asa-r2/index.html', 'operations', 'ASA r2 Systems Documentation'),
                ],
                'afx': [
                    ('https://docs.netapp.com/us-en/ontap-systems/afx/index.html', 'operations', 'AFX Systems Documentation'),
                ],
                'shelves': [
                    ('https://docs.netapp.com/us-en/ontap-systems/drive-shelves/index.html', 'operations', 'Drive Shelves Installation'),
                ],
                'switches': [
                    ('https://docs.netapp.com/us-en/ontap-systems-switches/index.html', 'operations', 'Switches Documentation'),
                ]
            }
            
            detected_families = set()
            for plat in fleet_platforms:
                for family_key in platform_doc_map:
                    if family_key in plat: detected_families.add(family_key)
            for prod in fleet_products:
                for family_key in platform_doc_map:
                    if family_key in prod: detected_families.add(family_key)
            for model in fleet_models:
                model_l = model.lower()
                if 'aff' in model_l or model_l.startswith('a'): detected_families.add('aff')
                if 'fas' in model_l: detected_families.add('fas')
                if 'asa' in model_l: detected_families.add('asa')
                if 'afx' in model_l: detected_families.add('afx')

            if not detected_families:
                detected_families = {'aff', 'fas'}

            detected_families.add('shelves')
            detected_families.add('switches')

            for family in detected_families:
                docs = platform_doc_map.get(family, [])
                for doc_url, category, title in docs:
                    if doc_url not in existing_urls:
                        new_articles.append({
                            'url': doc_url,
                            'title': title,
                            'source': 'docs.netapp.com',
                            'category': category,
                            'relevance': f'{family.upper()} platform in fleet',
                            'discoveredAt': datetime.now(timezone.utc).isoformat()[:10],
                            '_fleetRelevant': True,
                        })
                        existing_urls.add(doc_url)
                        fleet_articles_added += 1

            # ── 6e-iii. Model-specific hardware procedures ──
            for model in sorted(fleet_models):
                model_slug = model.lower().replace(' ', '-')
                hw_docs = [
                    (f'https://docs.netapp.com/us-en/ontap-systems/{model_slug}/install-setup.html',
                     'operations', f'{model} — Installation & Setup'),
                    (f'https://docs.netapp.com/us-en/ontap-systems/{model_slug}/maintain-overview.html',
                     'operations', f'{model} — Hardware Maintenance'),
                ]
                for doc_url, category, title in hw_docs:
                    if doc_url not in existing_urls:
                        new_articles.append({
                            'url': doc_url,
                            'title': title,
                            'source': 'docs.netapp.com',
                            'category': category,
                            'relevance': f'{model} deployed in fleet',
                            'discoveredAt': datetime.now(timezone.utc).isoformat()[:10],
                            '_fleetRelevant': True,
                        })
                        existing_urls.add(doc_url)
                        fleet_articles_added += 1

            # ── 6e-iv. Fleet KB searches (JSON-LD category crawling) ──
            fleet_kb_urls = [
                'https://kb.netapp.com/on-prem/ontap/da',
                'https://kb.netapp.com/on-prem/ontap/DP',
                'https://kb.netapp.com/on-prem/ontap/DM',
                'https://kb.netapp.com/on-prem/ontap/mc',
                'https://kb.netapp.com/on-prem/ontap/DP/SnapMirror',
                'https://kb.netapp.com/on-prem/ontap/DP/SnapLock',
                'https://kb.netapp.com/on-prem/ontap/da/NAS',
                'https://kb.netapp.com/on-prem/ontap/da/SAN',
            ]
            
            for base_url in fleet_kb_urls:
                try:
                    text, err = _enrich_fetch(base_url, timeout=15)
                    if not err and text:
                        ld_blocks = _re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', text, _re.DOTALL)
                        for block in ld_blocks:
                            try:
                                data = _json_mod.loads(block)
                                if 'mainEntity' in data:
                                    for item in data['mainEntity'].get('itemListElement', []):
                                        url = item.get('url', '')
                                        name = item.get('name', '')
                                        if url and url.startswith('https://kb.netapp.com/'):
                                            if url not in existing_urls:
                                                new_articles.append({
                                                    'url': url,
                                                    'title': html.unescape(name).strip() if name else url.split('/')[-1].replace('-', ' ').title(),
                                                    'source': 'kb.netapp.com',
                                                    'category': 'troubleshooting',
                                                    'relevance': 'fleet-specific',
                                                    'discoveredAt': datetime.now(timezone.utc).isoformat()[:10],
                                                    '_fleetRelevant': True,
                                                })
                                                existing_urls.add(url)
                                                fleet_articles_added += 1
                            except: pass
                    time.sleep(2)
                except Exception:
                    pass

            # ── 6e-v. Remediation docs for active risks/advisories ──
            if BULLETINS_PATH.exists():
                try:
                    bdata = json.loads(BULLETINS_PATH.read_text(encoding='utf-8'))
                    bulletins = bdata.get('bulletins', [])
                    critical_bulletins = [
                        b for b in bulletins
                        if b.get('severity', '').lower() in ('critical', 'high')
                    ]
                    
                    remediation_docs = [
                        ('https://docs.netapp.com/us-en/ontap/antivirus/index.html', 'Antivirus Configuration'),
                        ('https://docs.netapp.com/us-en/ontap/anti-ransomware/index.html', 'Anti-Ransomware Configuration'),
                        ('https://docs.netapp.com/us-en/ontap/nas-audit/index.html', 'NAS Audit Configuration'),
                        ('https://docs.netapp.com/us-en/ontap/multi-admin-verify/index.html', 'Multi-Admin Verify'),
                        ('https://docs.netapp.com/us-en/ontap/snaplock/index.html', 'SnapLock Configuration'),
                        ('https://docs.netapp.com/us-en/ontap/authentication/workflow-concept.html', 'Authentication Workflow'),
                        ('https://docs.netapp.com/us-en/ontap-technical-reports/ransomware-solutions/ransomware-overview.html', 'Ransomware Solutions Overview'),
                    ]
                    
                    for b in critical_bulletins[:20]:
                        adv_url = b.get('url')
                        if adv_url and adv_url.startswith('https://security.netapp.com/') and adv_url not in existing_urls:
                            new_articles.append({
                                'url': adv_url,
                                'title': f"Advisory Remediation: {b.get('title', 'Security Bulletin')}",
                                'source': 'security.netapp.com',
                                'category': 'remediation',
                                'relevance': 'Active critical advisory',
                                'discoveredAt': datetime.now(timezone.utc).isoformat()[:10],
                                '_fleetRelevant': True,
                            })
                            existing_urls.add(adv_url)
                            fleet_articles_added += 1
                            
                    for r_url, r_title in remediation_docs:
                        if r_url not in existing_urls:
                            new_articles.append({
                                'url': r_url,
                                'title': r_title,
                                'source': 'docs.netapp.com',
                                'category': 'remediation',
                                'relevance': 'Security Remediation Guide',
                                'discoveredAt': datetime.now(timezone.utc).isoformat()[:10],
                                '_fleetRelevant': True,
                            })
                            existing_urls.add(r_url)
                            fleet_articles_added += 1
                            
                except Exception:
                    pass

            print(f'  [ENRICH]   Fleet-aware docs: +{fleet_articles_added} articles '
                  f'for {len(fleet_major_versions)} ONTAP versions, '
                  f'{len(detected_families)} platform families', flush=True)

            # ── 6f. 3rd Party Vendor Documentation & Best Practice Alignment ──
            # Comprehensive vendor guideline enrichment: detects which 3rd party
            # integrations are in use (or likely in use) based on fleet telemetry,
            # then pulls relevant vendor documentation, NetApp configuration
            # guidelines, and best practice alignment notes.
            vendor_articles_added = 0

            # ── Fleet Integration Detection Heuristics ──
            # Scan fleet telemetry for signals that indicate which 3rd party
            # platforms/tools are in use or relevant.
            fleet_signals = {
                'vmware':    False, 'hyperv':     False, 'kvm_linux':  False,
                'proxmox':   False, 'nutanix':    False, 'kubernetes': False,
                'cisco_san': False, 'brocade_fc': False, 'broadcom_eth': False,
                'oracle_db': False, 'mssql':      False, 'sap_hana':   False,
                'veeam':     False, 'commvault':  False, 'rubrik':     False,
                'cohesity':  False, 'hycu':       False, 'veritas':    False,
                'snapcenter': False, 'fabricpool': False, 'metrocluster': False,
                'snapmirror': False, 'arp':        False, 'fpolicy':    False,
                'eseries':   False, 'storagegrid': False, 'asa_r2':     False,
                'afx':       False, 'nvme':       False, 'iscsi':      False,
                'fc_san':    False, 'nfs':        False, 'smb_cifs':   False,
                'ai_ml':     False, 'splunk':     False, 'crowdstrike': False,
                'paloalto':  False, 'varonis':    False, 'cyberark':   False,
                'flexpod':   False,
            }

            for sys_item in fleet_systems:
                plat_str = (sys_item.get('platform') or sys_item.get('platformType') or '').lower()
                model_str = (sys_item.get('model') or '').lower()
                prod_str = (sys_item.get('productType') or sys_item.get('systemType') or '').lower()
                ver_str = sys_item.get('osVersion') or ''
                all_text = f'{plat_str} {model_str} {prod_str}'.lower()

                # Platform type detection
                if 'storagegrid' in all_text: fleet_signals['storagegrid'] = True
                if 'e-series' in all_text or 'ef6' in all_text or 'ef3' in all_text or 'ef50' in all_text or 'ef80' in all_text or 'e2800' in all_text or 'e5700' in all_text:
                    fleet_signals['eseries'] = True
                if 'asa' in all_text and ('r2' in all_text or 'a20' in model_str or 'a30' in model_str or 'a50' in model_str or 'a70' in model_str or 'a90' in model_str):
                    fleet_signals['asa_r2'] = True
                if 'afx' in all_text: fleet_signals['afx'] = True
                if 'flexpod' in all_text or 'ucs' in all_text: fleet_signals['flexpod'] = True
                if 'nutanix' in all_text: fleet_signals['nutanix'] = True

                # Feature/protocol detection from system properties
                if sys_item.get('isARPEnabled'): fleet_signals['arp'] = True
                if sys_item.get('isFabricPoolEnabled') or (sys_item.get('efficiency') or {}).get('fabricPoolTieredTB', 0) > 0:
                    fleet_signals['fabricpool'] = True
                if sys_item.get('snapmirror') and sys_item.get('snapmirror', {}).get('enabled'):
                    fleet_signals['snapmirror'] = True
                # Fixed field-name mismatch: the harvested field is "isMetroCluster"
                # (server.py systems_out), not "isMetroClusterConfigured" -- the old
                # key was never set anywhere, so this signal was permanently False
                # even for genuine MetroCluster fleets, silently suppressing the
                # MetroCluster vendor-guidelines articles from ever being recommended.
                if sys_item.get('isMetroCluster'):
                    fleet_signals['metrocluster'] = True

                # Switch detection from switch data
                switches = sys_item.get('switches') or sys_item.get('clusterSwitches') or []
                if isinstance(switches, list):
                    for sw in switches:
                        sw_model = (sw.get('model') or sw.get('switchModel') or '').lower()
                        sw_vendor = (sw.get('vendor') or '').lower()
                        if 'cisco' in sw_model or 'cisco' in sw_vendor or 'nexus' in sw_model or 'mds' in sw_model:
                            fleet_signals['cisco_san'] = True
                        if 'brocade' in sw_model or 'brocade' in sw_vendor:
                            fleet_signals['brocade_fc'] = True
                        if 'broadcom' in sw_model or 'bes-53248' in sw_model:
                            fleet_signals['broadcom_eth'] = True

                # Host/hypervisor detection from connected hosts
                hosts = sys_item.get('hosts') or sys_item.get('connectedHosts') or []
                if isinstance(hosts, list):
                    for host in hosts:
                        host_os = (host.get('os') or host.get('osType') or host.get('type') or '').lower()
                        if 'vmware' in host_os or 'esxi' in host_os or 'vsphere' in host_os:
                            fleet_signals['vmware'] = True
                        if 'hyper-v' in host_os or 'hyperv' in host_os or 'windows' in host_os:
                            fleet_signals['hyperv'] = True
                        if 'linux' in host_os or 'rhel' in host_os or 'suse' in host_os or 'ubuntu' in host_os or 'centos' in host_os:
                            fleet_signals['kvm_linux'] = True

                # Protocol detection from LIF/interface data
                lifs = sys_item.get('lifs') or sys_item.get('interfaces') or []
                if isinstance(lifs, list):
                    for lif in lifs:
                        proto = (lif.get('dataProtocol') or lif.get('protocol') or '').lower()
                        if 'nfs' in proto: fleet_signals['nfs'] = True
                        if 'cifs' in proto or 'smb' in proto: fleet_signals['smb_cifs'] = True
                        if 'iscsi' in proto: fleet_signals['iscsi'] = True
                        if 'fc' in proto or 'fcp' in proto: fleet_signals['fc_san'] = True
                        if 'nvme' in proto: fleet_signals['nvme'] = True

                # Risk-based detection (risks mentioning 3rd party tools)
                risks = sys_item.get('risks') or []
                if isinstance(risks, list):
                    for risk in risks:
                        risk_text = (risk.get('description') or risk.get('name') or '').lower()
                        if 'snapcenter' in risk_text: fleet_signals['snapcenter'] = True
                        if 'fpolicy' in risk_text: fleet_signals['fpolicy'] = True
                        if 'veeam' in risk_text: fleet_signals['veeam'] = True
                        if 'commvault' in risk_text or 'intellisnap' in risk_text: fleet_signals['commvault'] = True
                        if 'flexPod' in risk_text or 'flexpod' in risk_text or 'ucs' in risk_text: fleet_signals['flexpod'] = True
                        if 'nutanix' in risk_text or 'ahv' in risk_text: fleet_signals['nutanix'] = True
                        # Backup vendors
                        if 'rubrik' in risk_text: fleet_signals['rubrik'] = True
                        if 'cohesity' in risk_text: fleet_signals['cohesity'] = True
                        if 'hycu' in risk_text: fleet_signals['hycu'] = True
                        if 'veritas' in risk_text or 'netbackup' in risk_text or 'backup exec' in risk_text: fleet_signals['veritas'] = True
                        # Databases
                        if 'oracle' in risk_text or 'dnfs' in risk_text or 'asm' in risk_text: fleet_signals['oracle_db'] = True
                        if 'sql server' in risk_text or 'mssql' in risk_text or 'always on' in risk_text: fleet_signals['mssql'] = True
                        if 'sap hana' in risk_text or 'sap' in risk_text: fleet_signals['sap_hana'] = True
                        # Security & observability
                        if 'crowdstrike' in risk_text or 'falcon' in risk_text: fleet_signals['crowdstrike'] = True
                        if 'palo alto' in risk_text or 'prisma' in risk_text or 'cortex' in risk_text: fleet_signals['paloalto'] = True
                        if 'varonis' in risk_text: fleet_signals['varonis'] = True
                        if 'cyberark' in risk_text: fleet_signals['cyberark'] = True
                        if 'splunk' in risk_text: fleet_signals['splunk'] = True
                        # Kubernetes / containers
                        if 'kubernetes' in risk_text or 'trident' in risk_text or 'openshift' in risk_text: fleet_signals['kubernetes'] = True
                        # AI/ML workloads
                        if 'gpu' in risk_text or 'dgx' in risk_text or 'nvidia' in risk_text or 'ai ' in risk_text or 'machine learning' in risk_text: fleet_signals['ai_ml'] = True

                # Host-based extended detection (Proxmox, Nutanix, Kubernetes)
                if isinstance(hosts, list):
                    for host in hosts:
                        host_os = (host.get('os') or host.get('osType') or host.get('type') or '').lower()
                        if 'proxmox' in host_os or 'pve' in host_os: fleet_signals['proxmox'] = True
                        if 'nutanix' in host_os or 'ahv' in host_os: fleet_signals['nutanix'] = True

            # Count detected integrations
            detected_count = sum(1 for v in fleet_signals.values() if v)
            print(f'  [ENRICH]   Fleet integration signals: {detected_count} detected '
                  f'({", ".join(k for k, v in fleet_signals.items() if v) or "none"})', flush=True)

            # ── Vendor Documentation Source Registry ──
            # Maps vendor documentation URLs to categories, with fleet signal
            # conditions for relevance-aware enrichment. URLs with condition=None
            # are always fetched (core NetApp best practices). URLs with a
            # condition are only fetched when that fleet signal is detected.
            VENDOR_GUIDELINE_SOURCES = [
                # ═══════════════════════════════════════════════════════════════
                # CORE NETAPP BEST PRACTICES (always fetched)
                # ═══════════════════════════════════════════════════════════════
                # Security hardening & zero trust
                {'url': 'https://docs.netapp.com/us-en/ontap/security/index.html',
                 'title': 'ONTAP Security Hardening Guide', 'category': 'best_practices',
                 'alignment': 'TLS 1.2+ minimum, disable HTTP, MFA, MAV for destructive ops',
                 'condition': None},
                {'url': 'https://docs.netapp.com/us-en/ontap/zero-trust/zero-trust-overview.html',
                 'title': 'Zero Trust Architecture with ONTAP', 'category': 'best_practices',
                 'alignment': 'Zero-trust microsegmentation, least-privilege SVM isolation',
                 'condition': None},
                {'url': 'https://docs.netapp.com/us-en/ontap/anti-ransomware/index.html',
                 'title': 'Autonomous Ransomware Protection (ARP) Configuration',
                 'category': 'best_practices',
                 'alignment': 'ARP/AI (9.16.1+) zero-learning ML detection, 99% precision',
                 'condition': None},
                {'url': 'https://docs.netapp.com/us-en/ontap/encryption-at-rest/index.html',
                 'title': 'ONTAP Encryption at Rest (NVE/NAE)', 'category': 'best_practices',
                 'alignment': 'Data-at-rest encryption, key management, FIPS 140-2 compliance',
                 'condition': None},
                {'url': 'https://docs.netapp.com/us-en/ontap/multi-admin-verify/index.html',
                 'title': 'Multi-Admin Verification (MAV)', 'category': 'best_practices',
                 'alignment': 'MAV prevents single-admin destructive operations (9.11.1+)',
                 'condition': None},
                # Data protection & DR
                {'url': 'https://docs.netapp.com/us-en/ontap/data-protection/index.html',
                 'title': 'ONTAP Data Protection Overview', 'category': 'best_practices',
                 'alignment': 'SnapMirror, SnapVault, snapshot policies, consistency groups',
                 'condition': None},
                {'url': 'https://docs.netapp.com/us-en/ontap/snapmirror-active-sync/index.html',
                 'title': 'SnapMirror Active Sync (zero RPO/RTO)', 'category': 'best_practices',
                 'alignment': 'Transparent app failover <15s, requires Mediator + AFF/ASA',
                 'condition': None},
                # Performance & efficiency
                {'url': 'https://docs.netapp.com/us-en/ontap/performance-admin/index.html',
                 'title': 'ONTAP Performance Monitoring & QoS', 'category': 'best_practices',
                 'alignment': 'Adaptive QoS policies, workload balancing, latency monitoring',
                 'condition': None},
                {'url': 'https://docs.netapp.com/us-en/ontap/volumes/deduplication-data-compression-efficiency-concept.html',
                 'title': 'Storage Efficiency (Dedup/Compression)', 'category': 'best_practices',
                 'alignment': 'Inline dedup+compression, post-process dedup scheduling',
                 'condition': None},

                # ═══════════════════════════════════════════════════════════════
                # VIRTUALIZATION — VMware vSphere
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://docs.netapp.com/us-en/ontap-tools-vmware-vsphere-10/index.html',
                 'title': 'ONTAP Tools for VMware vSphere 10.x', 'category': 'vendor_guidelines',
                 'alignment': 'OTV 10.x for VAAI, VASA 3.0, vVols provisioning',
                 'condition': 'vmware'},
                {'url': 'https://docs.netapp.com/us-en/ontap-apps-dbs/vmware/vmware-vsphere-overview.html',
                 'title': 'VMware vSphere with ONTAP Best Practices', 'category': 'vendor_guidelines',
                 'alignment': 'NFS/iSCSI/FC datastore config, ESXi host settings, VAAI',
                 'condition': 'vmware'},
                {'url': 'https://docs.netapp.com/us-en/ontap-apps-dbs/vmware/vmware-otv-hardening-overview.html',
                 'title': 'VMware OTV Security Hardening', 'category': 'vendor_guidelines',
                 'alignment': 'OTV appliance hardening, certificate management',
                 'condition': 'vmware'},
                {'url': 'https://docs.netapp.com/us-en/ontap-apps-dbs/vmware/vmware-srm-overview.html',
                 'title': 'VMware SRM with ONTAP (DR Automation)', 'category': 'vendor_guidelines',
                 'alignment': 'SRA configuration, SnapMirror-based DR failover for VMs',
                 'condition': 'vmware'},
                {'url': 'https://docs.netapp.com/us-en/ontap-apps-dbs/vmware/vmware-vvols-overview.html',
                 'title': 'VMware vVols with ONTAP', 'category': 'vendor_guidelines',
                 'alignment': 'Per-VM storage policy, VASA Provider, FlexVol-backed vVols',
                 'condition': 'vmware'},
                {'url': 'https://docs.netapp.com/us-en/sc-plugin-vmware-vsphere/index.html',
                 'title': 'SnapCenter Plugin for VMware vSphere', 'category': 'vendor_guidelines',
                 'alignment': 'Application-consistent VM snapshots, backup scheduling',
                 'condition': 'vmware'},
                # VMware 3rd party docs
                {'url': 'https://docs.vmware.com/en/VMware-vSphere/index.html',
                 'title': 'VMware vSphere Documentation Portal', 'category': 'vendor_guidelines',
                 'alignment': 'Official VMware vSphere release docs and compatibility',
                 'condition': 'vmware'},
                {'url': 'https://knowledge.broadcom.com/external/article?articleNumber=315039',
                 'title': 'VMware NFS Best Practices (Broadcom KB)', 'category': 'vendor_guidelines',
                 'alignment': 'ESXi NFS mount options, timeout settings, multipath',
                 'condition': 'vmware'},

                # ═══════════════════════════════════════════════════════════════
                # VIRTUALIZATION — Microsoft Hyper-V
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://docs.netapp.com/us-en/ontap/smb-hyper-v-sql/index.html',
                 'title': 'ONTAP SMB for Hyper-V and SQL Server', 'category': 'vendor_guidelines',
                 'alignment': 'SMB 3.0 ODX, CSV with iSCSI, Hyper-V over SMB best practices',
                 'condition': 'hyperv'},
                {'url': 'https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/best-practices-analyzer/best-practices-analyzer-for-hyper-v',
                 'title': 'Microsoft Hyper-V Best Practices Analyzer', 'category': 'vendor_guidelines',
                 'alignment': 'Microsoft-recommended Hyper-V configuration guidelines',
                 'condition': 'hyperv'},
                {'url': 'https://docs.netapp.com/us-en/ontap-sanhost/hu_wuhu_72.html',
                 'title': 'Windows Unified Host Utilities 7.2', 'category': 'vendor_guidelines',
                 'alignment': 'MPIO configuration, disk timeout settings, iSCSI initiator',
                 'condition': 'hyperv'},

                # ═══════════════════════════════════════════════════════════════
                # VIRTUALIZATION — KVM/Linux
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://docs.netapp.com/us-en/ontap-sanhost/hu_luhu_71.html',
                 'title': 'Linux Host Utilities 7.1 Configuration', 'category': 'vendor_guidelines',
                 'alignment': 'dm-multipath, iSCSI initiator, NFS mount options for Linux',
                 'condition': 'kvm_linux'},
                {'url': 'https://docs.netapp.com/us-en/ontap/nfs-config/index.html',
                 'title': 'ONTAP NFS Configuration for Linux Hosts', 'category': 'vendor_guidelines',
                 'alignment': 'NFSv4.1 export policies, Kerberos, pNFS for FlexGroup',
                 'condition': 'kvm_linux'},

                # ═══════════════════════════════════════════════════════════════
                # CONTAINERS — Kubernetes / OpenShift
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://docs.netapp.com/us-en/trident/index.html',
                 'title': 'Astra Trident CSI Driver Documentation', 'category': 'vendor_guidelines',
                 'alignment': 'Trident 26.02.1 GA, StorageClass config, backend setup',
                 'condition': 'kubernetes'},
                {'url': 'https://docs.netapp.com/us-en/astra-control-center/index.html',
                 'title': 'Astra Control Center (K8s App Data Management)',
                 'category': 'vendor_guidelines',
                 'alignment': 'Application-aware backup/restore/clone for Kubernetes',
                 'condition': 'kubernetes'},

                # ═══════════════════════════════════════════════════════════════
                # SAN SWITCHING — Cisco
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://docs.netapp.com/us-en/ontap-systems-switches/index.html',
                 'title': 'NetApp Switch Documentation Portal', 'category': 'vendor_guidelines',
                 'alignment': 'Cluster/MetroCluster switch install, firmware upgrade procedures',
                 'condition': 'cisco_san'},
                {'url': 'https://www.cisco.com/c/en/us/support/switches/nexus-9000-series-switches/series.html',
                 'title': 'Cisco Nexus 9000 Series Documentation', 'category': 'vendor_guidelines',
                 'alignment': 'NX-OS 10.4.2 recommended for AFX, 9.3(12) for legacy 9336C-FX2',
                 'condition': 'cisco_san'},
                {'url': 'https://www.cisco.com/c/en/us/support/switches/mds-9000-series-multilayer-switches/series.html',
                 'title': 'Cisco MDS 9000 FC SAN Switch Documentation', 'category': 'vendor_guidelines',
                 'alignment': 'MDS firmware 9.2(2) recommended, FC zone configuration',
                 'condition': 'cisco_san'},

                # ═══════════════════════════════════════════════════════════════
                # SAN SWITCHING — Broadcom/Brocade
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://docs.broadcom.com/docs/FOS-92x-Admin',
                 'title': 'Brocade Fabric OS 9.2.x Administration Guide',
                 'category': 'vendor_guidelines',
                 'alignment': 'FOS 9.2.1 recommended, TruFOS certificate requirements',
                 'condition': 'brocade_fc'},
                {'url': 'https://techdocs.broadcom.com/us/en/fibre-channel-networking/fabric-os/fabric-os-administration/9-2-x.html',
                 'title': 'Broadcom Fabric OS Administration (9.2.x)',
                 'category': 'vendor_guidelines',
                 'alignment': 'Zone configuration, ISL trunking, firmware management',
                 'condition': 'brocade_fc'},

                # ═══════════════════════════════════════════════════════════════
                # BACKUP & DATA PROTECTION — Veeam
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://helpcenter.veeam.com/docs/backup/plugins/netapp_ontap_plugin.html',
                 'title': 'Veeam NetApp ONTAP Plugin Guide', 'category': 'vendor_guidelines',
                 'alignment': 'NetApp Plugin v2 for VBR 12.3+, snapshot orchestration',
                 'condition': 'veeam'},
                {'url': 'https://helpcenter.veeam.com/docs/backup/plugins/netapp_ontap_snapdiff.html',
                 'title': 'Veeam SnapDiff CFT Configuration', 'category': 'vendor_guidelines',
                 'alignment': 'Changed File Tracking via ONTAP SnapDiff API, NOT on 9.10.1-P10',
                 'condition': 'veeam'},
                {'url': 'https://www.veeam.com/kb4516',
                 'title': 'Veeam NetApp ONTAP Integration Requirements', 'category': 'vendor_guidelines',
                 'alignment': 'Storage integration compatibility matrix, plugin versions',
                 'condition': 'veeam'},

                # ═══════════════════════════════════════════════════════════════
                # BACKUP & DATA PROTECTION — Commvault
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://documentation.commvault.com/2024e/essential/snap_backup_netapp.html',
                 'title': 'Commvault IntelliSnap for NetApp ONTAP', 'category': 'vendor_guidelines',
                 'alignment': 'IntelliSnap snapshot orchestration, SnapVault integration',
                 'condition': 'commvault'},

                # ═══════════════════════════════════════════════════════════════
                # BACKUP & DATA PROTECTION — Rubrik
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://www.rubrik.com/solutions/netapp',
                 'title': 'Rubrik for NetApp ONTAP Integration', 'category': 'vendor_guidelines',
                 'alignment': 'NAS Cloud Direct, NDMP backup, Security Cloud DSPM',
                 'condition': 'rubrik'},

                # ═══════════════════════════════════════════════════════════════
                # BACKUP & DATA PROTECTION — Cohesity
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://docs.cohesity.com/',
                 'title': 'Cohesity DataProtect Documentation', 'category': 'vendor_guidelines',
                 'alignment': 'NDMP/NFS registration, DataHawk threat scanning',
                 'condition': 'cohesity'},

                # ═══════════════════════════════════════════════════════════════
                # BACKUP & DATA PROTECTION — HYCU
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://support.hycu.com/hc/en-us/categories/360001985619-HYCU-for-NetApp',
                 'title': 'HYCU for NetApp ONTAP Documentation', 'category': 'vendor_guidelines',
                 'alignment': 'Agentless REST API integration, R-Shield YARA scanning',
                 'condition': 'hycu'},

                # ═══════════════════════════════════════════════════════════════
                # BACKUP & DATA PROTECTION — SnapCenter (always if ONTAP)
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://docs.netapp.com/us-en/snapcenter/index.html',
                 'title': 'SnapCenter Software Documentation', 'category': 'vendor_guidelines',
                 'alignment': 'Application-consistent backups for Oracle, SQL, VMware, SAP',
                 'condition': None},

                # ═══════════════════════════════════════════════════════════════
                # DATABASES — Oracle
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://docs.netapp.com/us-en/ontap-apps-dbs/oracle/oracle-overview.html',
                 'title': 'Oracle Database on ONTAP Best Practices', 'category': 'vendor_guidelines',
                 'alignment': 'dNFS config, ASM on iSCSI/FC, RMAN to NFS, SnapCenter Oracle',
                 'condition': 'oracle_db'},
                {'url': 'https://docs.oracle.com/en/database/oracle/oracle-database/23/ntdbi/',
                 'title': 'Oracle Database NFS Direct (dNFS) Guide', 'category': 'vendor_guidelines',
                 'alignment': 'Oracle-side dNFS setup, oranfstab, multipath dispatchers',
                 'condition': 'oracle_db'},

                # ═══════════════════════════════════════════════════════════════
                # DATABASES — Microsoft SQL Server
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://docs.netapp.com/us-en/ontap-apps-dbs/mssql/mssql-overview.html',
                 'title': 'Microsoft SQL Server on ONTAP Best Practices', 'category': 'vendor_guidelines',
                 'alignment': 'SMB 3.0 for .mdf/.ldf, iSCSI MPIO, tempdb on NVMe/TCP',
                 'condition': 'mssql'},
                {'url': 'https://learn.microsoft.com/en-us/sql/sql-server/install/hardware-and-software-requirements-for-installing-sql-server',
                 'title': 'SQL Server Hardware & Software Requirements', 'category': 'vendor_guidelines',
                 'alignment': 'Microsoft storage requirements for SQL Server deployments',
                 'condition': 'mssql'},

                # ═══════════════════════════════════════════════════════════════
                # DATABASES — SAP HANA
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://docs.netapp.com/us-en/ontap-apps-dbs/sap-hana/sap-hana-overview.html',
                 'title': 'SAP HANA on ONTAP Best Practices', 'category': 'vendor_guidelines',
                 'alignment': 'SAP HANA TDI certification, NFS data/log volume layout',
                 'condition': 'sap_hana'},

                # ═══════════════════════════════════════════════════════════════
                # SAN HOST UTILITIES & MULTIPATH
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://docs.netapp.com/us-en/ontap-sanhost/',
                 'title': 'NetApp SAN Host Configuration Guide', 'category': 'vendor_guidelines',
                 'alignment': 'OS-specific SAN host settings, multipath, HBA drivers',
                 'condition': None},
                {'url': 'https://docs.netapp.com/us-en/ontap-sanhost/hu_vsphere_8.html',
                 'title': 'VMware ESXi 8.x SAN Host Settings', 'category': 'vendor_guidelines',
                 'alignment': 'ESXi multipath PSP, disk timeout, NFS VAAI plugin',
                 'condition': 'vmware'},

                # ═══════════════════════════════════════════════════════════════
                # PROTOCOLS — NVMe, iSCSI, FC, NFS, SMB
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://docs.netapp.com/us-en/ontap/san-admin/index.html',
                 'title': 'ONTAP SAN Administration (iSCSI/FC/NVMe)', 'category': 'best_practices',
                 'alignment': 'LUN provisioning, igroup config, ALUA, port sets',
                 'condition': None},
                {'url': 'https://docs.netapp.com/us-en/ontap/nvme/index.html',
                 'title': 'ONTAP NVMe-oF Configuration', 'category': 'vendor_guidelines',
                 'alignment': 'NVMe/FC and NVMe/TCP setup, namespace management (9.14.1+)',
                 'condition': 'nvme'},

                # ═══════════════════════════════════════════════════════════════
                # CLOUD TIERING — FabricPool
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://docs.netapp.com/us-en/ontap/fabricpool/index.html',
                 'title': 'FabricPool Cloud Tiering Configuration', 'category': 'best_practices',
                 'alignment': 'Cold data tiering to S3/Azure/GCS, auto/snapshot-only policies',
                 'condition': 'fabricpool'},

                # ═══════════════════════════════════════════════════════════════
                # METROCLUSTER & HA
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://docs.netapp.com/us-en/ontap-metrocluster/index.html',
                 'title': 'MetroCluster Configuration & Management', 'category': 'vendor_guidelines',
                 'alignment': 'FC/IP MetroCluster, ISL requirements, switchover/switchback',
                 'condition': 'metrocluster'},
                {'url': 'https://docs.netapp.com/us-en/ontap/mediator/index.html',
                 'title': 'ONTAP Mediator for MetroCluster/SMBC', 'category': 'vendor_guidelines',
                 'alignment': 'Mediator deployment for automatic unplanned switchover (AUSO)',
                 'condition': 'metrocluster'},

                # ═══════════════════════════════════════════════════════════════
                # SECURITY & CYBER VENDORS
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://docs.netapp.com/us-en/ontap/nas-audit/index.html',
                 'title': 'ONTAP NAS Auditing & FPolicy', 'category': 'vendor_guidelines',
                 'alignment': 'FPolicy for 3rd party security (Varonis, Netwrix, Superna)',
                 'condition': 'fpolicy'},
                {'url': 'https://docs.netapp.com/us-en/ontap/antivirus/index.html',
                 'title': 'ONTAP Antivirus (Vscan) Configuration', 'category': 'best_practices',
                 'alignment': 'Vscan integration with CrowdStrike, Sophos, Symantec, McAfee',
                 'condition': None},

                # ═══════════════════════════════════════════════════════════════
                # AI / ML WORKLOADS
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://docs.netapp.com/us-en/netapp-dataops-toolkit/',
                 'title': 'NetApp DataOps Toolkit (AI/ML)', 'category': 'vendor_guidelines',
                 'alignment': 'Python library for data scientists, NearClone, Jupyter',
                 'condition': 'ai_ml'},

                # ═══════════════════════════════════════════════════════════════
                # MONITORING & OBSERVABILITY
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://netapp.github.io/harvest/',
                 'title': 'NetApp Harvest 2.0 (Prometheus/Grafana)', 'category': 'vendor_guidelines',
                 'alignment': 'Open-source ONTAP metrics, pre-built Grafana dashboards',
                 'condition': None},
                {'url': 'https://docs.netapp.com/us-en/active-iq-unified-manager/index.html',
                 'title': 'Active IQ Unified Manager', 'category': 'vendor_guidelines',
                 'alignment': 'Fleet-wide ONTAP monitoring, health scoring, event management',
                 'condition': None},

                # ═══════════════════════════════════════════════════════════════
                # E-SERIES / STORAGEGRID
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://docs.netapp.com/us-en/e-series-santricity/index.html',
                 'title': 'SANtricity System Manager Documentation', 'category': 'vendor_guidelines',
                 'alignment': 'E-Series block array management, firmware updates',
                 'condition': 'eseries'},
                {'url': 'https://docs.netapp.com/us-en/storagegrid/index.html',
                 'title': 'StorageGRID Documentation', 'category': 'vendor_guidelines',
                 'alignment': 'Object storage grid management, ILM policies, S3 API',
                 'condition': 'storagegrid'},

                # ═══════════════════════════════════════════════════════════════
                # ASA r2 / AFX
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://docs.netapp.com/us-en/asa-r2/index.html',
                 'title': 'ASA r2 Systems Documentation', 'category': 'vendor_guidelines',
                 'alignment': 'Storage units, SAN-optimized provisioning, SAZ topology',
                 'condition': 'asa_r2'},
                {'url': 'https://docs.netapp.com/us-en/ontap-systems/afx/index.html',
                 'title': 'AFX Disaggregated ONTAP Systems', 'category': 'vendor_guidelines',
                 'alignment': 'AFX 1K/2K hardware, NSM140 shelves, REST-only API',
                 'condition': 'afx'},

                # ═══════════════════════════════════════════════════════════════
                # AUTOMATION & DEVOPS
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://docs.netapp.com/us-en/ontap-automation/index.html',
                 'title': 'ONTAP REST API Automation', 'category': 'best_practices',
                 'alignment': 'REST API for all ONTAP operations, Ansible modules',
                 'condition': None},

                # ═══════════════════════════════════════════════════════════════
                # CLOUD INTEGRATIONS
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://docs.netapp.com/us-en/bluexp-cloud-volumes-ontap/index.html',
                 'title': 'Cloud Volumes ONTAP (CVO)', 'category': 'vendor_guidelines',
                 'alignment': 'CVO 9.18.1 across AWS/Azure/GCP, same Trident/SnapCenter surface',
                 'condition': None},
                {'url': 'https://docs.netapp.com/us-en/bluexp-fsx-ontap/index.html',
                 'title': 'Amazon FSx for ONTAP', 'category': 'vendor_guidelines',
                 'alignment': 'Fully managed ONTAP on AWS, sub-ms SSD latency',
                 'condition': None},
                {'url': 'https://docs.netapp.com/us-en/bluexp-azure-netapp-files/index.html',
                 'title': 'Azure NetApp Files (ANF)', 'category': 'vendor_guidelines',
                 'alignment': 'Azure-native file storage, migration assistant, cache volumes',
                 'condition': None},
                {'url': 'https://docs.netapp.com/us-en/bluexp-google-cloud-netapp-volumes/index.html',
                 'title': 'Google Cloud NetApp Volumes (GCNV)', 'category': 'vendor_guidelines',
                 'alignment': 'GCNV Flex Unified service level, backup/replication GA',
                 'condition': None},

                # ═══════════════════════════════════════════════════════════════
                # MIGRATION
                # ═══════════════════════════════════════════════════════════════
                {'url': 'https://docs.netapp.com/us-en/ontap-fli/',
                 'title': 'Foreign LUN Import (FLI)', 'category': 'vendor_guidelines',
                 'alignment': 'Non-disruptive LUN migration from 3rd party arrays to ONTAP',
                 'condition': None},

                # ═══════════════════════════════════════════════════════════════
                # CERTIFIED REFERENCE ARCHITECTURES & VALIDATED DESIGNS (NVA/CVD)
                # ═══════════════════════════════════════════════════════════════
                # FlexPod (Cisco + NetApp converged infrastructure)
                {'url': 'https://www.cisco.com/c/en/us/solutions/design-zone/data-center-design-guides/flexpod-design-guides.html',
                 'title': 'FlexPod Design Zone — Cisco Validated Designs (CVDs)',
                 'category': 'reference_architecture',
                 'alignment': 'Cisco UCS + NetApp ONTAP converged infrastructure — validated end-to-end designs for enterprise workloads',
                 'condition': None},
                {'url': 'https://www.netapp.com/flexpod/',
                 'title': 'FlexPod Solutions Portal',
                 'category': 'reference_architecture',
                 'alignment': 'NetApp + Cisco joint solution: compute, network, storage — pre-validated reference architectures',
                 'condition': 'flexpod'},
                {'url': 'https://docs.netapp.com/us-en/flexpod/',
                 'title': 'FlexPod Documentation Center',
                 'category': 'reference_architecture',
                 'alignment': 'FlexPod deployment guides, upgrade procedures, and architecture updates',
                 'condition': 'flexpod'},

                # NetApp Verified Architectures (NVA) — workload-specific validated designs
                {'url': 'https://www.netapp.com/data-management/resources/?type=verified-architecture',
                 'title': 'NetApp Verified Architectures (NVA) Library',
                 'category': 'reference_architecture',
                 'alignment': 'Workload-specific validated architectures: databases, VDI, AI/ML, healthcare, SAP, analytics',
                 'condition': None},

                # Technical Reports (TRs) — deep-dive reference documents
                {'url': 'https://www.netapp.com/media/10674-tr4569.pdf',
                 'title': 'TR-4569: ONTAP 9 Security Hardening Guide',
                 'category': 'reference_architecture',
                 'alignment': 'NetApp-certified security hardening procedures, CIS benchmarks, STIG compliance, zero-trust',
                 'condition': None},
                {'url': 'https://www.netapp.com/media/10720-tr4067.pdf',
                 'title': 'TR-4067: NFS on ONTAP Best Practices',
                 'category': 'reference_architecture',
                 'alignment': 'NFS v3/v4.1 tuning, mount options, pNFS, VMware NFS datastores',
                 'condition': 'nfs'},
                {'url': 'https://www.netapp.com/media/16423-tr-4515.pdf',
                 'title': 'TR-4515: ONTAP AFF All-SAN Array Systems',
                 'category': 'reference_architecture',
                 'alignment': 'AFF/ASA SAN design: FC, iSCSI, NVMe/FC, multipathing, ALUA',
                 'condition': 'fc_san'},
                {'url': 'https://www.netapp.com/media/85481-tr-4929.pdf',
                 'title': 'TR-4929: FlexPod Datacenter with Cisco UCS',
                 'category': 'reference_architecture',
                 'alignment': 'FlexPod DC reference architecture: Cisco UCS X-Series + AFF A-Series + Nexus 9000',
                 'condition': 'flexpod'},
                {'url': 'https://www.netapp.com/media/21702-tr-4616.pdf',
                 'title': 'TR-4616: NFS Kerberos in ONTAP',
                 'category': 'reference_architecture',
                 'alignment': 'NFS Kerberos krb5p in-flight encryption, Microsoft AD integration, mutual authentication',
                 'condition': None},
                {'url': 'https://www.netapp.com/media/17229-tr4571.pdf',
                 'title': 'TR-4571: FlexPod Solution Architecture',
                 'category': 'reference_architecture',
                 'alignment': 'End-to-end FlexPod architectural deep-dive: compute, network, storage tiers',
                 'condition': 'flexpod'},
                {'url': 'https://www.netapp.com/media/7334-tr4613.pdf',
                 'title': 'TR-4613: NVMe/FC SAN Host Configuration',
                 'category': 'reference_architecture',
                 'alignment': 'NVMe/FC host setup for Linux, Windows, ESXi — multipath, queues, tuning',
                 'condition': 'nvme'},
                {'url': 'https://www.netapp.com/media/17068-tr4733.pdf',
                 'title': 'TR-4733: SnapMirror Business Continuity',
                 'category': 'reference_architecture',
                 'alignment': 'SM-BC/Active Sync zero-RPO design, Mediator deployment, application failover',
                 'condition': 'snapmirror'},
                {'url': 'https://docs.netapp.com/us-en/ontap/san-admin/san-host-reporting-concept.html',
                 'title': 'ONTAP SAN Host Reporting & Alignment Guide',
                 'category': 'reference_architecture',
                 'alignment': 'SAN host configuration verification, LUN alignment, SCSI timeout tuning',
                 'condition': 'fc_san'},
                {'url': 'https://www.netapp.com/media/10680-tr4614.pdf',
                 'title': 'TR-4614: SAP HANA Backup & Recovery with SnapCenter',
                 'category': 'reference_architecture',
                 'alignment': 'SAP HANA SnapCenter backup, HANA Studio integration, file-based and snapshot-based backup',
                 'condition': None},
                {'url': 'https://www.netapp.com/media/17009-tr4668.pdf',
                 'title': 'TR-4668: Oracle Database Deployment on ONTAP',
                 'category': 'reference_architecture',
                 'alignment': 'Oracle NVA: dNFS, ASM, RAC, RMAN, SnapCenter — validated architecture',
                 'condition': None},
                {'url': 'https://www.netapp.com/media/8585-tr4590.pdf',
                 'title': 'TR-4590: Microsoft SQL Server on ONTAP',
                 'category': 'reference_architecture',
                 'alignment': 'SQL Server NVA: iSCSI/SMB, Always On AG, SnapCenter, tempdb tuning',
                 'condition': None},
                {'url': 'https://docs.netapp.com/us-en/ontap-apps-dbs/sap-hana/sap-hana-overview.html',
                 'title': 'SAP HANA on ONTAP Best Practices (NVA)',
                 'category': 'reference_architecture',
                 'alignment': 'SAP HANA TDI certified, NFS/FC, data tiering, backup with SnapCenter',
                 'condition': None},

                # AI/ML/DL Reference Architectures
                {'url': 'https://www.netapp.com/artificial-intelligence/',
                 'title': 'NetApp AI Solutions — NVIDIA DGX + ONTAP',
                 'category': 'reference_architecture',
                 'alignment': 'NVIDIA DGX SuperPOD + AFF A900/A90/A1K, BeeGFS on E-Series, AI/ML data pipelines',
                 'condition': None},
                {'url': 'https://docs.netapp.com/us-en/netapp-solutions/ai/index.html',
                 'title': 'NetApp AI Solutions Documentation',
                 'category': 'reference_architecture',
                 'alignment': 'NVA for AI/ML: NVIDIA DGX, MLOps, data lakehouse, Domino Data Lab',
                 'condition': None},

                # Industry-Specific Validated Designs
                {'url': 'https://www.netapp.com/solutions/healthcare/',
                 'title': 'NetApp Healthcare Solutions (Epic, Cerner, Imaging)',
                 'category': 'reference_architecture',
                 'alignment': 'Healthcare NVA: Epic EHR, medical imaging (DICOM), HIPAA compliance, FlexPod for Healthcare',
                 'condition': None},
                {'url': 'https://www.netapp.com/solutions/financial-services/',
                 'title': 'NetApp Financial Services Solutions',
                 'category': 'reference_architecture',
                 'alignment': 'Low-latency trading, regulatory compliance (SEC 17a-4), SnapLock WORM',
                 'condition': None},

                # Automation & Infrastructure-as-Code
                {'url': 'https://docs.netapp.com/us-en/ontap-automation/migrate/mapping.html',
                 'title': 'ONTAP Automation Toolkit — Ansible, Terraform, PowerShell',
                 'category': 'reference_architecture',
                 'alignment': 'NetApp-certified Ansible modules (na_ontap_*), Terraform provider, PowerShell Toolkit 9.x',
                 'condition': None},
                {'url': 'https://galaxy.ansible.com/netapp/ontap',
                 'title': 'NetApp ONTAP Ansible Collection (Ansible Galaxy)',
                 'category': 'reference_architecture',
                 'alignment': 'Certified Ansible modules for ONTAP provisioning, SVM, LIF, volume, snapshot automation',
                 'condition': None},
                {'url': 'https://registry.terraform.io/providers/NetApp/netapp-ontap/latest/docs',
                 'title': 'NetApp ONTAP Terraform Provider',
                 'category': 'reference_architecture',
                 'alignment': 'Infrastructure-as-code: declarative ONTAP resource management via Terraform',
                 'condition': None},

                # BlueXP Services (SaaS management layer)
                {'url': 'https://docs.netapp.com/us-en/bluexp-ransomware-protection/index.html',
                 'title': 'BlueXP Ransomware Protection',
                 'category': 'reference_architecture',
                 'alignment': 'SaaS-based ransomware dashboard: ARP status, backup readiness, workload risk scoring',
                 'condition': None},
                {'url': 'https://docs.netapp.com/us-en/bluexp-classification/index.html',
                 'title': 'BlueXP Classification (Data Sense)',
                 'category': 'reference_architecture',
                 'alignment': 'AI-driven data discovery, PII/PHI scanning, GDPR/HIPAA compliance automation',
                 'condition': None},
                {'url': 'https://docs.netapp.com/us-en/bluexp-tiering/index.html',
                 'title': 'BlueXP Tiering (FabricPool Management)',
                 'category': 'reference_architecture',
                 'alignment': 'Policy-driven cold data tiering to S3/Azure Blob/GCS, capacity savings dashboard',
                 'condition': 'fabricpool'},
                {'url': 'https://docs.netapp.com/us-en/bluexp-disaster-recovery/index.html',
                 'title': 'BlueXP Disaster Recovery',
                 'category': 'reference_architecture',
                 'alignment': 'VMware DR orchestration via SnapMirror, automated failover/failback runbooks',
                 'condition': 'vmware'},
                {'url': 'https://docs.netapp.com/us-en/bluexp-backup-recovery/index.html',
                 'title': 'BlueXP Backup & Recovery',
                 'category': 'reference_architecture',
                 'alignment': 'Policy-based cloud backup for ONTAP volumes, 3-2-1 rule automation',
                 'condition': None},

                # Keystone STaaS
                {'url': 'https://docs.netapp.com/us-en/keystone/',
                 'title': 'NetApp Keystone STaaS — Subscription Storage',
                 'category': 'reference_architecture',
                 'alignment': 'Subscription-based opex storage: AFF/FAS/ASA/AFX/CVO, usage-based billing, SLA-guaranteed',
                 'condition': None},

                # Nutanix AHV (Early Access)
                {'url': 'https://docs.netapp.com/us-en/ontap/san-admin/index.html',
                 'title': 'Nutanix AHV with ONTAP (Early Access — Q3 2026 GA target)',
                 'category': 'reference_architecture',
                 'alignment': 'Nutanix AHV + AFF all-flash A-series: iSCSI SAN integration (Early Access, GA targeted Q3 2026)',
                 'condition': 'nutanix'},
            ]

            # ── Fetch and persist vendor guideline articles ──
            for source in VENDOR_GUIDELINE_SOURCES:
                doc_url = source['url']
                if doc_url in existing_urls:
                    continue

                # Conditional fetch: only pull if fleet signal is detected (or unconditional)
                condition = source.get('condition')
                if condition and not fleet_signals.get(condition, False):
                    continue

                # Build article entry — lightweight: we store the URL and metadata,
                # not the full page content (same pattern as existing KB articles)
                new_articles.append({
                    'url': doc_url,
                    'title': source['title'],
                    'source': 'vendor-docs' if condition else 'docs.netapp.com',
                    'category': source['category'],
                    'alignment': source.get('alignment', ''),
                    'relevance': f'Fleet integration: {condition}' if condition else 'Core NetApp best practice',
                    'discoveredAt': datetime.now(timezone.utc).isoformat()[:10],
                    '_vendorGuideline': True,
                    '_fleetRelevant': bool(condition),
                    '_integrationKey': condition or 'core',
                })
                existing_urls.add(doc_url)
                vendor_articles_added += 1

            # ── Vendor page title enrichment (scrape titles for new articles) ──
            # For articles that were just added, attempt to fetch actual page
            # titles from the vendor sites to improve KB display quality.
            vendor_scrape_count = 0
            vendor_scrape_errors = 0
            for article in new_articles:
                if not article.get('_vendorGuideline'):
                    continue
                if vendor_scrape_count >= 40:  # rate limit: max 40 vendor fetches per scan cycle
                    break
                try:
                    text, err = _enrich_fetch(article['url'], timeout=10)
                    vendor_scrape_count += 1
                    if text and not err:
                        # Extract <title> tag
                        title_match = _re.search(r'<title[^>]*>([^<]{5,200})</title>', text, _re.IGNORECASE)
                        if title_match:
                            scraped_title = html.unescape(title_match.group(1)).strip()
                            # Clean up common suffixes
                            for suffix in [' — NetApp', ' | NetApp', ' - NetApp', ' — Cisco', ' | Cisco',
                                           ' - Broadcom', ' | Broadcom', ' - VMware', ' | VMware',
                                           ' - Veeam', ' | Veeam', ' — docs.netapp.com',
                                           ' — Oracle', ' - Oracle', ' | Oracle',
                                           ' | Microsoft Learn', ' - Microsoft Learn',
                                           ' :: NetApp', ' — HYCU', ' | Rubrik']:
                                if scraped_title.endswith(suffix):
                                    scraped_title = scraped_title[:-len(suffix)].strip()
                            if len(scraped_title) > 10:
                                article['_scrapedTitle'] = scraped_title

                        # Extract key configuration directives/version numbers
                        # Look for version patterns, CLI commands, requirements
                        config_hints = []
                        ver_matches = _re.findall(
                            r'(?:version|requires?|minimum|recommended|supported)[:\s]+([0-9]+\.[0-9]+(?:\.[0-9]+)?(?:P[0-9]+)?)',
                            text, _re.IGNORECASE
                        )
                        if ver_matches:
                            config_hints.extend([f'Version: {v}' for v in set(ver_matches[:5])])

                        cmd_matches = _re.findall(
                            r'(?:run|execute|configure|command)[:\s]*[`"]([a-z][a-z0-9 \-_]{10,80})[`"]',
                            text, _re.IGNORECASE
                        )
                        if cmd_matches:
                            config_hints.extend([f'CLI: {c.strip()}' for c in cmd_matches[:3]])

                        if config_hints:
                            article['_configHints'] = config_hints[:5]

                    else:
                        vendor_scrape_errors += 1
                    time.sleep(1.5)  # polite rate limit for vendor sites
                except Exception:
                    vendor_scrape_errors += 1

            # ── Gap Analysis: detect uncovered integrations ──
            # Identify integrations that are likely in use but have no
            # corresponding vendor documentation or NetApp best practice guide.
            gap_signals = []
            # Common backup vendors not explicitly detected but likely present
            backup_signals = ['veeam', 'commvault', 'rubrik', 'cohesity', 'hycu', 'veritas']
            if fleet_signals.get('snapmirror') and not any(fleet_signals.get(b) for b in backup_signals):
                gap_signals.append({
                    'type': 'backup_gap',
                    'message': 'SnapMirror active but no 3rd party backup vendor detected — verify backup strategy covers application-consistent protection',
                    'recommendation': 'Consider SnapCenter for application-consistent snapshots, or integrate Veeam/Commvault/Rubrik for comprehensive backup'
                })

            if fleet_signals.get('smb_cifs') and not fleet_signals.get('hyperv'):
                gap_signals.append({
                    'type': 'smb_gap',
                    'message': 'SMB/CIFS protocol in use — verify Windows host configuration aligns with ONTAP SMB best practices',
                    'recommendation': 'Review ODX offload settings, SMB 3.0 encryption, and Kerberos AES compliance'
                })

            if fleet_signals.get('fc_san') and not fleet_signals.get('cisco_san') and not fleet_signals.get('brocade_fc'):
                gap_signals.append({
                    'type': 'fc_switch_gap',
                    'message': 'FC SAN protocol detected but no switch vendor identified — verify switch firmware alignment with NetApp IMT',
                    'recommendation': 'Cross-reference switch firmware against REFERENCE_LIBRARY_FIRMWARE_BASELINES'
                })

            if fleet_signals.get('nfs') and not fleet_signals.get('vmware') and not fleet_signals.get('kvm_linux'):
                gap_signals.append({
                    'type': 'nfs_host_gap',
                    'message': 'NFS protocol active but host platform not detected — verify NFS mount options and host utility versions',
                    'recommendation': 'Install NetApp Host Utilities, configure recommended mount options (rsize/wsize=1048576, hard,nointr)'
                })

            if not fleet_signals.get('arp') and any(fleet_signals.get(p) for p in ['nfs', 'smb_cifs']):
                gap_signals.append({
                    'type': 'security_gap',
                    'message': 'NAS protocols active but ARP (Anti-Ransomware Protection) not detected — security gap',
                    'recommendation': 'Enable ARP on NAS volumes (9.10.1+ FlexVol, 9.13.1+ FlexGroup, 9.16.1+ ARP/AI)'
                })

            # ── Integration version alignment gaps ──
            # Check if fleet ONTAP versions meet minimum requirements for detected integrations
            integration_version_reqs = {
                'vmware':     {'tool': 'ONTAP Tools for VMware (OTV)', 'minOntap': '9.12', 'recommended': '10.3'},
                'kubernetes': {'tool': 'Astra Trident', 'minOntap': '9.8', 'recommended': '26.06'},
                'snapcenter': {'tool': 'SnapCenter', 'minOntap': '9.12', 'recommended': '6.2.2'},
                'veeam':      {'tool': 'Veeam VBR + NetApp Plugin', 'minOntap': '9.8', 'recommended': '12.3'},
                'commvault':  {'tool': 'Commvault IntelliSnap', 'minOntap': '9.10', 'recommended': '2024'},
                'oracle_db':  {'tool': 'SnapCenter for Oracle', 'minOntap': '9.12', 'recommended': '6.2'},
                'mssql':      {'tool': 'SnapCenter for SQL Server', 'minOntap': '9.12', 'recommended': '6.2'},
                'sap_hana':   {'tool': 'SnapCenter for SAP HANA', 'minOntap': '9.12', 'recommended': '6.2'},
                'cisco_san':  {'tool': 'Cisco NX-OS (cluster/SAN switch)', 'minOntap': '9.8', 'recommended': 'NX-OS 10.4.2'},
                'brocade_fc': {'tool': 'Brocade Fabric OS (FC switch)', 'minOntap': '9.8', 'recommended': 'FOS 9.2.1'},
                'rubrik':     {'tool': 'Rubrik NAS Direct Archive', 'minOntap': '9.5', 'recommended': 'latest'},
                'cohesity':   {'tool': 'Cohesity DataProtect', 'minOntap': '9.5', 'recommended': 'latest'},
                'hycu':       {'tool': 'HYCU for ONTAP', 'minOntap': '9.8', 'recommended': 'latest'},
            }

            for signal_key, req in integration_version_reqs.items():
                if not fleet_signals.get(signal_key):
                    continue
                req_major = float(req['minOntap'])
                fleet_below = False
                below_system = ''
                below_ver = ''
                for sys_item in fleet_systems:
                    os_ver = sys_item.get('osVersion', '')
                    if not os_ver:
                        continue
                    ver_match = _re.match(r'(\d+\.\d+)', os_ver)
                    if not ver_match:
                        continue
                    ver_num = float(ver_match.group(1))
                    if ver_num < req_major:
                        fleet_below = True
                        below_system = sys_item.get('hostname') or sys_item.get('serialNumber') or 'unknown'
                        below_ver = os_ver
                        break
                if fleet_below:
                    gap_signals.append({
                        'type': f'imt_version_gap_{signal_key}',
                        'message': f'{req["tool"]} v{req["recommended"]} requires minimum ONTAP {req["minOntap"]} — system {below_system} is running ONTAP {below_ver}',
                        'recommendation': f'Upgrade ONTAP to {req["minOntap"]}+ or verify compatibility of an older {req["tool"]} version in the NetApp IMT (imt.netapp.com)',
                    })

            if gap_signals:
                for gap in gap_signals:
                    new_articles.append({
                        'url': f'https://docs.netapp.com/us-en/ontap/{gap["type"]}-gap',
                        'title': f'⚠ Gap Detected: {gap["message"][:80]}',
                        'source': 'gap-analysis',
                        'category': 'gap_analysis',
                        'alignment': gap['recommendation'],
                        'relevance': 'Fleet gap analysis',
                        'discoveredAt': datetime.now(timezone.utc).isoformat()[:10],
                        '_vendorGuideline': True,
                        '_gapAnalysis': True,
                        '_fleetRelevant': True,
                        '_integrationKey': gap['type'],
                    })

            # ── Version-specific NetApp feature mapping ──
            # Map detected ONTAP versions to key features, enhancements, and
            # configuration changes introduced in each release.
            ontap_feature_map = {
                '9.19': [
                    ('SnapMirror active sync transparent failover for AIX', 'data_protection', 'Requires ONTAP Mediator 1.12: mediator show'),
                    ('Tamperproof snapshot locking for SnapMirror Synchronous', 'data_protection', 'Enable: snapmirror modify -destination-path <path> -is-lock-enabled true'),
                    ('ASA r2 direct-attach FC (switchless)', 'configuration', 'No FC switch required for 2-node ASA r2 HA pairs — verify cabling with Hardware Universe'),
                    ('ARP/AI within SnapMirror active sync relationships', 'security', 'Verify ARP/AI status on both source and destination: security anti-ransomware volume show'),
                    ('AFX global deduplication across SAZ', 'configuration', 'Enabled by default on AFX — verify: storage aggregate show -fields dedupe-enabled'),
                    ('S3 idle connection timeout reduced 20min to 5min', 'configuration', 'Update S3 client timeout settings if applications rely on long-lived idle connections'),
                ],
                '9.18': [
                    ('SnapMirror cloud for MetroCluster FlexGroup volumes', 'data_protection', 'Enable: snapmirror create -type XDP -source-path <svm:vol> -destination-path <cloud-target>'),
                    ('100Gbps ISL minimum for high-speed MC-IP platforms', 'configuration', 'Verify ISL bandwidth: metrocluster interconnect show — must be 100Gbps for A70/A90/A1K'),
                    ('AFX ATM performance-aware balancing', 'configuration', 'ATM now balances by node load, not just volume count — monitor: storage aggregate show -fields atm-status'),
                    ('FlexCache/SnapMirror interop between AFX and Unified ONTAP', 'configuration', 'Unified ONTAP side must be 9.16.1+ for FlexCache/SnapMirror with AFX nodes'),
                    ('Controller replace combos for MC-IP (A70→A90, FAS70→FAS90)', 'operations', 'Use: system controller replace start — NDU controller upgrade in MetroCluster IP'),
                ],
                '9.17': [
                    ('AFX platform GA — minimum ONTAP for AFX 1K and AFX 2K', 'configuration', 'AFX requires 9.17.1+, REST-only API (no ZAPI), NX224 shelves with NSM140 only'),
                    ('Zero Copy Volume Move (ZCVM) for AFX', 'operations', 'Metadata-only volume relocation — triggered on failover/node events: volume move show'),
                    ('JIT privilege elevation for RBAC', 'security', 'Just-in-time admin access: security login role create -role <name> -cmddirname <cmd> -access all -query -jit-elevation true'),
                    ('MetroCluster IP E2E encryption extended to full lineup', 'security', 'Enable: metrocluster modify -is-encryption-enabled true — covers A20/A30/C30/A50/C60/A70/A90/A1K/C80, FAS50/70/90'),
                ],
                '9.16': [
                    ('ARP/AI zero-learning ML ransomware detection', 'security', 'Enable on all NAS volumes: security anti-ransomware volume enable -vserver <svm> -volume <vol> -state active'),
                    ('TLS 1.3 for S3, SnapMirror, FabricPool', 'security', 'SSLv3/TLS 1.0/1.1 disabled — verify client compatibility: security ssl show'),
                    ('NVMe/TCP UNMAP/TRIM default enabled', 'configuration', 'Verify host HBA UNMAP/TRIM support before upgrading SAN hosts: lun show -fields space-allocation'),
                    ('MAV expanded to Consistency Groups, VScan, ARP, LUN delete, NVMe', 'security', 'Review MAV rule coverage: security multi-admin-verify rule show'),
                    ('IPsec hardware offload', 'security', 'Enable: security ipsec config modify -is-enabled true — hardware offload automatic on supported platforms'),
                    ('WebAuthn MFA for System Manager', 'security', 'Register FIDO2 keys: security webauthn credentials create -username <admin>'),
                    ('OAuth 2.0 Entra ID integration', 'security', 'Configure: security oauth2 client create -name <name> -issuer-uri <entra-endpoint>'),
                ],
                '9.15': [
                    ('SnapMirror active sync symmetric active/active for all-SAN', 'data_protection', 'Requires ASA or AFF SAN-only volumes — transparent failover <15s: snapmirror show -fields active-sync-status'),
                    ('NFS over TLS GA', 'security', 'Enable: vserver nfs tls interface enable -vserver <svm> -lif <lif> -certificate-name <cert>'),
                    ('MetroCluster E2E backend encryption', 'security', 'Validate switch firmware compatibility before enabling: metrocluster check run'),
                    ('3-node ROBO cluster support', 'configuration', 'Reduced node count for remote office/branch office — cluster show'),
                    ('ARP FlexGroup support', 'security', 'Extend ARP to FlexGroup: security anti-ransomware volume enable (all nodes must be 9.13.1+)'),
                ],
                '9.14': [
                    ('NVMe/TCP GA for SAN workloads', 'configuration', 'Requires NVMe-oF host driver — configure: vserver nvme subsystem create'),
                    ('CLI support for consistency groups', 'data_protection', 'Create: consistency-group create -vserver <svm> -consistency-group <name> -volume <vol1,vol2>'),
                    ('FPolicy persistent stores', 'security', 'Enable persistent store: vserver fpolicy persistent-store create -vserver <svm> -persistent-store <name> -volume <vol>'),
                    ('TSSE physical-used semantics changed', 'configuration', 'Capacity dashboards may show different values — not a data issue. Recalibrate alert thresholds.'),
                    ('Cisco Duo 2FA for SSH', 'security', 'Enable MFA: security login create -user-or-group-name <admin> -authentication-method duosecurity'),
                ],
                '9.13': [
                    ('ARP for FlexGroup volumes', 'security', 'Enable: security anti-ransomware volume enable — all cluster nodes must be 9.13.1+'),
                    ('AES Kerberos encryption DEFAULT-ON for new CIFS SVMs', 'security', 'Critical for KB5073381/CVE-2026-20833: vserver cifs security show -fields kerberos-encryption-types'),
                    ('FPolicy v2 persistent store mode', 'security', 'Buffers FPolicy events locally — prevents event loss: vserver fpolicy show -fields is-persistent-store-enabled'),
                    ('S3 object versioning', 'configuration', 'Required for Veeam immutable backup: vserver object-store-server bucket modify -bucket <name> -versioning-state enabled'),
                    ('NVMe/FC 4-node cluster support', 'configuration', 'Expanded from 2-node: vserver nvme show'),
                ],
                '9.12': [
                    ('TSSE default-on for AFF C-Series', 'configuration', 'Changes efficiency ratio reporting — verify capacity dashboards: storage aggregate show -fields efficiency-data-reduction'),
                    ('Tamper-proof audit logging default-on', 'security', 'Immutable audit log — vserver audit show -fields log-format,guaranteed-purge'),
                    ('REST API parity with ZAPI', 'automation', 'Begin migration from ZAPI to REST API: curl -X GET https://<cluster>/api/cluster'),
                    ('NVMe/FC in MetroCluster IP', 'configuration', 'Enable NVMe/FC on MC-IP: vserver nvme create -vserver <svm>'),
                ],
                '9.11': [
                    ('Multi-Admin Verification (MAV) introduced', 'security', 'Enable: security multi-admin-verify modify -approval-groups <group> -enabled true'),
                    ('Consistency groups GA in System Manager', 'data_protection', 'System Manager: Storage > Consistency Groups — create, snapshot, replicate'),
                    ('SnapMirror active sync expanded platform support', 'data_protection', 'Requires ONTAP Mediator: snapmirror mediator show'),
                ],
                '9.10': [
                    ('ARP for FlexVol NAS (30-day learning)', 'security', 'Enable per volume: security anti-ransomware volume enable -vserver <svm> -volume <vol>'),
                    ('Firewall policies DEPRECATED to LIF service policies', 'configuration', 'BREAKING: migrate before upgrade — network interface service-policy show'),
                    ('NVMe/TCP introduced', 'configuration', 'New SAN protocol: vserver nvme subsystem show'),
                    ('SnapLock+non-SnapLock coexistence on same aggregate', 'configuration', 'Mixed SnapLock: storage aggregate show -fields snaplock-type'),
                ],
                '9.9': [
                    ('SnapMirror active sync (SM-BC) GA', 'data_protection', 'Configure: snapmirror create -source-path <src> -destination-path <dst> -type automatedfailover'),
                    ('MetroCluster IP 8-node support', 'configuration', 'Expanded from 4-node: metrocluster show -fields cluster-type,node-count'),
                    ('L3 IP-routed MetroCluster backend', 'configuration', 'IP routing for MC backend: metrocluster configuration-settings network show'),
                ],
                '9.8': [
                    ('ONTAP REST API parity begins (ZAPI deprecated)', 'automation', 'Migrate scripts from ZAPI to REST: https://<cluster>/api — ZAPI removed entirely from AFX'),
                    ('SnapDiff v3 for backup integrations', 'data_protection', 'Veeam/Rubrik CFT: volume snapshot diff start -vserver <svm> -volume <vol>'),
                ],
                '9.7': [
                    ('FabricPool for all platforms', 'configuration', 'Enable cold data tiering: storage aggregate object-store config create -object-store-name <name>'),
                    ('WAFL metadata format upgrade', 'operations', 'Ensure aggregates have >15% free capacity: storage aggregate show -fields percent-used'),
                    ('TLS 1.0/1.1 disabled for management APIs', 'security', 'Verify client TLS version support: security ssl show -fields minimum-protocol'),
                ],
            }

            # ── StorageGRID version-specific feature mapping ──
            storagegrid_feature_map = {
                '12.1': [
                    ('12 TB/s aggregate throughput (400% vs 12.0)', 'performance', 'Validate network bandwidth for upgraded throughput: grid topology show'),
                    ('Global Federated Namespace up to 10EB', 'configuration', 'Cross-grid bucket federation — configure via Grid Manager: CONFIGURATION > Cross-grid federation'),
                    ('Batch operations on billions of objects', 'operations', 'S3 batch ops for lifecycle, tagging, copy — configure via Grid Manager'),
                    ('Multi-Admin Verification for StorageGRID', 'security', 'Requires approval for destructive admin operations: Grid Manager > CONFIGURATION > Access control'),
                    ('AI-agent change tracking on buckets', 'automation', 'Bucket-level change feed for AI/ML data pipelines — enable via bucket settings'),
                ],
                '12.0': [
                    ('StorageGRID 12.0 GA architecture refresh', 'operations', 'Major version upgrade — backup Grid Manager configuration before upgrading'),
                    ('Enhanced ILM rule engine', 'configuration', 'Information Lifecycle Management v2 rules — review existing policies for compatibility'),
                ],
                '11.9': [
                    ('S3 Select support for Parquet', 'configuration', 'Query objects server-side without full download — configure via bucket policy'),
                    ('Improved erasure coding profiles', 'data_protection', 'New EC 6+3 profile for improved storage efficiency with fault tolerance'),
                ],
            }

            # ── SANtricity version-specific feature mapping ──
            santricity_feature_map = {
                '12.0': [
                    ('SANtricity 12.0 GA for EF50/EF80 NVMe arrays', 'operations', 'Required for new-gen NVMe: 110+ GB/s read, 1.5PB capacity, AI/ML scratch workloads'),
                    ('NVMe-oF support expanded (NVMe/TCP, NVMe/FC, NVMe/RoCE)', 'configuration', 'Configure host-side NVMe-oF initiators: eseries cli host-port identify'),
                ],
                '11.90': [
                    ('Enhanced volume snapshots for E-Series', 'data_protection', 'Point-in-time copies: SANtricity System Manager > Storage > Snapshots'),
                    ('Improved SSD wear-leveling algorithms', 'operations', 'Monitor drive wear: SANtricity System Manager > Hardware > Drives > SSD statistics'),
                ],
                '11.80': [
                    ('E-Series REST API GA', 'automation', 'Migrate from Symbol/SMcli to REST: https://<controller>/devmgr/v2'),
                    ('Dynamic Disk Pool rebalancing', 'operations', 'Automatic capacity optimization across pool: Storage > Pools > Rebalance'),
                ],
            }

            # ── SnapCenter version-specific feature mapping ──
            snapcenter_feature_map = {
                '6.2': [
                    ('SnapCenter 6.2 with ONTAP 9.16.1+ validation', 'operations', 'Verify SnapCenter-ONTAP compatibility: Get-SmStorageConnection | Select Version'),
                    ('Enhanced Oracle RAC backup coordination', 'data_protection', 'Multi-node RAC snapshot orchestration: New-SmBackup -Resources <rac-db>'),
                    ('SQL Server Always On AG log backup improvements', 'data_protection', 'Cross-replica log coordination: New-SmBackup -Resources <ag-name> -BackupType Log'),
                ],
                '6.0': [
                    ('Linux Server support (RHEL/Oracle Linux/SLES)', 'operations', 'Install SnapCenter Server on Linux: ./InstallSnapCenter -AcceptEULA'),
                    ('Plug-in for VMware vSphere 6.x with NVMe/TCP VMFS', 'configuration', 'Deploy SnapCenter Plug-in for VMware: register-vsc -vcenter <vcenter-ip>'),
                ],
                '5.0': [
                    ('SnapCenter 5.0 — cloud-native plugin architecture', 'operations', 'Modernized plug-in framework: Get-SmHost | Select PluginVersion'),
                ],
            }

            # ── Trident version-specific feature mapping ──
            trident_feature_map = {
                '26.06': [
                    ('Trident 26.06 GA with Kubernetes 1.36 support', 'configuration', 'Upgrade: tridentctl upgrade --to 26.06 — verify: tridentctl version'),
                    ('AFX FlexGroup driver support (ontap-nas-flexgroup on AFX)', 'configuration', 'Configure AFX backend: tridentctl create backend -f afx-flexgroup-backend.json'),
                    ('GCNV NAS+SAN AutoGrow GA', 'configuration', 'Enable auto-expand for GCNV PVCs: storageClass.parameters.autoGrow=true'),
                    ('Read-only root filesystems support', 'security', 'Pod security: securityContext.readOnlyRootFilesystem: true — Trident handles mount setup'),
                ],
                '26.02': [
                    ('CVE-2026-24051 fix (PATH hijacking in OpenTelemetry-Go)', 'security', 'CRITICAL: upgrade from any version below 26.02 — tridentctl upgrade'),
                    ('Concurrency GA for Economy/SolidFire backends', 'performance', 'Parallel provisioning: tridentctl get backends -o json | grep concurrency'),
                ],
                '25.10': [
                    ('Trident Operator improvements', 'operations', 'Helm chart v25.10: helm upgrade trident netapp-trident/trident-operator'),
                ],
            }

            for major_ver in sorted(fleet_major_versions):
                features = ontap_feature_map.get(major_ver, [])
                for feat_name, feat_cat, feat_guidance in features:
                    feat_url = f'https://docs.netapp.com/us-en/ontap/release-notes/ontap-{major_ver}-features'
                    if feat_url not in existing_urls:
                        new_articles.append({
                            'url': feat_url,
                            'title': f'ONTAP {major_ver}: {feat_name}',
                            'source': 'version-features',
                            'category': feat_cat,
                            'alignment': feat_guidance,
                            'relevance': f'ONTAP {major_ver} deployed in fleet',
                            'discoveredAt': datetime.now(timezone.utc).isoformat()[:10],
                            '_vendorGuideline': True,
                            '_versionFeature': True,
                            '_fleetRelevant': True,
                            '_integrationKey': f'ontap-{major_ver}',
                        })
                        existing_urls.add(feat_url)
                        vendor_articles_added += 1

            # ── Multi-platform version feature enrichment ──
            # StorageGRID, SANtricity, SnapCenter, and Trident version features
            platform_feature_maps = [
                (storagegrid_feature_map, 'storagegrid', fleet_signals.get('storagegrid', False),
                 'https://docs.netapp.com/us-en/storagegrid/release-notes/',
                 'StorageGRID'),
                (santricity_feature_map, 'eseries', fleet_signals.get('eseries', False),
                 'https://docs.netapp.com/us-en/e-series/getting-started/',
                 'SANtricity'),
                (snapcenter_feature_map, 'snapcenter', fleet_signals.get('snapcenter', False),
                 'https://docs.netapp.com/us-en/snapcenter/release-notes/',
                 'SnapCenter'),
                (trident_feature_map, 'kubernetes', fleet_signals.get('kubernetes', False),
                 'https://docs.netapp.com/us-en/trident/trident-rn.html',
                 'Trident'),
            ]

            for feat_map, signal_key, is_detected, base_url, product_name in platform_feature_maps:
                if not is_detected:
                    continue
                for ver, features in feat_map.items():
                    for feat_name, feat_cat, feat_guidance in features:
                        feat_url = f'{base_url}#{product_name.lower()}-{ver}-features'
                        if feat_url not in existing_urls:
                            new_articles.append({
                                'url': feat_url,
                                'title': f'{product_name} {ver}: {feat_name}',
                                'source': 'version-features',
                                'category': feat_cat,
                                'alignment': feat_guidance,
                                'relevance': f'{product_name} detected in fleet',
                                'discoveredAt': datetime.now(timezone.utc).isoformat()[:10],
                                '_vendorGuideline': True,
                                '_versionFeature': True,
                                '_fleetRelevant': True,
                                '_integrationKey': f'{signal_key}-{ver}',
                            })
                            existing_urls.add(feat_url)
                            vendor_articles_added += 1

            print(f'  [ENRICH]   Vendor guidelines: +{vendor_articles_added} articles '
                  f'(scraped {vendor_scrape_count}, errors {vendor_scrape_errors})', flush=True)
            if gap_signals:
                print(f'  [ENRICH]   Gap analysis: {len(gap_signals)} coverage gaps detected', flush=True)

        else:
            print('  [ENRICH]   Fleet-aware docs: skipped (no cached fleet data)', flush=True)


        # Persist
        if new_articles:
            all_articles = kb_data.get('articles', []) + new_articles
            kb_out = {
                'version': 1,
                'lastUpdated': datetime.now(timezone.utc).isoformat()[:10],
                'articleCount': len(all_articles),
                'articles': all_articles,
            }
            KNOWLEDGE_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = KNOWLEDGE_PATH.with_suffix('.tmp')
            tmp_path.write_text(json.dumps(kb_out, indent=2, ensure_ascii=False), encoding='utf-8')
            tmp_path.replace(KNOWLEDGE_PATH)
            print(f'  [ENRICH]   Knowledge base: +{len(new_articles)} new articles ({len(all_articles)} total)', flush=True)

        return {'new': len(new_articles), 'total': len(kb_data.get('articles', [])) + len(new_articles)}

    # ── Scanner 7: Reference Library Auto-Update (EOA, IMT, Firmware) ──
    def _scan_reference_library(self):
        """Automated reference data refresh: firmware baselines, EOA database,
        IMT interop matrix, and integration version discovery.
        Uses fuzzy-matching against GitHub, PyPI, vendor docs, and endoflife.date."""
        print('  [ENRICH] [7/7] Scanning reference library (firmware + EOA + IMT)...', flush=True)
        _data_dir = os.path.join(os.path.dirname(__file__), 'data')
        changes = {}
        # ── 7a. Firmware baselines harvester ──
        try:
            import sys as _sys7
            _tools_dir = os.path.join(os.path.dirname(__file__), 'tools')
            if _tools_dir not in _sys7.path:
                _sys7.path.insert(0, _tools_dir)
            from firmware_harvester import scheduled_harvest as _fw_harvest
            fw_changes = _fw_harvest(_data_dir)
            if fw_changes:
                changes['firmware_baselines'] = fw_changes
                print(f'  [ENRICH]   Firmware baselines: {len(fw_changes)} updates', flush=True)
                for k, v in fw_changes.items():
                    print(f'    {k}: {v.get("old","")} -> {v.get("new","")}', flush=True)
            else:
                print('  [ENRICH]   Firmware baselines: up to date', flush=True)
        except Exception as _fw_err:
            print(f'  [ENRICH]   Firmware baselines harvest failed: {_fw_err}', flush=True)

        # ── 7b. Reference library harvester (EOA, IMT, advisories) ──
        try:
            from reference_harvester import scheduled_reference_harvest as _ref_harvest
            # Pass GitHub PAT from config if available
            _gh_token = ""
            try:
                _cfg_for_gh = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
                _gh_token = _cfg_for_gh.get("githubToken", "") or ""
            except Exception:
                pass
            ref_changes = _ref_harvest(_data_dir, github_token=_gh_token)
            if ref_changes:
                changes['reference_library'] = ref_changes
                _ref_summary = []
                if ref_changes.get('eoa'):
                    _ref_summary.append(f"EOA: {len(ref_changes['eoa'])} changes")
                if ref_changes.get('imt'):
                    _ref_summary.append(f"IMT: {len(ref_changes['imt'])} updates")
                if ref_changes.get('advisories'):
                    _ref_summary.append(f"Advisories: {len(ref_changes['advisories'])} new")
                if ref_changes.get('docs_discovered'):
                    _ref_summary.append(f"Docs: {ref_changes['docs_discovered']} discovered")
                print(f'  [ENRICH]   Reference library: {", ".join(_ref_summary) if _ref_summary else "up to date"}', flush=True)
            else:
                print('  [ENRICH]   Reference library: up to date', flush=True)
        except Exception as _ref_err:
            print(f'  [ENRICH]   Reference library harvest failed: {_ref_err}', flush=True)

        return changes


def _infer_affected_products(adv_id, title):
    """Heuristic: infer which products an advisory affects from its ID and title."""
    title_l = title.lower()
    products = []
    if 'ontap'      in title_l: products.append('ONTAP')
    if 'storagegrid' in title_l or 'storage grid' in title_l: products.append('StorageGRID')
    if 'snapcenter'  in title_l or 'snap center' in title_l:  products.append('SnapCenter')
    if 'trident'     in title_l: products.append('Astra Trident')
    if 'active iq'   in title_l or 'activeiq' in title_l:     products.append('Active IQ Unified Manager')
    if 'sanhost'     in title_l or 'san host' in title_l:     products.append('SAN Host Utilities')
    return products or ['ONTAP']  # default to ONTAP if nothing matched



def _parse_netapp_release_notes(text, version, platform):
    """
    Extract known issues, fixed issues, and what's-new blurbs from
    NetApp docs HTML for a given version/platform.
    Uses section-aware parsing: looks for headings like 'Known Issues',
    'Fixed Issues', "What's New", then reads the <li> items under each.
    Returns dict: {knownIssues, fixedIssues, whatsNew, upgradeMotivation}
    """
    known = []
    fixed = []
    whatsnew = []

    # Pre-strip <script>, <style>, <noscript>, <svg> blocks to prevent
    # raw JavaScript/CSS from leaking into extracted release notes.
    text = _re.sub(r'<(script|style|noscript|svg)[^>]*>.*?</\1>', '', text, flags=_re.DOTALL | _re.IGNORECASE)
    # ── Section-aware extraction ──────────────────────────────────────────────
    # Split HTML into segments by heading text so we pull issues from the right
    # section rather than from any random <li> on the page.
    def _items_under_heading(html, *heading_patterns):
        """Find text of <li> items in the section immediately after a heading."""
        pat = '|'.join(heading_patterns)
        m = _re.search(
            rf'<h[2-4][^>]*>(?:[^<]*<[^>]+>)*[^<]*(?:{pat})[^<]*(?:<[^>]+>[^<]*)*</h[2-4]>',
            html, _re.IGNORECASE
        )
        if not m:
            return []
        segment = html[m.end():m.end() + 8000]
        # Stop at next heading
        next_h = _re.search(r'<h[2-4][\s>]', segment)
        if next_h:
            segment = segment[:next_h.start()]
        items = _re.findall(r'<li[^>]*>(.*?)</li>', segment, _re.DOTALL)
        return [_strip_html_tags(i)[:300].strip() for i in items if len(_strip_html_tags(i).strip()) > 20]

    # Known issues
    known = _items_under_heading(text, r'known\s+issue', r'known\s+problem', r'known\s+limitation')[:8]
    # Fixed bugs / resolved issues
    fixed = _items_under_heading(text, r'fixed\s+bug', r'resolved\s+issue', r'bug\s+fix', r'fixed\s+issue')[:8]
    # What's new / new features
    whatsnew = _items_under_heading(text, r"what.{0,4}s\s+new", r'new\s+feature', r'enhancements?')[:5]

    # ── Fallback: scan all <li> by keyword if sections not found ─────────────
    if not known and not whatsnew:
        all_li = _re.findall(r'<li[^>]*>(.*?)</li>', text, _re.DOTALL)
        issue_kw  = ['issue', 'problem', 'bug', 'fail', 'error', 'crash', 'panic', 'incorrect', 'missing', 'not work', 'defect', 'caveat']
        feature_kw = ['support', 'introduc', 'enabl', 'improve', 'new', 'add', 'enhanc', 'increas', 'extend']
        for item in all_li[:100]:
            clean = _strip_html_tags(item)[:250].strip()
            if len(clean) < 25:
                continue
            cl = clean.lower()
            if any(k in cl for k in issue_kw) and len(known) < 6:
                known.append(clean)
            elif any(k in cl for k in feature_kw) and len(whatsnew) < 4:
                whatsnew.append(clean)

    motivation_parts = []
    if known:
        motivation_parts.append(f"{len(known)} known issue(s) documented for {version}")
    if fixed:
        motivation_parts.append(f"{len(fixed)} issue(s) fixed in this release")
    if whatsnew:
        motivation_parts.append(f"new in {version}: {whatsnew[0][:80]}")
    motivation = '. '.join(motivation_parts) or 'Check docs.netapp.com for current release status.'

    return {
        'knownIssues': known[:8],
        'fixedIssues': fixed[:8],
        'whatsNew':    whatsnew[:5],
        'upgradeMotivation': motivation
    }


def _search_netapp_psirt_for_version(version, product_keyword):
    """
    Search the NetApp PSIRT advisory list for advisories that mention
    a given software version. Scrapes security.netapp.com/advisory/ index.
    Returns list of {id, title, severity, link} dicts.
    """
    results = []
    try:
        # PSIRT search page — queries by product keyword
        search_url = f'https://security.netapp.com/advisory/?q={urllib.parse.quote(product_keyword)}'
        text, err = _enrich_fetch(search_url, timeout=15)
        if err or not text:
            return results
        # Extract advisory links + titles from the listing
        adv_matches = _re.findall(
            r'href="(/advisory/ntap-[^"]+)"[^>]*>.*?<[^>]+>([^<]{10,120})',
            text, _re.DOTALL
        )
        for path, raw_title in adv_matches[:20]:
            title = _strip_html_tags(raw_title).strip()
            # Only include if the version string or major.minor appears in the listing
            major_minor = _re.match(r'^(\d+\.\d+)', version)
            ver_str = major_minor.group(1) if major_minor else version[:5]
            if ver_str not in text:
                continue
            adv_id = path.strip('/').split('/')[-1]
            results.append({
                'id': adv_id,
                'title': title[:200],
                'link': f'https://security.netapp.com{path}',
                'severity': 'UNKNOWN'
            })
    except Exception:
        pass
    return results[:5]


# Real NVD CPE Dictionary product names for NetApp platforms — verified via a
# live query against services.nvd.nist.gov/rest/json/cpes/2.0 (2026-08-10), not
# guessed. Wrong names here would silently return zero CPE-matched results:
#   ONTAP        -> clustered_data_ontap (modern cluster-mode, matches 9.x)
#   StorageGRID  -> storagegrid
#   SANtricity   -> e-series_santricity_os_controller (232 CVEs confirmed live)
_NVD_CPE_PRODUCT = {
    'ONTAP': 'clustered_data_ontap',
    'StorageGRID': 'storagegrid',
    'SANtricity': 'e-series_santricity_os_controller',
}


def _parse_nvd_vulnerabilities(vulnerabilities):
    """Shared parser: NVD vulnerabilities[] -> [{id, description, cvss, severity, publishedDate}]."""
    parsed = []
    for item in vulnerabilities:
        vuln = item.get('cve', {})
        cve_id = vuln.get('id', '')
        if not cve_id:
            continue
        descs = vuln.get('descriptions', [])
        desc = next((d['value'] for d in descs if d.get('lang') == 'en'), '')
        metrics = vuln.get('metrics', {})
        cvss_score = None
        severity = 'UNKNOWN'
        for key in ('cvssMetricV31', 'cvssMetricV30', 'cvssMetricV2'):
            if key in metrics and metrics[key]:
                m = metrics[key][0].get('cvssData', {})
                cvss_score = m.get('baseScore')
                severity = (m.get('baseSeverity') or 'UNKNOWN').upper()
                break
        parsed.append({
            'id': cve_id,
            'description': desc[:400],
            'cvss': cvss_score,
            'severity': severity,
            'publishedDate': vuln.get('published', '')[:10],
        })
    return parsed


def _search_nvd_for_version(version, cpe_product_keyword, nvd_api_key=None):
    """
    Find CVEs affecting this platform/version. Tries a precise CPE
    (Common Platform Enumeration) match first — using NetApp's real, verified
    NVD Dictionary product names — since keywordSearch alone is a blunt
    instrument that also surfaces loosely-related historical CVEs matching
    the product name in unrelated contexts. Falls back to / supplements with
    keyword search for broader recall, deduplicated by CVE ID.
    Returns list of {id, description, cvss, severity, publishedDate} dicts.

    nvd_api_key: if not passed explicitly, read directly from aiq_config.json
    (same pattern as scan_and_persist_advisories) so existing callers benefit
    from the configured key without needing to thread it through.
    """
    if nvd_api_key is None:
        try:
            if CONFIG_PATH.exists():
                nvd_api_key = json.loads(CONFIG_PATH.read_text(encoding='utf-8')).get('nvdApiKey') or None
        except Exception:
            nvd_api_key = None
    headers = {'apiKey': nvd_api_key} if nvd_api_key else None
    by_id = {}

    # ── 1. Precise CPE match (versionless prefix — catches all versions of
    #      this product; NVD's virtualMatchString does prefix matching) ──────
    cpe_product = _NVD_CPE_PRODUCT.get(cpe_product_keyword)
    if cpe_product:
        try:
            cpe_str = urllib.parse.quote(f'cpe:2.3:*:netapp:{cpe_product}:*', safe=':*')
            url = f'https://services.nvd.nist.gov/rest/json/cves/2.0?virtualMatchString={cpe_str}&resultsPerPage=10'
            text, err = _enrich_fetch(url, timeout=20, extra_headers=headers)
            if not err and text:
                data = json.loads(text)
                for r in _parse_nvd_vulnerabilities(data.get('vulnerabilities', [])):
                    by_id[r['id']] = r
        except Exception:
            pass

    # ── 2. Keyword search (product + version) — supplements CPE match with
    #      version-specific text hits the CPE prefix match wouldn't isolate ──
    try:
        q = urllib.parse.quote(f'{cpe_product_keyword} {version}')
        url = f'https://services.nvd.nist.gov/rest/json/cves/2.0?keywordSearch={q}&resultsPerPage=10'
        text, err = _enrich_fetch(url, timeout=20, extra_headers=headers)
        if not err and text:
            data = json.loads(text)
            for r in _parse_nvd_vulnerabilities(data.get('vulnerabilities', [])):
                by_id.setdefault(r['id'], r)
    except Exception:
        pass

    return list(by_id.values())[:8]


def _search_netapp_bugs_online(version, product_keyword):
    """
    Search NetApp Bugs Online public RSS feed for bugs matching a version.
    Returns list of {id, title, description, component} dicts.
    """
    results = []
    try:
        # NetApp Bugs Online has a public search interface
        # The query format: product=ONTAP&release=X.Y&type=bug
        q = urllib.parse.quote(f'{product_keyword} {version}')
        url = f'https://mysupport.netapp.com/site/bugs-online/product/ONTAP/qosb?searchContext=&queryKeywords={q}'
        text, err = _enrich_fetch(url, timeout=15)
        if err or not text:
            return results
        # Parse bug entries — Bugs Online returns HTML with bug IDs and titles
        bug_matches = _re.findall(
            r'bug[_\-\s]?id[^>]*>([0-9]{5,10})[^<]*<.*?(?:title|summary)[^>]*>([^<]{20,300})',
            text, _re.IGNORECASE | _re.DOTALL
        )
        for bug_id, title in bug_matches[:10]:
            clean_title = _strip_html_tags(title).strip()
            if clean_title and len(clean_title) > 15:
                results.append({
                    'id':    f'Bug {bug_id}',
                    'title': clean_title[:200],
                    'link':  f'https://mysupport.netapp.com/site/bugs-online/product/ONTAP/{bug_id}'
                })
    except Exception:
        pass
    return results[:5]


def fetch_ontap_version_info(version):
    """
    Multi-source enrichment for an ONTAP version:
      1. docs.netapp.com release notes (version-specific URL)
      2. NetApp PSIRT advisories mentioning this ONTAP version
      3. NVD CVE search for ONTAP + version
      4. NetApp Bugs Online public search
    All sources are merged; any missing source fails silently.
    """
    ver_m = _re.match(r'^(\d+)\.(\d+)(?:\.(\d+))?', version)
    if not ver_m:
        return None
    major, minor = ver_m.group(1), ver_m.group(2)
    ver_slug = f'{major}-{minor}'

    result = {
        'version': version,
        'platform': 'ONTAP',
        'knownIssues': [],
        'fixedIssues': [],
        'whatsNew': [],
        'kbArticles': [],
        'upgradePath': {},
        'bestPractices': [],
        'upgradeMotivation': '',
        'relatedCVEs': [],
        'relatedAdvisories': [],
        'relatedBugs': [],
        'sources': [],
        'source_url': ''
    }

    # ── Source 1: docs.netapp.com release notes ───────────────────────────────
    doc_urls = [
        f'https://docs.netapp.com/us-en/ontap/release-notes/ontap-{ver_slug}-release-notes.html',
        f'https://docs.netapp.com/us-en/ontap/{major}-{minor}/release-notes/index.html',
    ]
    for url in doc_urls:
        text, err = _enrich_fetch(url)
        if text and not err and '<html' in text.lower():
            parsed = _parse_netapp_release_notes(text, version, 'ontap')
            result['knownIssues']  = parsed['knownIssues']
            result['fixedIssues']  = parsed['fixedIssues']
            result['whatsNew']     = parsed['whatsNew']
            result['source_url']   = url
            result['sources'].append('docs.netapp.com')
            print(f'  [ENRICH] ONTAP {version} docs: {len(parsed["knownIssues"])} issues, {len(parsed["whatsNew"])} new features', flush=True)
            break

    # ── Source 2: NetApp PSIRT advisories ────────────────────────────────────
    try:
        advisories = _search_netapp_psirt_for_version(version, 'ONTAP')
        if advisories:
            result['relatedAdvisories'] = advisories
            result['sources'].append('security.netapp.com')
            print(f'  [ENRICH] ONTAP {version} PSIRT: {len(advisories)} advisory/advisories', flush=True)
    except Exception:
        pass

    # ── Source 3: NVD CVE search ──────────────────────────────────────────────
    try:
        cves = _search_nvd_for_version(version, 'ONTAP')
        if cves:
            result['relatedCVEs'] = cves
            result['sources'].append('nvd.nist.gov')
            print(f'  [ENRICH] ONTAP {version} NVD: {len(cves)} CVE(s)', flush=True)
    except Exception:
        pass

    # ── Source 4: NetApp Bugs Online ──────────────────────────────────────────
    try:
        bugs = _search_netapp_bugs_online(version, 'ONTAP')
        if bugs:
            result['relatedBugs'] = bugs
            if 'mysupport.netapp.com' not in result['sources']:
                result['sources'].append('mysupport.netapp.com')
            print(f'  [ENRICH] ONTAP {version} Bugs Online: {len(bugs)} bug(s)', flush=True)
    except Exception:
        pass

    try:
        kbs = fetch_kb_articles(version, 'ONTAP')
        if kbs:
            result['kbArticles'] = kbs
            result['sources'].append('kb.netapp.com')
    except Exception:
        pass

    try:
        up = fetch_upgrade_path_info(version, 'ONTAP')
        if up and up.get('recommendedTarget'):
            result['upgradePath'] = up
            result['sources'].append('docs.netapp.com (upgrade)')
    except Exception:
        pass

    try:
        bps = fetch_best_practice_guides(version, 'ONTAP')
        if bps:
            result['bestPractices'] = bps
            result['sources'].append('docs.netapp.com (TRs)')
    except Exception:
        pass

    # ── Upgrade motivation: synthesise from all sources ───────────────────────
    parts = []
    if result['knownIssues']:
        parts.append(f"{len(result['knownIssues'])} known issue(s) in release notes")
    if result['relatedCVEs']:
        high = [c for c in result['relatedCVEs'] if (c.get('cvss') or 0) >= 7]
        parts.append(f"{len(result['relatedCVEs'])} CVE(s) found ({len(high)} high/critical)")
    if result['relatedAdvisories']:
        parts.append(f"{len(result['relatedAdvisories'])} PSIRT advisory/advisories")
    if result['relatedBugs']:
        parts.append(f"{len(result['relatedBugs'])} tracked bug(s)")
    if result['fixedIssues']:
        parts.append(f"{len(result['fixedIssues'])} issue(s) fixed in this release")
    if result.get('kbArticles'):
        parts.append(f"{len(result['kbArticles'])} KB article(s)")
    if result.get('upgradePath') and result['upgradePath'].get('recommendedTarget'):
        parts.append(f"Upgrade path available")
    if result.get('bestPractices'):
        parts.append(f"{len(result['bestPractices'])} best practice guide(s)")
        
    result['upgradeMotivation'] = '. '.join(parts) if parts else 'No major issues found in public sources for this version.'

    return result if result['sources'] else None


def fetch_sg_version_info(version):
    """
    Multi-source enrichment for a StorageGRID version:
      1. docs.netapp.com StorageGRID release notes
      2. NetApp PSIRT advisories mentioning StorageGRID + version
      3. NVD CVE search for StorageGRID + version
    """
    ver_m = _re.match(r'^(\d+)\.(\d+)', version)
    if not ver_m:
        return None
    major, minor = ver_m.group(1), ver_m.group(2)
    ver_slug = f'{major}{minor}'   # e.g. '119' for 11.9

    result = {
        'version': version,
        'platform': 'StorageGRID',
        'knownIssues': [],
        'fixedIssues': [],
        'whatsNew': [],
        'kbArticles': [],
        'upgradePath': {},
        'bestPractices': [],
        'upgradeMotivation': '',
        'relatedCVEs': [],
        'relatedAdvisories': [],
        'relatedBugs': [],
        'sources': [],
        'source_url': ''
    }

    # ── Source 1: docs.netapp.com ─────────────────────────────────────────────
    doc_urls = [
        f'https://docs.netapp.com/us-en/storagegrid-{ver_slug}/release-notes/index.html',
        f'https://docs.netapp.com/us-en/storagegrid-{major}-{minor}/release-notes/index.html',
    ]
    for url in doc_urls:
        text, err = _enrich_fetch(url)
        if text and not err and '<html' in text.lower():
            parsed = _parse_netapp_release_notes(text, version, 'storagegrid')
            result['knownIssues'] = parsed['knownIssues']
            result['fixedIssues'] = parsed['fixedIssues']
            result['whatsNew']    = parsed['whatsNew']
            result['source_url']  = url
            result['sources'].append('docs.netapp.com')
            print(f'  [ENRICH] StorageGRID {version} docs: {len(parsed["knownIssues"])} issues', flush=True)
            break

    # ── Source 2: PSIRT ───────────────────────────────────────────────────────
    try:
        advisories = _search_netapp_psirt_for_version(version, 'StorageGRID')
        if advisories:
            result['relatedAdvisories'] = advisories
            result['sources'].append('security.netapp.com')
    except Exception:
        pass

    # ── Source 3: NVD ────────────────────────────────────────────────────────
    try:
        cves = _search_nvd_for_version(version, 'StorageGRID')
        if cves:
            result['relatedCVEs'] = cves
            result['sources'].append('nvd.nist.gov')
    except Exception:
        pass

    try:
        kbs = fetch_kb_articles(version, 'StorageGRID')
        if kbs:
            result['kbArticles'] = kbs
            result['sources'].append('kb.netapp.com')
    except Exception:
        pass

    try:
        up = fetch_upgrade_path_info(version, 'StorageGRID')
        if up and up.get('recommendedTarget'):
            result['upgradePath'] = up
            result['sources'].append('docs.netapp.com (upgrade)')
    except Exception:
        pass

    try:
        bps = fetch_best_practice_guides(version, 'StorageGRID')
        if bps:
            result['bestPractices'] = bps
            result['sources'].append('docs.netapp.com (TRs)')
    except Exception:
        pass

    # ── Motivation ────────────────────────────────────────────────────────────
    parts = []
    if result['knownIssues']:
        parts.append(f"{len(result['knownIssues'])} known issue(s)")
    if result['relatedCVEs']:
        parts.append(f"{len(result['relatedCVEs'])} CVE(s) found via NVD")
    if result['relatedAdvisories']:
        parts.append(f"{len(result['relatedAdvisories'])} PSIRT advisory/advisories")
    if result.get('kbArticles'):
        parts.append(f"{len(result['kbArticles'])} KB article(s)")
    if result.get('upgradePath') and result['upgradePath'].get('recommendedTarget'):
        parts.append(f"Upgrade path available")
    if result.get('bestPractices'):
        parts.append(f"{len(result['bestPractices'])} best practice guide(s)")
        
    result['upgradeMotivation'] = '. '.join(parts) if parts else 'No major issues found in public sources for this version.'

    return result if result['sources'] else None


def fetch_santricity_version_info(version):
    """
    Multi-source enrichment for a SANtricity / E-Series version:
      1. docs.netapp.com SANtricity what's-new page (no per-version URL)
      2. NetApp PSIRT advisories mentioning SANtricity + version
      3. NVD CVE search for SANtricity + version
    """
    ver_m = _re.match(r'^(\d+)\.(\d+)', version)
    if not ver_m:
        return None

    result = {
        'version': version,
        'platform': 'SANtricity',
        'knownIssues': [],
        'fixedIssues': [],
        'whatsNew': [],
        'kbArticles': [],
        'upgradePath': {},
        'bestPractices': [],
        'upgradeMotivation': '',
        'relatedCVEs': [],
        'relatedAdvisories': [],
        'relatedBugs': [],
        'sources': [],
        'source_url': ''
    }

    # ── Source 1: docs.netapp.com (SANtricity what's-new is a single page) ────
    url = 'https://docs.netapp.com/us-en/e-series-santricity/whats-new.html'
    text, err = _enrich_fetch(url)
    if text and not err and '<html' in text.lower():
        # Filter the page to the section that matches our version
        ver_section_m = _re.search(
            rf'(?:<h[2-4][^>]*>[^<]*{_re.escape(version[:5])}[^<]*</h[2-4]>)(.*?)(?=<h[2-4]|\Z)',
            text, _re.DOTALL | _re.IGNORECASE
        )
        segment = ver_section_m.group(1) if ver_section_m else text
        parsed = _parse_netapp_release_notes(segment, version, 'santricity')
        result['knownIssues'] = parsed['knownIssues']
        result['fixedIssues'] = parsed['fixedIssues']
        result['whatsNew']    = parsed['whatsNew']
        result['source_url']  = url
        result['sources'].append('docs.netapp.com')
        print(f'  [ENRICH] SANtricity {version} docs: {len(parsed["knownIssues"])} issues', flush=True)

    # ── Source 2: PSIRT ───────────────────────────────────────────────────────
    try:
        advisories = _search_netapp_psirt_for_version(version, 'SANtricity')
        if advisories:
            result['relatedAdvisories'] = advisories
            result['sources'].append('security.netapp.com')
    except Exception:
        pass

    # ── Source 3: NVD ────────────────────────────────────────────────────────
    try:
        cves = _search_nvd_for_version(version, 'SANtricity')
        if cves:
            result['relatedCVEs'] = cves
            result['sources'].append('nvd.nist.gov')
    except Exception:
        pass

    try:
        kbs = fetch_kb_articles(version, 'SANtricity')
        if kbs:
            result['kbArticles'] = kbs
            result['sources'].append('kb.netapp.com')
    except Exception:
        pass

    try:
        up = fetch_upgrade_path_info(version, 'SANtricity')
        if up and up.get('recommendedTarget'):
            result['upgradePath'] = up
            result['sources'].append('docs.netapp.com (upgrade)')
    except Exception:
        pass

    try:
        bps = fetch_best_practice_guides(version, 'SANtricity')
        if bps:
            result['bestPractices'] = bps
            result['sources'].append('docs.netapp.com (TRs)')
    except Exception:
        pass

    # ── Motivation ────────────────────────────────────────────────────────────
    parts = []
    if result['knownIssues']:
        parts.append(f"{len(result['knownIssues'])} known issue(s)")
    if result['relatedCVEs']:
        parts.append(f"{len(result['relatedCVEs'])} CVE(s) found via NVD")
    if result['relatedAdvisories']:
        parts.append(f"{len(result['relatedAdvisories'])} PSIRT advisory/advisories")
    if result.get('kbArticles'):
        parts.append(f"{len(result['kbArticles'])} KB article(s)")
    if result.get('upgradePath') and result['upgradePath'].get('recommendedTarget'):
        parts.append(f"Upgrade path available")
    if result.get('bestPractices'):
        parts.append(f"{len(result['bestPractices'])} best practice guide(s)")
        
    result['upgradeMotivation'] = '. '.join(parts) if parts else 'No major issues found in public sources for this version.'

    return result if result['sources'] else None

def fetch_kb_articles(version, platform='ONTAP'):
    articles = []
    try:
        urls = []
        if platform == 'StorageGRID':
            urls.append('https://kb.netapp.com/hybrid_cloud_infrastructure/StorageGRID/')
        else:
            urls.append(f'https://kb.netapp.com/onprem/ontap/da/NAS/ONTAP_{version}_troubleshooting')
            urls.append(f'https://kb.netapp.com/?q=ONTAP+{version}+issue')
            ver_m = _re.match(r'^(\d+)\.(\d+)', version)
            if ver_m:
                urls.append(f'https://kb.netapp.com/on-prem/ontap/os/ONTAP_{ver_m.group(1)}_{ver_m.group(2)}')

        for url in urls:
            time.sleep(1.0)
            text, err = _enrich_fetch(url)
            if not text or err:
                continue
            
            matches = _re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(?:<[^>]+>)*([^<]+)(?:<[^>]+>)*</a>', text)
            for href, title in matches:
                title = title.strip()
                if not title or len(title) < 5 or title.lower() in ('home', 'login', 'search'): continue
                if href.startswith('/'):
                    href = 'https://kb.netapp.com' + href
                articles.append({
                    'id': f"kb-{len(articles)}",
                    'title': title,
                    'summary': 'Found matching KB article',
                    'remediation': 'See article for details.',
                    'url': href,
                    'category': 'Troubleshooting'
                })
                if len(articles) >= 8:
                    break
            if len(articles) >= 8:
                break
    except Exception:
        pass
    print(f"  [ENRICH] KB Articles for {platform} {version}: {len(articles)} found", flush=True)
    return articles[:8]

def fetch_upgrade_path_info(current_version, platform='ONTAP'):
    res = {
        'currentVersion': current_version,
        'recommendedTarget': '',
        'directUpgradeSupported': False,
        'prerequisites': [],
        'notes': [],
        'upgradeGuideUrl': ''
    }
    try:
        if platform == 'StorageGRID':
            url = 'https://docs.netapp.com/us-en/storagegrid/upgrade/index.html'
            ver_regex = r'1[12]\.\d+\.\d+'
        elif platform == 'SANtricity':
            url = 'https://docs.netapp.com/us-en/e-series-santricity/whats-new.html'
            ver_regex = r'1[12]\.\d+(?:\.\d+)?'
        else:
            url = 'https://docs.netapp.com/us-en/ontap/upgrade/concept_upgrade_paths.html'
            ver_regex = r'9\.\d+\.\d+'
            
        time.sleep(1.0)
        text, err = _enrich_fetch(url)
        res['upgradeGuideUrl'] = url
        if text and not err:
            ver_m = _re.match(r'^(\d+)\.(\d+)', current_version)
            if ver_m:
                maj_min = f"{ver_m.group(1)}.{ver_m.group(2)}"
                if maj_min in text:
                    res['notes'].append(f"Found upgrade path details for {maj_min}")
                    res['directUpgradeSupported'] = True
            
            versions = _re.findall(ver_regex, text)
            if versions:
                def _vkey(v):
                    p = v.split('.')
                    return tuple(int(x) if x.isdigit() else 0 for x in p)
                versions.sort(key=_vkey, reverse=True)
                # Don't recommend the current version as the target
                target = versions[0]
                cur_m = _re.match(r'^(\d+\.\d+)', current_version)
                tgt_m = _re.match(r'^(\d+\.\d+)', target)
                if cur_m and tgt_m and cur_m.group(1) != tgt_m.group(1):
                    res['recommendedTarget'] = target
                elif len(versions) > 1:
                    res['recommendedTarget'] = target
                else:
                    res['recommendedTarget'] = target
    except Exception:
        pass
    print(f"  [ENRICH] Upgrade path info for {platform} {current_version}: {'Found' if res['recommendedTarget'] else 'Not found'}", flush=True)
    return res

def fetch_best_practice_guides(version, platform='ONTAP'):
    guides = []
    try:
        urls = [
            'https://docs.netapp.com/us-en/ontap/concepts/index.html',
            'https://docs.netapp.com/us-en/ontap/security/index.html',
            'https://docs.netapp.com/us-en/ontap/performance/index.html'
        ]
        
        time.sleep(1.0)
        tr_text, err = _enrich_fetch('https://www.netapp.com/media/10720-tr4569.pdf', timeout=5)
        if not err:
            guides.append({
                'trNumber': 'TR-4569',
                'title': 'Security Hardening Guide for ONTAP 9',
                'summary': 'Best practices for securing ONTAP systems',
                'url': 'https://www.netapp.com/media/10720-tr4569.pdf',
                'relevantFeatures': ['Security', 'Hardening']
            })

        for url in urls:
            if len(guides) >= 6: break
            time.sleep(1.0)
            text, err = _enrich_fetch(url)
            if not text or err:
                continue
                
            matches = _re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(?:<[^>]+>)*([^<]+)(?:<[^>]+>)*</a>', text)
            for href, title in matches:
                title = title.strip()
                if 'best practice' in title.lower() or 'technical report' in title.lower() or ' TR' in title:
                    if href.startswith('/'):
                        href = 'https://docs.netapp.com' + href
                    guides.append({
                        'trNumber': 'TR-Unknown',
                        'title': title,
                        'summary': f"Best practice guide found on {url.split('/')[-2]}",
                        'url': href,
                        'relevantFeatures': [url.split('/')[-2].capitalize()]
                    })
                    if len(guides) >= 6:
                        break
    except Exception:
        pass
    print(f"  [ENRICH] Best practice guides for {platform} {version}: {len(guides)} found", flush=True)
    return guides[:6]

def fetch_latest_version_catalog():
    catalog = {
        'ontap': [],
        'storagegrid': [],
        'santricity': [],
        'fetchedAt': datetime.now(timezone.utc).isoformat()
    }
    def _vkey(v):
        p = v.split('.')
        return tuple(int(x) if x.isdigit() else 0 for x in p)

    # ── ONTAP: Try endoflife.date API first (structured JSON, no WAF) ──
    ontap_found = False
    try:
        time.sleep(0.5)
        eol_raw, _ = _enrich_fetch('https://endoflife.date/api/netapp-ontap.json')
        if eol_raw:
            eol_data = json.loads(eol_raw)
            if isinstance(eol_data, list) and eol_data:
                ontap_versions = []
                for entry in eol_data:
                    cycle = entry.get('cycle', '')
                    if _re.match(r'^9\.\d{1,2}\.\d+', cycle):
                        ontap_versions.append(cycle)
                if ontap_versions:
                    ontap_versions = sorted(set(ontap_versions), key=_vkey, reverse=True)
                    catalog['ontap'] = ontap_versions[:20]
                    ontap_found = True
    except Exception:
        pass

    # ── ONTAP fallback: PyPI netapp-ontap SDK releases ──
    if not ontap_found:
        try:
            time.sleep(0.5)
            pypi_raw, _ = _enrich_fetch('https://pypi.org/pypi/netapp-ontap/json')
            if pypi_raw:
                pypi_data = json.loads(pypi_raw)
                releases = pypi_data.get('releases', {})
                ontap_versions = []
                for ver in releases.keys():
                    m = _re.match(r'^(9\.\d{1,2}\.\d+)', ver)
                    if m:
                        ontap_versions.append(m.group(1))
                if ontap_versions:
                    ontap_versions = sorted(set(ontap_versions), key=_vkey, reverse=True)
                    catalog['ontap'] = ontap_versions[:20]
                    ontap_found = True
        except Exception:
            pass

    # ── ONTAP fallback: docs.netapp.com (may 403) ──
    if not ontap_found:
        try:
            time.sleep(1.0)
            ontap_text, _ = _enrich_fetch('https://docs.netapp.com/us-en/ontap/release-notes/index.html')
            if ontap_text:
                ontap_raw = _re.findall(r'\b(9\.(?:[3-9]|1[0-9])\.\d{1})\b', ontap_text)
                ontap_versions = sorted(set(ontap_raw), key=_vkey, reverse=True)
                catalog['ontap'] = ontap_versions[:20]
        except Exception:
            pass

    # ── StorageGRID: docs.netapp.com (no alternative API available) ──
    try:
        time.sleep(1.0)
        sg_text, _ = _enrich_fetch('https://docs.netapp.com/us-en/storagegrid/release-notes/index.html')
        if sg_text:
            sg_raw = _re.findall(r'\b(1[12]\.\d{1,2}(?:\.\d{1,2})?)\b', sg_text)
            sg_versions = sorted(set(v for v in sg_raw if _vkey(v)[1] < 20), key=_vkey, reverse=True)
            catalog['storagegrid'] = sg_versions[:20]
    except Exception:
        pass

    # ── SANtricity: docs.netapp.com ──
    try:
        time.sleep(1.0)
        san_text, _ = _enrich_fetch('https://docs.netapp.com/us-en/e-series-santricity/whats-new.html')
        if san_text:
            san_raw = _re.findall(r'\b(1[12]\.\d{1,2}(?:\.\d{1,2})?)\b', san_text)
            san_versions = sorted(set(v for v in san_raw if _vkey(v)[1] < 100), key=_vkey, reverse=True)
            catalog['santricity'] = san_versions[:20]
    except Exception:
        pass

    print(f"  [ENRICH] Version Catalog refreshed. ONTAP: {len(catalog['ontap'])}, SG: {len(catalog['storagegrid'])}, SAN: {len(catalog['santricity'])}", flush=True)
    return catalog



# Version types that are ALWAYS fetched in background — never block the server thread
_VERSION_ENRICH_TYPES = {'ontap-version', 'sg-version', 'santricity-version'}


def handle_enrich_request(params, db):
    """
    Main dispatcher for /api/enrich. Returns a JSON-serializable dict.

    Version enrichment (ontap-version, sg-version, santricity-version):
      Cache-only. Returns {status:'pending'} on miss — the background thread
      (_enrich_all_versions) does the actual fetching after every harvest.
      This keeps the server non-blocking (it is single-threaded).

    CVE / advisory enrichment:
      Fetches live — these are targeted NVD/PSIRT JSON calls, fast, user-initiated.

    params: dict from parse_qs (values are lists)
    db: sqlite3 connection
    """
    enrich_type = (params.get('type', [''])[0] or '').strip()
    item_id = (params.get('id', params.get('ver', ['']))[0] or '').strip()
    nvd_key = (params.get('apiKey', [''])[0] or '').strip() or None

    if not enrich_type or not item_id:
        return {'status': 'error', 'error': 'Missing type or id parameter'}

    # Sanitize: only allow safe characters in identifiers
    if not _re.match(r'^[A-Za-z0-9.:\-_/ ]+$', item_id):
        return {'status': 'error', 'error': 'Invalid id format'}

    cache_key = f'{enrich_type}:{item_id}'

    # ── Always check cache first (applies to all types) ──────────────────────
    row = db.execute(
        'SELECT result_json, fetched_at, source FROM enrich_cache WHERE cache_key = ?',
        (cache_key,)
    ).fetchone()
    if row:
        try:
            data = json.loads(row[0])
            return {'status': 'ok', 'source': row[2], 'cached': True, 'fetched_at': row[1], 'data': data}
        except Exception:
            pass  # corrupt entry — fall through

    if enrich_type in _VERSION_ENRICH_TYPES:
        # Cache miss — try a synchronous fetch as fallback so the first
        # request returns data instead of always saying 'pending'.
        # This blocks the single-threaded server for up to ~15s but only
        # happens once per version (result is cached for subsequent calls).
        data = None
        try:
            if enrich_type == 'ontap-version':
                data = fetch_ontap_version_info(item_id)
            elif enrich_type == 'sg-version':
                data = fetch_sg_version_info(item_id)
            elif enrich_type == 'santricity-version':
                data = fetch_santricity_version_info(item_id)
        except Exception as _fe:
            print(f"  [ENRICH] Sync fallback for {cache_key} failed: {_fe}", flush=True)

        if data:
            fetched_at = datetime.now(timezone.utc).isoformat()
            try:
                db.execute(
                    'INSERT OR REPLACE INTO enrich_cache (cache_key, result_json, fetched_at, source) VALUES (?, ?, ?, ?)',
                    (cache_key, json.dumps(data), fetched_at, 'docs.netapp.com')
                )
                db.commit()
            except Exception:
                pass
            return {'status': 'ok', 'source': 'docs.netapp.com', 'cached': False, 'fetched_at': fetched_at, 'data': data}

        # Fetch failed — fall back to 'pending' (background thread will retry)
        return {
            'status': 'pending',
            'message': 'Version enrichment fetch attempted but returned no data. '
                       'Background sync thread will retry.',
            'cache_key': cache_key
        }

    # ── CVE / advisory: fetch live (fast, targeted JSON endpoints) ────────────
    fetched_at = datetime.now(timezone.utc).isoformat()
    data = None
    source = 'unknown'

    if enrich_type == 'cve':
        source = 'nvd'
        data = fetch_cve_nvd(item_id, api_key=nvd_key)
    elif enrich_type == 'ntap-advisory':
        source = 'netapp-psirt'
        data = fetch_netapp_psirt(item_id)
    else:
        return {'status': 'error', 'error': f'Unknown enrich type: {enrich_type}'}

    if data is None:
        return {'status': 'error', 'source': source, 'cached': False, 'error': 'Fetch failed or no data returned'}

    # Store in cache
    try:
        db.execute(
            'INSERT OR REPLACE INTO enrich_cache (cache_key, result_json, fetched_at, source) VALUES (?, ?, ?, ?)',
            (cache_key, json.dumps(data), fetched_at, source)
        )
        db.commit()
    except Exception:
        pass

    return {'status': 'ok', 'source': source, 'cached': False, 'fetched_at': fetched_at, 'data': data}


# ─────────────────────────────────────────────────────────────────────
# HTTP Request Handler
# ─────────────────────────────────────────────────────────────────────

class ProxyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def guess_type(self, path):
        """Override to force UTF-8 charset on all text and JavaScript responses.

        Python's SimpleHTTPRequestHandler serves static files without a charset
        declaration by default.  Corporate-network browsers (and DLP/security
        proxies) may then interpret the file as ISO-8859-1, which corrupts the
        12,000+ non-ASCII Unicode characters (emoji, box-drawing dividers, etc.)
        embedded in app.js.  The resulting decode error is a SyntaxError at the
        very start of script execution — before any function definition is
        hoisted — which is why the browser reports "switchTab is not defined"
        with a blank Source field (no filename, because the script never parsed).

        Adding '; charset=utf-8' here fixes the corporate-network instance
        without touching any application logic.
        """
        ctype = super().guess_type(path)
        if not ctype:
            return ctype
        # text/* types (text/html, text/css, text/plain …)
        if ctype.startswith('text/') and 'charset' not in ctype:
            return ctype + '; charset=utf-8'
        # JavaScript — may be reported as application/javascript or text/javascript
        if ctype in ('application/javascript', 'text/javascript'):
            return ctype + '; charset=utf-8'
        return ctype

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
        elif self.path == '/api/eoa-database':
            self.handle_eoa_database_get()
        elif self.path == '/api/imt-interop':
            self.handle_imt_interop_get()
        elif self.path == '/api/reference-library/status':
            self.handle_reference_status_get()
        elif self.path == '/api/knowledge-base':
            self.handle_knowledge_base_get()
        elif self.path == '/api/enrich/status':
            self.handle_enrich_status()
        elif self.path.startswith('/api/enrich'):
            self.handle_enrich()
        elif self.path.startswith('/api/bulletins/scan'):
            self.handle_bulletins_scan()
        elif self.path.startswith('/api/bulletins'):
            self.handle_bulletins_get()
        elif self.path.startswith('/api/history/'):
            self.handle_system_history()
        elif self.path.startswith('/api/asup/imports'):
            self.handle_asup_list()
        elif self.path == '/api/asup/import':
            self.handle_asup_import()
        elif self.path == '/api/asup/customers':
            self.handle_asup_customers()
        elif self.path.startswith('/api/firmware-probe'):
            self.handle_firmware_probe()
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
        """Return sync metadata as JSON — aggregated across all configured
        accounts, plus a per-account breakdown for the Settings/Account UI."""
        db = _init_db()
        try:
            meta = _get_sync_meta(db)
            try:
                all_cached = _load_all_accounts_cached(db)
                configured_ids = {a["id"] for a in _get_accounts()} | {"default"}
                all_cached = [(acct_id, result, m) for acct_id, result, m in all_cached if acct_id in configured_ids]
                meta["accounts"] = [
                    {
                        "id": acct_id,
                        "label": m.get("accountLabel"),
                        "lastSync": m.get("harvested_at"),
                        "systemCount": m.get("system_count", 0),
                        "clusterCount": m.get("cluster_count", 0),
                        "riskCount": m.get("risk_count", 0),
                        "caseCount": m.get("case_count", 0),
                    }
                    for acct_id, _result, m in all_cached
                ]
                if all_cached:
                    meta["systemCount"] = sum(a["systemCount"] for a in meta["accounts"])
                    meta["clusterCount"] = sum(a["clusterCount"] for a in meta["accounts"])
                    meta["riskCount"] = sum(a["riskCount"] for a in meta["accounts"])
                    meta["caseCount"] = sum(a["caseCount"] for a in meta["accounts"])
                    meta["lastSync"] = max((a["lastSync"] or "" for a in meta["accounts"]), default=meta.get("lastSync")) or meta.get("lastSync")
            except Exception as _acct_meta_err:
                print(f"  [SYNC-STATUS] Per-account breakdown skipped: {_acct_meta_err}", flush=True)
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
        # Optional ?account=<id> scopes the response to one configured account
        # instead of the default merged cross-customer fleet view.
        account_id_param = params.get("account", [None])[0]
        # Support legacy single-ID query param or read all IDs from config
        param_id = params.get("watchlistId", [None])[0]
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
            ids_str = cfg.get("watchlistIds") or cfg.get("watchlist_id") or ""
            if not ids_str:
                legacy = cfg.get("watchlistId") or ""
                if legacy and legacy != "wl_prod" and not legacy.startswith("wl_"):
                    ids_str = legacy
            wl_ids = [w.strip() for w in ids_str.split(",") if w.strip()]

        except Exception:
            wl_ids = []
        # Query param overrides config (for manual/test requests)
        if param_id and param_id not in wl_ids:
            wl_ids = [param_id]

        try:
            if force:
                # Fire harvest in a background thread and return 202 immediately.
                # NEVER run _do_full_harvest() synchronously in the request handler
                # thread -- it takes ~2 min, clients time out, the resulting
                # BrokenPipeError kills the handler and crashes the server.
                scope_msg = f" ({len(wl_ids)} watchlist(s))" if wl_ids else " (all systems)"
                print(f"  [HARVEST] Force sync requested{scope_msg} -- firing background thread", flush=True)
                if not _is_syncing:
                    t = threading.Thread(target=_background_sync, daemon=True)
                    t.start()
                    print("  [HARVEST] Background harvest thread started", flush=True)
                else:
                    print("  [HARVEST] Sync already in progress -- skipping new thread", flush=True)
                # Return 202 immediately; client polls /api/sync-status for progress
                self.send_response(202)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "started",
                    "message": "Harvest running in background. Poll /api/sync-status for progress.",
                    "isSyncing": True,
                }).encode("utf-8"))
                return

            # Check cache first — merges every configured account by default;
            # ?account=<id> scopes to just one.
            db = _init_db()
            try:
                cached_result, metas = _get_merged_harvest(db, account_id_param)
            finally:
                db.close()

            if cached_result:
                # Serve cached data immediately
                last_sync = max((m.get("harvested_at") or "" for m in metas), default="unknown") or "unknown"
                sys_count = sum(m.get("system_count", 0) for m in metas)
                print(f"  [CACHE] Serving cached data ({sys_count} systems across {len(metas)} account(s), synced: {last_sync})", flush=True)

                # Inject cache metadata into response
                cached_result["_cache"] = {
                    "hit": True,
                    "lastSync": last_sync,
                    "durationMs": sum(m.get("duration_ms", 0) for m in metas),
                    "accounts": [{"id": m.get("accountId"), "label": m.get("accountLabel"),
                                  "lastSync": m.get("harvested_at"), "systemCount": m.get("system_count", 0)} for m in metas],
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

                # Also trigger version enrichment for cached systems if needed.
                # If enrichment cache is empty/stale, this populates it so version
                # intel is available immediately rather than only after a full re-sync.
                try:
                    t2 = threading.Thread(
                        target=_enrich_all_versions,
                        args=(cached_result,),
                        daemon=True
                    )
                    t2.start()
                    print("  [CACHE] Version enrichment thread started for cached data", flush=True)
                except Exception:
                    pass
                return

            # No cache -- fire background harvest and return 202
            scope_msg = f" ({len(wl_ids)} watchlist(s))" if wl_ids else " (all systems)"
            print(f"  [CACHE] No cached data -- starting background harvest{scope_msg}", flush=True)
            if not _is_syncing:
                t = threading.Thread(target=_background_sync, daemon=True)
                t.start()
            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "started",
                "message": "Initial harvest running in background. Poll /api/sync-status for progress.",
                "isSyncing": True,
                "systems": [],
                "watchlists": [],
            }).encode("utf-8"))

        except Exception as e:
            err_str = str(e)
            is_setup_error = err_str.startswith("setup_required:")
            if is_setup_error:
                # Expected first-run condition — no traceback needed
                print(f"  [HARVEST] Setup required: {err_str}", flush=True)
            else:
                import traceback
                traceback.print_exc()
                print(f"  [HARVEST] FAILED: {err_str}", flush=True)

            # On failure, try to serve stale cache if available (skip for setup errors — no cache yet)
            if not is_setup_error:
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
                            "error": err_str,
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

            # Return structured error — needsSetup flag triggers the UI setup banner
            human_msg = err_str.replace("setup_required: ", "") if is_setup_error else err_str
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "error",
                "message": human_msg,
                "needsSetup": is_setup_error,
                "systems": [],
                "watchlists": []
            }).encode("utf-8"))

    def do_POST(self):
        if self.path == '/api/app/update':
            self.handle_app_update()
        elif self.path.startswith('/api/harvest'):
            # POST /api/harvest and POST /api/harvest?force=1 both trigger harvest
            self.handle_harvest()
        elif self.path == '/api/config':
            self.handle_config_post()
        elif self.path.startswith('/api/bulletins'):
            self.handle_bulletins_post()
        elif self.path == '/api/enrich/scan':
            self.handle_enrich_scan()
        elif self.path == '/api/asup/import':
            self.handle_asup_import()
        elif self.path == '/api/asup/associate':
            self.handle_asup_associate()
        elif self.path == '/api/history/annotate':
            self.handle_history_annotate()
        elif self.path.startswith('/api/') or self.path in ('/graphql', '/api/graphql'):
            self.handle_proxy('POST')
        else:
            self.send_error(404, "Not Found")

    def do_DELETE(self):
        if self.path.startswith('/api/asup/imports'):
            self.handle_asup_delete()
        else:
            self.send_error(404, "Not Found")

    def do_PUT(self):
        if self.path.startswith('/api/'):
            self.handle_proxy('PUT')
        else:
            self.send_error(404, "Not Found")

    # ─────────────────────────────────────────────────────────────────────
    # ASUP Offline Import Handlers
    # ─────────────────────────────────────────────────────────────────────

    def _json_response(self, code, payload):
        """Helper: send JSON response."""
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def handle_asup_import(self):
        """POST /api/asup/import
        Accepts the ASUP bundle as the raw POST body.
        Headers: X-Filename, X-Customer-Name (optional)
        Returns: { ok, system, coverage, warnings, error, matchInfo }
          matchInfo: { type: 'api_synced'|'asup_import'|'new',
                       existingSystem: {...}|null,
                       existingCustomer: str, existingSite: str }
        """
        if not _ASUP_AVAILABLE:
            self._json_response(503, {"ok": False, "error": "asup_parser.py not found on server"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self._json_response(400, {"ok": False, "error": "Empty request body"})
                return
            if content_length > 600 * 1024 * 1024:
                self._json_response(413, {"ok": False, "error": "Bundle too large (600 MB limit)"})
                return

            data_bytes    = self.rfile.read(content_length)
            filename      = self.headers.get("X-Filename", "bundle.7z")
            customer_name = self.headers.get("X-Customer-Name", "").strip()

            print(f"  [ASUP] Import request: {filename} ({len(data_bytes):,} bytes) customer='{customer_name}'", flush=True)

            result = asup_parser.parse_bundle(filename, data_bytes, customer_name)

            match_info = {"type": "new", "existingSystem": None,
                          "existingCustomer": "", "existingSite": "", "existingNotes": ""}

            if result["ok"] and result.get("system"):
                system = result["system"]
                serial = system.get("serialNumber", f"ASUP-{datetime.now(timezone.utc).isoformat()[:10]}")
                now_str = datetime.now(timezone.utc).isoformat()

                db = _init_db()
                try:
                    # ── 1. Check harvest_cache (AIQ-synced systems) ──────────────────
                    cached_row = db.execute(
                        "SELECT result_json FROM harvest_cache WHERE id = 1"
                    ).fetchone()
                    if cached_row:
                        try:
                            cached = json.loads(cached_row[0])
                            for s in cached.get("systems", []):
                                if s.get("serialNumber") == serial:
                                    match_info["type"] = "api_synced"
                                    match_info["existingSystem"] = {
                                        "serialNumber":  s.get("serialNumber"),
                                        "systemName":    s.get("systemName") or s.get("clusterName"),
                                        "customerName":  s.get("customerName"),
                                        "platform":      s.get("platform"),
                                        "osVersion":     s.get("osVersion"),
                                        "clusterRawCapacityTB": s.get("clusterRawCapacityTB"),
                                    }
                                    match_info["existingCustomer"] = s.get("customerName") or ""
                                    print(f"  [ASUP] Matched serial {serial} -> AIQ system '{s.get('systemName')}'", flush=True)
                                    break
                        except Exception as me:
                            print(f"  [ASUP] harvest_cache search error: {me}", flush=True)

                    # ── 2. Check asup_imports (previous offline imports) ─────────────
                    if match_info["type"] == "new":
                        prev_row = db.execute(
                            "SELECT customer_name, site_name, notes FROM asup_imports WHERE serial_number = ?",
                            (serial,)
                        ).fetchone()
                        if prev_row:
                            match_info["type"] = "asup_import"
                            match_info["existingCustomer"] = prev_row[0] or ""
                            match_info["existingSite"]     = prev_row[1] or ""
                            match_info["existingNotes"]    = prev_row[2] or ""
                            print(f"  [ASUP] Matched serial {serial} -> previous ASUP import", flush=True)

                    # ── 3. Persist / update asup_imports ────────────────────────────
                    # Preserve existing customer/site/notes if not overriding
                    existing_assoc = db.execute(
                        "SELECT customer_name, site_name, notes FROM asup_imports WHERE serial_number = ?",
                        (serial,)
                    ).fetchone()
                    resolved_customer = (customer_name or
                                         (existing_assoc[0] if existing_assoc else None) or
                                         match_info["existingCustomer"] or
                                         system.get("customerName") or "")

                    db.execute("""
                        INSERT INTO asup_imports
                          (serial_number, system_json, coverage_json, customer_name,
                           site_name, notes, filename, imported_at, matched_serial, match_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(serial_number) DO UPDATE SET
                          system_json   = excluded.system_json,
                          coverage_json = excluded.coverage_json,
                          filename      = excluded.filename,
                          imported_at   = excluded.imported_at,
                          matched_serial = excluded.matched_serial,
                          match_type    = excluded.match_type
                    """, (
                        serial,
                        json.dumps(system, default=str),
                        json.dumps(result.get("coverage", {}), default=str),
                        resolved_customer,
                        existing_assoc[1] if existing_assoc else "",
                        existing_assoc[2] if existing_assoc else "",
                        filename,
                        now_str,
                        serial if match_info["type"] == "api_synced" else "",
                        match_info["type"],
                    ))
                    db.commit()
                    system["customerName"] = resolved_customer
                    print(f"  [ASUP] Persisted: serial={serial}, match={match_info['type']}, customer={resolved_customer}", flush=True)

                finally:
                    db.close()

            result["matchInfo"] = match_info
            self._json_response(200 if result["ok"] else 422, result)

        except Exception as e:
            print(f"  [ASUP] Import error: {e}", flush=True)
            self._json_response(500, {"ok": False, "error": str(e), "system": None,
                                      "coverage": {}, "warnings": [], "matchInfo": {}})

    def handle_system_history(self):
        """GET /api/history/<serialNumber>[?days=400] — dated trend snapshots
        for one system (week/month/quarter/year-over-year comparison)."""
        try:
            from urllib.parse import urlparse, parse_qs, unquote
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            serial = unquote(parsed.path[len('/api/history/'):].strip('/'))
            days = int((params.get('days') or ['400'])[0])
            if not serial:
                self._json_response(400, {"ok": False, "error": "serial number required"})
                return
            db = _init_db()
            try:
                history = _get_system_history(db, serial, days=days)
            finally:
                db.close()
            self._json_response(200, {"ok": True, "serialNumber": serial, "history": history, "count": len(history)})
        except Exception as e:
            print(f"  [HISTORY] Error: {e}", flush=True)
            self._json_response(500, {"ok": False, "error": str(e), "history": []})

    def handle_history_annotate(self):
        """POST /api/history/annotate
        Body: { entries: [{ serialNumber, adoptionScorePct }, ...] }

        Adoption score is a derived value computed by a checklist formula
        that lives client-side (computeFeatureAdoptionScore() in app.js) --
        deliberately NOT duplicated in Python, since this codebase already
        had a real bug once (three different health-grade formulas giving
        the same account different letter grades depending on which
        deliverable was opened). Rather than re-derive the score here from
        raw fields and risk a second divergent formula, the client computes
        it once and annotates it onto TODAY's already-captured snapshot row.
        Only updates a row that already exists (created by the day's
        harvest) -- never creates a new snapshot from this endpoint, so a
        client bug here can't fabricate history that didn't happen.
        """
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length).decode("utf-8"))
            entries = body.get("entries") or []
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            db = _init_db()
            updated = 0
            try:
                for e in entries:
                    serial = (e.get("serialNumber") or "").strip()
                    pct = e.get("adoptionScorePct")
                    if not serial or pct is None:
                        continue
                    row = db.execute(
                        "SELECT snapshot_json FROM system_snapshots WHERE serial_number = ? AND snapshot_date = ?",
                        (serial, today)
                    ).fetchone()
                    if not row:
                        continue
                    try:
                        snap = json.loads(row[0])
                    except Exception:
                        continue
                    snap["adoptionScorePct"] = pct
                    db.execute(
                        "UPDATE system_snapshots SET snapshot_json = ? WHERE serial_number = ? AND snapshot_date = ?",
                        (json.dumps(snap), serial, today)
                    )
                    updated += 1
                db.commit()
            finally:
                db.close()
            self._json_response(200, {"ok": True, "updated": updated})
        except Exception as e:
            print(f"  [HISTORY] Annotate error: {e}", flush=True)
            self._json_response(500, {"ok": False, "error": str(e)})

    def handle_asup_list(self):
        """GET /api/asup/imports — return list of all imported ASUP systems."""
        try:
            db = _init_db()
            try:
                rows = db.execute(
                    "SELECT serial_number, system_json, coverage_json, customer_name, site_name, notes, filename, imported_at, matched_serial, match_type FROM asup_imports ORDER BY imported_at DESC"
                ).fetchall()
            finally:
                db.close()

            imports = []
            for row in rows:
                try:
                    system   = json.loads(row[1])
                    coverage = json.loads(row[2])
                    imports.append({
                        "serialNumber":  row[0],
                        "customerName":  row[3],
                        "siteName":      row[4] or "",
                        "notes":         row[5] or "",
                        "filename":      row[6],
                        "importedAt":    row[7],
                        "matchedSerial": row[8] or "",
                        "matchType":     row[9] or "new",
                        "system":        system,
                        "coverage":      coverage,
                    })
                except Exception:
                    pass

            self._json_response(200, {"ok": True, "imports": imports, "count": len(imports)})

        except Exception as e:
            print(f"  [ASUP] List error: {e}", flush=True)
            self._json_response(500, {"ok": False, "error": str(e), "imports": []})

    def handle_asup_associate(self):
        """POST /api/asup/associate
        Body: { serial, customerName, siteName, notes }
        Updates asup_imports with the association details.
        If the serial matches an AIQ-synced system (match_type='api_synced'),
        also patches the harvest_cache result_json to update that system's
        customerName, siteName, and notes fields.
        Returns: { ok, serial, matchType, merged }
        """
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length).decode("utf-8"))
            serial        = (body.get("serial") or "").strip()
            customer_name = (body.get("customerName") or "").strip()
            site_name     = (body.get("siteName") or "").strip()
            notes         = (body.get("notes") or "").strip()

            if not serial:
                self._json_response(400, {"ok": False, "error": "serial required"})
                return

            db = _init_db()
            merged_into_harvest = False
            try:
                # Update asup_imports association
                db.execute("""
                    UPDATE asup_imports
                    SET customer_name = ?, site_name = ?, notes = ?
                    WHERE serial_number = ?
                """, (customer_name, site_name, notes, serial))

                # Also update the system_json inside asup_imports to reflect the new customer
                row = db.execute(
                    "SELECT system_json, match_type FROM asup_imports WHERE serial_number = ?", (serial,)
                ).fetchone()
                if row:
                    try:
                        sys_dict = json.loads(row[0])
                        sys_dict["customerName"] = customer_name
                        sys_dict["_siteName"]    = site_name
                        sys_dict["_notes"]       = notes
                        db.execute(
                            "UPDATE asup_imports SET system_json = ? WHERE serial_number = ?",
                            (json.dumps(sys_dict, default=str), serial)
                        )
                    except Exception:
                        pass
                    match_type = row[1] or "new"

                    # If this serial is matched to an AIQ-synced system, patch harvest_cache too
                    if match_type == "api_synced":
                        cached_row = db.execute(
                            "SELECT result_json FROM harvest_cache WHERE id = 1"
                        ).fetchone()
                        if cached_row:
                            try:
                                cached = json.loads(cached_row[0])
                                changed = False
                                for s in cached.get("systems", []):
                                    if s.get("serialNumber") == serial:
                                        # Patch with ASUP-provided data — fill nulls only for critical fields
                                        asup_sys = sys_dict
                                        for field in ["osVersion", "platform", "nodeCount",
                                                       "clusterRawCapacityTB", "clusterUsableCapacityTB",
                                                       "clusterPhysicalUsedTB", "isHAConfigured",
                                                       "snapMirrorCount", "asupStatus", "asupTransport"]:
                                            if (s.get(field) is None or s.get(field) == "") and asup_sys.get(field) is not None:
                                                s[field] = asup_sys[field]
                                        # Always update customer/site from association
                                        if customer_name:
                                            s["customerName"] = customer_name
                                        s["_asupImported"]  = True
                                        s["_asupFilename"]  = asup_sys.get("_asupFilename", "")
                                        s["_asupImportedAt"]= asup_sys.get("_importedAt", "")
                                        s["_siteName"]      = site_name
                                        s["_notes"]         = notes
                                        changed = True
                                        break
                                if changed:
                                    db.execute(
                                        "UPDATE harvest_cache SET result_json = ? WHERE id = 1",
                                        (json.dumps(cached, default=str),)
                                    )
                                    merged_into_harvest = True
                                    print(f"  [ASUP] Merged serial {serial} into harvest_cache", flush=True)
                            except Exception as me:
                                print(f"  [ASUP] harvest_cache merge error: {me}", flush=True)

                db.commit()
                print(f"  [ASUP] Association saved: serial={serial}, customer={customer_name}, site={site_name}", flush=True)

            finally:
                db.close()

            self._json_response(200, {
                "ok": True, "serial": serial,
                "customerName": customer_name, "siteName": site_name,
                "merged": merged_into_harvest,
            })

        except Exception as e:
            print(f"  [ASUP] Associate error: {e}", flush=True)
            self._json_response(500, {"ok": False, "error": str(e)})

    def handle_asup_customers(self):
        """GET /api/asup/customers — return unique customer names and sites for dropdowns."""
        try:
            customers = set()
            sites     = set()
            db = _init_db()
            try:
                # From harvest_cache
                cached_row = db.execute("SELECT result_json FROM harvest_cache WHERE id = 1").fetchone()
                if cached_row:
                    try:
                        for s in json.loads(cached_row[0]).get("systems", []):
                            c = s.get("customerName") or ""
                            if c: customers.add(c)
                    except Exception:
                        pass
                # From asup_imports
                for row in db.execute("SELECT customer_name, site_name FROM asup_imports").fetchall():
                    if row[0]: customers.add(row[0])
                    if row[1]: sites.add(row[1])
            finally:
                db.close()

            self._json_response(200, {
                "ok": True,
                "customers": sorted(customers),
                "sites":     sorted(sites),
            })
        except Exception as e:
            self._json_response(500, {"ok": False, "error": str(e), "customers": [], "sites": []})

    def handle_knowledge_base_get(self):
        """GET /api/knowledge-base — Return the full knowledge base for enrichment mapping."""
        global _enrichment_scheduler
        kb = {'version': 1, 'articles': [], 'lastUpdated': None, 'articleCount': 0}
        if KNOWLEDGE_PATH.exists():
            try:
                kb = json.loads(KNOWLEDGE_PATH.read_text(encoding='utf-8'))
            except Exception:
                pass
        # Also include CISA KEV data if available
        kev_cve_set = set()
        if KEV_PATH.exists():
            try:
                kev_data = json.loads(KEV_PATH.read_text(encoding='utf-8'))
                for v in kev_data.get('vulnerabilities', []):
                    cve_id = (v.get('cveID') or '').upper()
                    if cve_id:
                        kev_cve_set.add(cve_id)
            except Exception:
                pass
        # Include bulletin summary counts by category
        bulletin_summary = {}
        psirt_cve_set = set()
        if BULLETINS_PATH.exists():
            try:
                bdata = json.loads(BULLETINS_PATH.read_text(encoding='utf-8'))
                for b in bdata.get('bulletins', []):
                    cat = b.get('severity', 'unknown').lower()
                    bulletin_summary[cat] = bulletin_summary.get(cat, 0) + 1
                    # Collect all CVE IDs from PSIRT bulletins
                    for cve_id in b.get('cve', []):
                        psirt_cve_set.add(cve_id.upper())
            except Exception:
                pass
        # kevCount = only PSIRT CVEs that appear in the CISA KEV catalog
        # (i.e. NetApp advisories for actively exploited vulnerabilities)
        kev_overlap = psirt_cve_set & kev_cve_set
        response = {
            'articles': kb.get('articles', []),
            'articleCount': kb.get('articleCount', len(kb.get('articles', []))),
            'lastUpdated': kb.get('lastUpdated'),
            'kevCount': len(kev_overlap),
            'kevCatalogSize': len(kev_cve_set),
            'bulletinSummary': bulletin_summary,
        }
        body = json.dumps(response, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_eoa_database_get(self):
        """GET /api/eoa-database — Return the EOA platform database."""
        eoa_path = os.path.join(os.path.dirname(__file__), 'data', 'eoa_database.json')
        try:
            with open(eoa_path, 'r', encoding='utf-8') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(data.encode('utf-8'))
        except FileNotFoundError:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'{"platforms":[],"dates":{},"switches":[]}')
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))

    def handle_imt_interop_get(self):
        """GET /api/imt-interop — Return the IMT interoperability matrix."""
        imt_path = os.path.join(os.path.dirname(__file__), 'data', 'imt_interop.json')
        try:
            with open(imt_path, 'r', encoding='utf-8') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(data.encode('utf-8'))
        except FileNotFoundError:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'{}')
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))

    def handle_reference_status_get(self):
        """GET /api/reference-library/status — Return freshness of all reference data files."""
        data_dir = os.path.join(os.path.dirname(__file__), 'data')
        status = {}
        for fname in ['firmware_baselines.json', 'security_bulletins.json', 'knowledge_base.json',
                      'eoa_database.json', 'imt_interop.json', 'cisa_kev.json']:
            fpath = os.path.join(data_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    fdata = json.load(f)
                last_updated = fdata.get('_lastUpdated') or fdata.get('lastUpdated') or 'unknown'
                status[fname] = {'lastUpdated': last_updated, 'exists': True}
            except FileNotFoundError:
                status[fname] = {'lastUpdated': None, 'exists': False}
            except Exception:
                status[fname] = {'lastUpdated': 'error', 'exists': True}
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(status, indent=2).encode('utf-8'))

    def handle_enrich_status(self):
        """GET /api/enrich/status — Return enrichment scanner status."""
        global _enrichment_scheduler
        if _enrichment_scheduler:
            status = _enrichment_scheduler.status()
        else:
            status = {'enabled': False, 'lastScan': None, 'isRunning': False}
        res = json.dumps(status).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(res)

    def handle_enrich_scan(self):
        """POST /api/enrich/scan — Manually trigger an enrichment scan."""
        global _enrichment_scheduler
        if not _enrichment_scheduler:
            self.send_response(503)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Enrichment scheduler not running'}).encode('utf-8'))
            return
        result = _enrichment_scheduler.run_now()
        self.send_response(202)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(result).encode('utf-8'))

    def handle_asup_delete(self):
        """DELETE /api/asup/imports?serial=XXX — remove an ASUP import."""
        try:
            from urllib.parse import urlparse, parse_qs
            params = parse_qs(urlparse(self.path).query)
            serial = params.get("serial", [None])[0]
            if not serial:
                self._json_response(400, {"ok": False, "error": "serial parameter required"})
                return
            db = _init_db()
            try:
                db.execute("DELETE FROM asup_imports WHERE serial_number = ?", (serial,))
                db.commit()
            finally:
                db.close()
            print(f"  [ASUP] Deleted import: serial={serial}", flush=True)
            self._json_response(200, {"ok": True, "deleted": serial})
        except Exception as e:
            print(f"  [ASUP] Delete error: {e}", flush=True)
            self._json_response(500, {"ok": False, "error": str(e)})


    def handle_config_get(self):
        """GET /api/config — return current config (without sensitive tokens)."""
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
            # Return only non-sensitive fields
            safe_cfg = {
                "watchlistId": cfg.get("watchlistId") or cfg.get("watchlist_id") or "",
                "watchlistIds": cfg.get("watchlistIds") or cfg.get("watchlistId") or cfg.get("watchlist_id") or "",
                "watchlistName": cfg.get("watchlistName", ""),
                "hasToken": bool(cfg.get("refreshToken") or cfg.get("refresh_token")),
                "enrichEnabled": cfg.get("enrichEnabled", True),
                "enrichIntervalHours": cfg.get("enrichIntervalHours", 12),
                "hasNvdKey": bool(cfg.get("nvdApiKey", "")),
                "hasGithubToken": bool(cfg.get("githubToken", "")),
                # Multi-account (multi-customer) support — never return raw tokens,
                # only enough for the Settings UI to list/edit accounts safely.
                "accounts": [
                    {
                        "id": a.get("id", ""),
                        "label": a.get("label", ""),
                        "watchlistId": a.get("watchlistId", ""),
                        "enabled": a.get("enabled", True),
                        "hasToken": bool(a.get("refreshToken") or a.get("refresh_token")),
                    }
                    for a in (cfg.get("accounts") or [])
                ],
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
            # Support both new watchlistIds (comma-sep) and legacy watchlistId (single)
            if "watchlistIds" in body:
                cfg["watchlistIds"] = body["watchlistIds"] or ""
                # Also backfill legacy key with first ID for older code paths
                first_id = (body["watchlistIds"] or "").split(",")[0].strip()
                if first_id:
                    cfg["watchlistId"] = first_id
            elif "watchlistId" in body:
                cfg["watchlistId"] = body["watchlistId"] or ""
                if not cfg.get("watchlistIds"):
                    cfg["watchlistIds"] = cfg["watchlistId"]
            if "watchlistName" in body:
                cfg["watchlistName"] = body["watchlistName"] or ""
            if "refreshToken" in body and body["refreshToken"].strip():
                cfg["refreshToken"] = body["refreshToken"].strip()
                print(f"  [CONFIG] Refresh token updated ({len(cfg['refreshToken'])} chars)", flush=True)
            if "tamName" in body:
                cfg["tamName"] = body["tamName"] or ""
            if "tamEmail" in body:
                cfg["tamEmail"] = body["tamEmail"] or ""
            if "enrichEnabled" in body:
                cfg["enrichEnabled"] = bool(body["enrichEnabled"])
            if "enrichIntervalHours" in body:
                cfg["enrichIntervalHours"] = int(body["enrichIntervalHours"])
            if "nvdApiKey" in body and body["nvdApiKey"].strip():
                cfg["nvdApiKey"] = body["nvdApiKey"].strip()
            if "githubToken" in body and body["githubToken"].strip():
                val = body["githubToken"].strip()
                cfg["githubToken"] = val
                print(f"  [CONFIG] GitHub token updated ({len(val)} chars)", flush=True)
            # Multi-account (multi-customer) management — the client resends the
            # full desired accounts list each time (add/edit/remove/reorder all
            # look the same: "here is the list now"). GET /api/config never
            # returns raw tokens, so an account entry with no refreshToken in
            # the POST body means "keep whatever token is already stored for
            # this id" rather than "clear the token" — only an explicit empty
            # string with the id ALSO absent from cfg would ever drop a token,
            # which can't happen via this merge path.
            if "accounts" in body and isinstance(body["accounts"], list):
                existing_by_id = {a.get("id"): a for a in (cfg.get("accounts") or []) if a.get("id")}
                new_accounts = []
                for i, acct in enumerate(body["accounts"]):
                    acct_id = (acct.get("id") or "").strip() or f"account{i}_{int(time.time())}"
                    prior = existing_by_id.get(acct_id, {})
                    token = (acct.get("refreshToken") or "").strip() or prior.get("refreshToken", "")
                    new_accounts.append({
                        "id": acct_id,
                        "label": (acct.get("label") or "").strip() or acct_id,
                        "refreshToken": token,
                        "watchlistId": (acct.get("watchlistId") or "").strip(),
                        "enabled": acct.get("enabled", True),
                    })
                cfg["accounts"] = new_accounts
                print(f"  [CONFIG] Accounts updated: {len(new_accounts)} account(s) ({sum(1 for a in new_accounts if a['enabled'])} enabled)", flush=True)
            # Update enrichment scheduler if running
            global _enrichment_scheduler
            if _enrichment_scheduler:
                _enrichment_scheduler.update_config(
                    interval_hours=cfg.get('enrichIntervalHours', 12),
                    nvd_api_key=cfg.get('nvdApiKey') or None
                )
            # Write back
            CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
            has_token = bool(cfg.get("refreshToken") or cfg.get("refresh_token"))
            wl_ids_saved = cfg.get("watchlistIds") or cfg.get("watchlistId", "")
            print(f"  [CONFIG] Saved: watchlistIds={wl_ids_saved}, hasToken={has_token}", flush=True)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "hasToken": has_token}).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def handle_bulletins_get(self):
        """GET /api/bulletins — Return the full security advisory database.

        Reads data/security_bulletins.json — the single authoritative store for all
        advisory data. On first run (file absent), returns an empty bulletin list.
        The app populates NETAPP_SECURITY_BULLETIN_DB entirely from this response;
        there is no hardcoded fallback in app.js.
        """
        try:
            if BULLETINS_PATH.exists():
                data = json.loads(BULLETINS_PATH.read_text(encoding="utf-8"))
            else:
                # First run — no dynamic bulletins yet; app.js hardcoded DB is the full set
                data = {
                    "version": 1,
                    "lastUpdated": None,
                    "source": "dynamic",
                    "bulletinCount": 0,
                    "bulletins": []
                }
            res = json.dumps(data, default=str).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(res)
        except Exception as e:
            print(f"  [BULLETINS] GET error: {e}", flush=True)
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e), "bulletins": []}).encode("utf-8"))

    def handle_bulletins_scan(self):
        """GET /api/bulletins/scan — Trigger a live pull from NetApp PSIRT + NVD.

        Scrapes security.netapp.com for all NTAP advisory IDs, compares against
        the current data/security_bulletins.json, fetches detail+CVSS for any new ones,
        and persists them atomically. Returns a JSON summary of the results.
        This is a synchronous call — the client should expect a response in ~30-60s
        depending on how many new advisories are found.
        """
        try:
            print("  [BULLETINS] Scan triggered via UI button", flush=True)
            result = scan_and_persist_advisories()
            res = json.dumps(result).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(res)
        except Exception as e:
            print(f"  [BULLETINS] Scan error: {e}", flush=True)
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e), "added": 0, "total": 0}).encode("utf-8"))

    def handle_bulletins_post(self):

        """POST /api/bulletins — Upsert bulletin entries into the persistent database.

        Body: { "bulletins": [{id, cve, cvss, severity, title, description,
                               affectedProducts, affectedVersions, fixedVersions,
                               mitigation, published, link}, ...] }

        Persistence guarantees:
        - All EXISTING entries in data/security_bulletins.json are preserved.
        - Incoming entries are merged by 'id' (update if exists, append if new).
        - Write is ATOMIC: written to a .tmp file then renamed, so a crash or
          disk error cannot leave the database in a corrupted state.
        - The previous file is kept as security_bulletins.bak for recovery.
        - Each entry receives a _addedAt date stamp (YYYY-MM-DD) when upserted.
        """
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length).decode("utf-8"))
            new_entries = body.get("bulletins", [])
            if not isinstance(new_entries, list):
                raise ValueError("'bulletins' must be a list")

            # Load ALL existing bulletins — every one is preserved
            if BULLETINS_PATH.exists():
                existing_data = json.loads(BULLETINS_PATH.read_text(encoding="utf-8"))
                bulletins = existing_data.get("bulletins", [])
            else:
                bulletins = []

            # Upsert by ID: existing entries survive; new ones are appended
            id_to_idx = {b["id"]: i for i, b in enumerate(bulletins) if b.get("id")}
            added = updated = 0
            today = datetime.now(timezone.utc).isoformat()[:10]
            for entry in new_entries:
                entry_id = entry.get("id")
                if not entry_id:
                    continue
                entry["_addedAt"] = today
                if entry_id in id_to_idx:
                    bulletins[id_to_idx[entry_id]] = entry
                    updated += 1
                else:
                    id_to_idx[entry_id] = len(bulletins)
                    bulletins.append(entry)
                    added += 1

            # Build output document
            out = {
                "version": 1,
                "lastUpdated": today,
                "source": "dynamic — authoritative store, updated by daily advisory scan",
                "bulletinCount": len(bulletins),
                "bulletins": bulletins
            }
            payload = json.dumps(out, indent=2, ensure_ascii=False)

            # Atomic write: .tmp → .bak rotation → rename
            tmp_path = BULLETINS_PATH.with_suffix(".tmp")
            bak_path = BULLETINS_PATH.with_suffix(".bak")
            tmp_path.write_text(payload, encoding="utf-8")
            if BULLETINS_PATH.exists():
                import shutil
                shutil.copy2(str(BULLETINS_PATH), str(bak_path))  # snapshot previous state
            tmp_path.replace(BULLETINS_PATH)                       # atomic rename

            print(f"  [BULLETINS] POST: +{added} new, {updated} updated, {len(bulletins)} total", flush=True)

            res = json.dumps({"added": added, "updated": updated, "total": len(bulletins)}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(res)
        except Exception as e:
            print(f"  [BULLETINS] POST error: {e}", flush=True)
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def handle_enrich(self):

        """GET /api/enrich?type=TYPE&id=ID  — per-item enrichment.
        GET /api/enrich/dump               — return all cached enrichment as one JSON blob.
        """
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        path_clean = parsed.path.rstrip('/')

        if path_clean == '/api/enrich/versions':
            db = _init_db()
            try:
                row = db.execute("SELECT result_json FROM enrich_cache WHERE cache_key = '_catalog:versions'").fetchone()
                if row:
                    catalog = json.loads(row[0])
                else:
                    catalog = fetch_latest_version_catalog()
                    if catalog:
                        db.execute(
                            'INSERT OR REPLACE INTO enrich_cache (cache_key, fetched_at, result_json, source) VALUES (?, ?, ?, ?)',
                            ('_catalog:versions', datetime.now(timezone.utc).isoformat(), json.dumps(catalog), 'docs.netapp.com')
                        )
                        db.commit()
            except Exception as e:
                catalog = {'error': str(e)}
            finally:
                db.close()
            body = json.dumps({'status': 'ok', 'catalog': catalog}).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path_clean == '/api/enrich/dump':
            # Return every cached enrichment entry as a map: {cache_key: data}
            db = _init_db()
            try:
                rows = db.execute(
                    'SELECT cache_key, result_json, fetched_at, source FROM enrich_cache ORDER BY fetched_at DESC'
                ).fetchall()
            finally:
                db.close()
            dump = {}
            for row in rows:
                try:
                    dump[row[0]] = {
                        'data': json.loads(row[1]),
                        'fetched_at': row[2],
                        'source': row[3]
                    }
                except Exception:
                    pass
            body = json.dumps({'status': 'ok', 'count': len(dump), 'entries': dump}).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # Default: single-item enrichment
        params = parse_qs(parsed.query)
        db = _init_db()
        try:
            result = handle_enrich_request(params, db)
        finally:
            db.close()
        body = json.dumps(result).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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

    def handle_firmware_probe(self):
        """Live probe: query per-system firmware + top-level firmware endpoints and return raw results."""
        global _current_token
        token = _current_token
        if not token:
            # Try to get a fresh token from config
            try:
                cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
                refresh_token = cfg.get("refreshToken") or cfg.get("refresh_token")
                if refresh_token:
                    status, raw = _http("POST", f"{REST_BASE}/v1/tokens/accessToken",
                        {"Content-Type": "application/json", "Accept": "application/json"},
                        {"refresh_token": refresh_token})
                    if status == 200:
                        token_data = json.loads(raw.decode("utf-8", errors="replace"))
                        token = token_data.get("access_token")
                        if token:
                            _current_token = token
            except Exception:
                pass
        if not token:
            self.send_response(401)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "No token. Harvest first."}).encode())
            return

        results = {}

        # 1. Per-system firmware (first 2 systems)
        _, sys_resp = _gql(token, """{
            systems(pageSize: 2) {
                systems {
                    serialNumber hostName platformType type
                    ... on ONTAPSystem {
                        systemFirmware { type currentVersion recommendedVersion }
                        motherboardFirmware { currentVersion recommendedVersion }
                        diskQualificationPackage { currentVersion recommendedVersion autoUpdateEligible }
                        shelves {
                            serialNumber shelfId
                            hardwareModel { name }
                            moduleHardwareModel { name }
                            drives { totalCount drives { firmwareRevision vendor hardwareModel { name } } }
                        }
                    }
                }
            }
        }""")
        results["per_system"] = sys_resp

        # 2. Top-level systemFirmwares
        _, sf_resp = _gql(token, """{
            systemFirmwares(pageSize: 5) {
                totalCount cursor
                systemFirmwares { currentVersion recommendedVersion type autoUpdateEligible }
            }
        }""")
        results["systemFirmwares"] = sf_resp

        # 3. Top-level driveFirmwares
        _, df_resp = _gql(token, """{
            driveFirmwares(pageSize: 5) {
                totalCount cursor
                driveFirmwares { currentVersion recommendedVersion driveModel }
            }
        }""")
        results["driveFirmwares"] = df_resp

        # 4. Top-level shelfFirmwares
        _, shf_resp = _gql(token, """{
            shelfFirmwares(pageSize: 5) {
                totalCount cursor
                shelfFirmwares { currentVersion recommendedVersion }
            }
        }""")
        results["shelfFirmwares"] = shf_resp

        # 5. Top-level diskQualificationPackages
        _, dqp_resp = _gql(token, """{
            diskQualificationPackages(pageSize: 5) {
                totalCount cursor
                diskQualificationPackages { currentVersion recommendedVersion autoUpdateEligible }
            }
        }""")
        results["diskQualificationPackages"] = dqp_resp

        # 6. Also check what we have in cached harvest data
        _probe_db = _init_db()
        try:
            cached_data, _ = _load_cached(_probe_db)
        finally:
            _probe_db.close()
        cached_sys = (cached_data or {}).get("systems") or []
        cached_fw_samples = []
        for s in cached_sys[:3]:
            cached_fw_samples.append({
                "serialNumber": s.get("serialNumber"),
                "systemName": s.get("systemName"),
                "systemFirmware": s.get("systemFirmware"),
                "motherboardFirmware": s.get("motherboardFirmware"),
                "diskQualificationPackage": s.get("diskQualificationPackage"),
                "shelves_count": len(s.get("shelves") or []),
                "first_shelf": (s.get("shelves") or [{}])[0] if s.get("shelves") else None,
            })
        results["cached_harvest_samples"] = cached_fw_samples

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(results, indent=2, default=str).encode())

    def handle_proxy(self, method):
        if self.path in ('/graphql', '/api/graphql'):
            # GQL lives on a different host from the REST API
            target_url = GQL_URL
        else:
            # Strip /api prefix, leaving e.g. /watchlist/all or /v2/watchlist/action
            endpoint = self.path[4:]  # removes leading /api

            # If the endpoint already carries an explicit version (/v2/...), use it
            # as-is on the base domain. Otherwise, default to /v1.
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

        def _do_proxy_request(ctx):
            """Inner helper: make the proxied request with the given SSL context."""
            req = urllib.request.Request(target_url, data=req_data, headers=headers, method=method)
            with urllib.request.urlopen(req, context=ctx) as response:
                res_data = response.read()
                print(f"  \u2190 {response.status} ({len(res_data)} bytes)", flush=True)
                self.send_response(response.status)
                for key, val in response.getheaders():
                    if key.lower() not in ['transfer-encoding', 'content-encoding', 'access-control-allow-origin']:
                        self.send_header(key, val)
                self.end_headers()
                self.wfile.write(res_data)

        # Query NetApp API using the shared (enterprise-CA-aware) SSL context
        print(f"  >> PROXY {method} {target_url}", flush=True)
        try:
            _do_proxy_request(_ssl_ctx())
        except urllib.error.HTTPError as e:
            res_data = e.read()
            body_preview = res_data[:200].decode('utf-8', errors='replace')
            print(f"  << HTTP {e.code} ERROR: {body_preview}", flush=True)
            # Detect if Zscaler/proxy is blocking at app layer (TLS succeeded but request rejected)
            if e.code in (404, 403, 407) and 'Unsupported endpoint' in body_preview:
                print(f"  [TLS] WARN Corporate proxy blocking this endpoint at application layer.", flush=True)
                print(f"  [TLS]   TLS handshake succeeded but the proxy is filtering the request content.", flush=True)
                print(f"  [TLS]   Ask IT to add 'api.activeiq.netapp.com' to the SSL inspection bypass list.", flush=True)
            self.send_response(e.code)
            for key, val in e.headers.items():
                if key.lower() not in ['transfer-encoding', 'content-encoding', 'access-control-allow-origin']:
                    self.send_header(key, val)
            self.end_headers()
            self.wfile.write(res_data)
        except ssl.SSLError as e:
            # TLS handshake failed — refresh cert store and retry once
            print(f"  [TLS] SSL error in proxy: {e} — refreshing cert store and retrying...", flush=True)
            _refresh_ssl_ctx()
            try:
                _do_proxy_request(_ssl_ctx())
            except Exception as e2:
                print(f"  << PROXY RETRY FAILED: {e2}", flush=True)
                self.send_response(502)
                self.end_headers()
                self.wfile.write(f"TLS error after cert refresh: {e2}".encode('utf-8'))
        except Exception as e:
            err_str = str(e)
            # Check for TLS-related errors wrapped in urllib exceptions
            if any(k in err_str for k in ('SSL', 'CERTIFICATE', 'certificate verify failed',
                                           'UNABLE_TO_VERIFY', 'DEPTH_ZERO', 'CERT_UNTRUSTED')):
                print(f"  [TLS] TLS-related proxy error: {e} — refreshing cert store and retrying...", flush=True)
                _refresh_ssl_ctx()
                try:
                    _do_proxy_request(_ssl_ctx())
                    return
                except Exception as e2:
                    err_str = str(e2)
            print(f"  << PROXY EXCEPTION: {err_str}", flush=True)
            self.send_response(500)
            self.end_headers()
            self.wfile.write(err_str.encode('utf-8'))


if __name__ == '__main__':
    # Initialize the cache DB on startup
    db = _init_db()
    cached, meta = _load_cached(db)
    db.close()

    # TLS probe: detect corporate SSL inspection proxies and auto-import CAs
    # This runs in a background thread so it doesn't block server startup
    threading.Thread(
        target=_tls_probe_and_refresh,
        args=("api.activeiq.netapp.com", 443),
        daemon=True,
        name="tls-probe"
    ).start()

    # Advisory scan: run in background if bulletins DB is absent or stale (>12 h old).
    # This ensures the security bulletin database is always fresh without blocking startup.
    def _startup_advisory_scan():
        import time as _time
        _time.sleep(45)  # wait for TLS probe + cert-store rebuild to complete first
        try:
            should_scan = not BULLETINS_PATH.exists()
            if not should_scan:
                try:
                    _bdata = json.loads(BULLETINS_PATH.read_text(encoding='utf-8'))
                    _last = _bdata.get('lastUpdated') or _bdata.get('lastScanned', '')
                    if _last:
                        _last_dt = datetime.fromisoformat(_last.replace('Z', '+00:00'))
                        _age_h = (datetime.now(timezone.utc) - _last_dt).total_seconds() / 3600
                        should_scan = _age_h > 12
                    else:
                        should_scan = True
                except Exception:
                    should_scan = True
            if should_scan:
                print("  [STARTUP] Bulletins DB absent or stale — running background advisory scan...", flush=True)
                scan_and_persist_advisories()
                print("  [STARTUP] Background advisory scan complete.", flush=True)
            else:
                print("  [STARTUP] Bulletins DB is fresh — skipping advisory scan.", flush=True)
        except Exception as _scan_err:
            print(f"  [STARTUP] Advisory scan failed: {_scan_err}", flush=True)

    threading.Thread(target=_startup_advisory_scan, daemon=True, name="startup-advisory-scan").start()

    # Start enrichment scheduler
    try:
        _cfg = json.loads(CONFIG_PATH.read_text(encoding='utf-8')) if CONFIG_PATH.exists() else {}
        if _cfg.get('enrichEnabled', True):
            _enrich_interval = int(_cfg.get('enrichIntervalHours', 6))
            _nvd_key = _cfg.get('nvdApiKey') or None
            _enrichment_scheduler = EnrichmentScheduler(interval_hours=_enrich_interval, nvd_api_key=_nvd_key)
            _enrichment_scheduler.start()
    except Exception as _sched_err:
        print(f'  [STARTUP] Enrichment scheduler failed to start: {_sched_err}', flush=True)

    # Start firmware baselines harvester (runs every 48h in background as fallback)
    def _firmware_harvest_loop():
        """Periodic firmware baseline harvester — checks NetApp docs for newer versions."""
        import time as _fh_time
        _fh_interval = 48 * 3600  # 48 hours
        _fh_data_dir = os.path.join(os.path.dirname(__file__), "data")
        # Wait 5 minutes after startup before first harvest
        _fh_time.sleep(300)
        while True:
            try:
                import sys as _fh_sys
                _tools_dir = os.path.join(os.path.dirname(__file__), "tools")
                if _tools_dir not in _fh_sys.path:
                    _fh_sys.path.insert(0, _tools_dir)
                from firmware_harvester import scheduled_harvest
                print("  [FW-HARVEST] Starting scheduled firmware baseline harvest...", flush=True)
                changes = scheduled_harvest(_fh_data_dir)
                if changes:
                    print(f"  [FW-HARVEST] Baselines updated: {len(changes)} changes", flush=True)
                    for k, v in changes.items():
                        print(f"    {k}: {v.get('old','')} → {v.get('new','')}", flush=True)
                else:
                    print("  [FW-HARVEST] No newer versions found.", flush=True)
            except Exception as _fh_err:
                print(f"  [FW-HARVEST] Harvest failed: {_fh_err}", flush=True)
            _fh_time.sleep(_fh_interval)

    try:
        threading.Thread(target=_firmware_harvest_loop, daemon=True, name="fw-baseline-harvester").start()
        print("  [STARTUP] Firmware baseline harvester scheduled (48h interval, first run in 5min)", flush=True)
    except Exception as _fh_start_err:
        print(f"  [STARTUP] Firmware harvester failed to start: {_fh_start_err}", flush=True)

    # ── Print reference data freshness banner ──
    _data_dir = os.path.join(os.path.dirname(__file__), 'data')
    print('  [STARTUP] Reference Data Status:', flush=True)
    for _ref_file in ['firmware_baselines.json', 'security_bulletins.json', 'knowledge_base.json',
                       'eoa_database.json', 'imt_interop.json']:
        _ref_path = os.path.join(_data_dir, _ref_file)
        try:
            with open(_ref_path, 'r', encoding='utf-8') as _rf:
                _rdata = json.load(_rf)
            _last = _rdata.get('_lastUpdated') or _rdata.get('lastUpdated') or '?'
            _age = ''
            try:
                from datetime import date as _date_cls
                _d = _date_cls.fromisoformat(_last)
                _days = (_date_cls.today() - _d).days
                _age = f' ({_days}d old)'
            except: pass
            print(f'    {_ref_file:35s}: {_last}{_age}', flush=True)
        except FileNotFoundError:
            print(f'    {_ref_file:35s}: [NOT FOUND]', flush=True)
        except Exception as _ref_err:
            print(f'    {_ref_file:35s}: [ERROR: {_ref_err}]', flush=True)

    print(f"Starting CORS Proxy Web Server on port {PORT}...")
    if cached:
        print(f"  [CACHE] Found cached data: {meta['system_count']} systems (last sync: {meta['harvested_at']})")
    else:
        print(f"  [CACHE] No cached data — first harvest will be from API")
    print(f"Access the dashboard at http://localhost:{PORT}")

    # ThreadingHTTPServer instead of plain HTTPServer: the single-threaded
    # server could only handle one request at a time, so a slow request
    # (an external enrichment fetch, a large deliverable render, a
    # long-running report query) blocked every other client -- including
    # /api/sync-status polls -- until it finished. Request handlers already
    # open/close their own short-lived SQLite connection per call (see
    # _init_db()) rather than sharing one across requests, and the module's
    # few pieces of shared mutable state (_is_syncing, the enrichment
    # scheduler's _running/_kb_running flags) are already guarded by
    # threading.Lock, so this is a safe drop-in swap, not a rewrite.
    # daemon_threads=True so in-flight request threads don't block process
    # shutdown on Ctrl+C.
    server = http.server.ThreadingHTTPServer(('127.0.0.1', PORT), ProxyHTTPRequestHandler)
    server.daemon_threads = True
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
        server.server_close()
