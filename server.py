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
  GET /api/baselines         — returns firmware_baselines.json (latest GA versions for ONTAP, StorageGRID, SANtricity, etc.)
  GET /api/bulletins         — returns dynamic security bulletin DB (security_bulletins.json)
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
import time
import subprocess
import os
import re
import tempfile
from pathlib import Path
from datetime import datetime, timezone

# ASUP offline import parser (stdlib-only core, py7zr optional)
try:
    import asup_parser
    _ASUP_AVAILABLE = True
except ImportError:
    _ASUP_AVAILABLE = False
    print("[ASUP] asup_parser.py not found — offline import disabled", flush=True)

PORT = 8080
SCRIPT_DIR = Path(__file__).parent
DB_PATH = SCRIPT_DIR / "aiq_cache.db"
CONFIG_PATH = SCRIPT_DIR / "aiq_config.json"
BULLETINS_PATH = SCRIPT_DIR / "security_bulletins.json"
FW_BASELINES_PATH = SCRIPT_DIR / "firmware_baselines.json"
GQL_URL = "https://gql.aiq.netapp.com/graphql"
REST_BASE = "https://api.activeiq.netapp.com"

# ── Ground-truth firmware / OS version baselines (from firmware_baselines.json) ──
# Loaded once at startup; refreshed by the daily Reference Library scan agent.
def _load_fw_baselines():
    try:
        with open(FW_BASELINES_PATH, "r", encoding="utf-8") as _f:
            return json.load(_f)
    except Exception as _e:
        print(f"[FW_BASELINES] Could not load firmware_baselines.json: {_e}", flush=True)
        return {}

FIRMWARE_BASELINES = _load_fw_baselines()
print(f"[FW_BASELINES] Loaded. ONTAP latest GA: {FIRMWARE_BASELINES.get('ontap', {}).get('latestGA', 'unknown')}, StorageGRID: {FIRMWARE_BASELINES.get('storageGrid', {}).get('latestGA', 'unknown')}", flush=True)

# Global sync state
_sync_lock = threading.Lock()
_is_syncing = False
_last_sync_error = None

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


def _do_full_harvest(watchlist_ids=None):
    """Execute the full AIQ GraphQL harvest. Returns the result dict.
    This is the core logic extracted from handle_harvest, now reusable
    for both synchronous and background calls.
    
    If watchlist_ids is provided (list of ID strings), only systems in those
    watchlists are fetched and merged (deduplicated by serialNumber).
    For backward compatibility, a bare string is also accepted.
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
    watchlist_ids = watchlist_ids or []  # empty list == no filter (all systems)

    start_time = time.time()
    try:
        # 1. Read refresh token
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
                  autoSupports { asupId generatedDate receivedDate subject type isManual }
                  ... on ONTAPSystem {
                    capacity {
                      physical { rawMarketingKiB usedKiB usablePerformanceTierKiB }
                      logical { usedKiB }
                      reportedOn
                    }
                    monthlyCapacity {
                      month
                      physical { rawMarketingKiB usedKiB }
                      logical { usedKiB }
                    }
                  }"""

        # ── ULTRA_SAFE: absolute minimum — no Float ratio/pct fields at all.
        #    Only used when MINIMAL also returns a NaN error (very rare edge case
        #    where even usedKiB triggers a bug on a specific API build).
        SYSTEMS_FIELDS_ULTRA_SAFE = """
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
                    systemFirmware { type currentVersion recommendedVersion autoUpdateEligible postingDate }
                    motherboardFirmware { currentVersion recommendedVersion postingDate }
                    diskQualificationPackage { currentVersion recommendedVersion autoUpdateEligible }
                    drivesSummary { driveModel model count firmware { currentVersion recommendedVersion autoUpdateEligible postingDate } }
                    shelves {
                      shelfId serialNumber
                      hardwareModel { name endOfAvailability endOfHwSupport }
                      moduleHardwareModel { name }
                      shelfFirmware { currentVersion recommendedVersion autoUpdateEligible postingDate }
                      drives {
                        totalCount
                        drives { firmwareRevision vendor hardwareModel { name } }
                      }
                    }
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

        # ── TAM_SAFE: same as TAM but omits ALL fields that the AIQ API can
        #    return as NaN when a system has no capacity/telemetry history.
        #    GQL spec forbids NaN in JSON floats — one NaN field poisons the
        #    entire page response: "Float cannot represent non numeric value: NaN".
        #
        #    Known NaN sources (all are derived ratio/delta fields, undefined
        #    when the divisor — a prior period or total — is zero/absent):
        #      • efficiency.ratio.*          — data-reduction ratios (no capacity history)
        #      • capacity.physical.qoqUtilizationPercentage — QoQ delta (no prior quarter)
        #      • capacity.physical.yoyUtilizationPercentage — YoY delta (no prior year)
        #      • monthlyCapacity[].physical.qoqUtilizationPercentage — same, monthly
        #      • monthlyCapacity[].efficiency.ratio.* — same as efficiency.ratio above
        #
        #    All absolute capacity values, firmware, lifecycle, contract, ASUP,
        #    and every other TAM-enriched field are preserved.
        SYSTEMS_FIELDS_TAM_SAFE = """
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
                    systemFirmware { type currentVersion recommendedVersion autoUpdateEligible postingDate }
                    motherboardFirmware { currentVersion recommendedVersion postingDate }
                    diskQualificationPackage { currentVersion recommendedVersion autoUpdateEligible }
                    drivesSummary { driveModel model count firmware { currentVersion recommendedVersion autoUpdateEligible postingDate } }
                    shelves {
                      shelfId serialNumber
                      hardwareModel { name endOfAvailability endOfHwSupport }
                      moduleHardwareModel { name }
                      shelfFirmware { currentVersion recommendedVersion autoUpdateEligible postingDate }
                      drives {
                        totalCount
                        drives { firmwareRevision vendor hardwareModel { name } }
                      }
                    }
                    capacity {
                      physical { rawMarketingKiB usedKiB usedWithoutSnapshotsKiB usablePerformanceTierKiB }
                      logical { usedKiB usedWithoutSnapshotsClonesKiB }
                      efficiency {
                        saved { savedKiB deDuplicationSavedKiB compactionSavedKiB }
                      }
                      reportedOn
                    }
                    monthlyCapacity {
                      month
                      physical { rawMarketingKiB usedKiB }
                      logical { usedKiB }
                    }
                  }"""

        # ── Early watchlist auto-discovery ──────────────────────────────────────
        # Fetch watchlists from REST *before* the systems query so we can use them
        # as a fallback scope when the account lacks unfiltered_system_access.
        # Falls back to GraphQL watchlist query if REST paths return nothing.
        _early_watchlists = []  # list of watchlist id strings
        if not watchlist_ids:
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

        _NAN_PHRASE = "float cannot represent non numeric value: nan"

        def _fetch_systems_for_scope(fields, scope_wl_id=None):
            """Fetch all systems pages for a given fields set and optional watchlist scope.

            Returns (systems, privilege_blocked, nan_error).
            nan_error is True when the API refused the request specifically because a
            Float field returned NaN — the caller should retry with TAM_SAFE fields.
            """
            systems = []
            cursor = None
            page = 0
            privilege_blocked = False
            nan_error = False
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
                # Detect privilege block or NaN error or watchlist-not-found errors
                if sys_resp.get("errors"):
                    err_msg = sys_resp["errors"][0].get("message", "")
                    if any(p in err_msg.lower() for p in _PRIVILEGE_PHRASES):
                        print(f"  [HARVEST] Privilege block detected: {err_msg[:120]}", flush=True)
                        privilege_blocked = True
                        break
                    elif _NAN_PHRASE in err_msg.lower():
                        print(f"  [HARVEST] NaN float error in GQL response — will retry with next field tier", flush=True)
                        nan_error = True
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
            return systems, privilege_blocked, nan_error

        # Four-tier fallback: TAM (full) → TAM_SAFE (NaN-proof) → MINIMAL → ULTRA_SAFE
        # TAM_SAFE removes all ratio/delta Float fields that can be NaN.
        # MINIMAL removes utilizationPercentage too (can be NaN for brand-new systems).
        # ULTRA_SAFE is the last resort: no Float fields at all — guaranteed to work.
        _FIELD_TIERS = [
            (SYSTEMS_FIELDS_TAM,        "Expanded TAM"),
            (SYSTEMS_FIELDS_TAM_SAFE,   "TAM-safe (NaN-proof)"),
            (SYSTEMS_FIELDS_MINIMAL,    "Minimal"),
            (SYSTEMS_FIELDS_ULTRA_SAFE, "Ultra-safe (no floats)"),
        ]
        all_systems = []
        used_tam_query = False

        for attempt, (fields, tier_label) in enumerate(_FIELD_TIERS):
            all_systems = []
            _any_nan = False  # set if any scope call raises a NaN error on this tier

            # First: try with configured watchlist_ids (fetching + deduplicating across all)
            if watchlist_ids:
                print(f"  [HARVEST] Fetching systems across {len(watchlist_ids)} configured watchlist(s) [{tier_label}]...", flush=True)
                seen_serials = set()
                for wl_id_cfg in watchlist_ids:
                    wl_systems, wl_blocked, wl_nan = _fetch_systems_for_scope(fields, wl_id_cfg)
                    if wl_nan:
                        _any_nan = True
                        break
                    for s in wl_systems:
                        sn = s.get("serialNumber", "")
                        if sn not in seen_serials:
                            seen_serials.add(sn)
                            all_systems.append(s)
                    if wl_blocked:
                        print(f"  [HARVEST] Privilege block on watchlist {wl_id_cfg} (skipping)", flush=True)
                blocked = len(all_systems) == 0 and not _any_nan
                fetched = all_systems[:]
            else:
                fetched, blocked, _any_nan = _fetch_systems_for_scope(fields, None)
                # ── BUG FIX: assign the unfiltered result to all_systems ──────
                # Previously `fetched` was populated but `all_systems` stayed []
                # causing the server to always store 0 systems even when the API
                # returned hundreds of systems.
                all_systems = list(fetched)

            # NaN error: skip straight to next tier (TAM_SAFE or MINIMAL)
            if _any_nan:
                print(f"  [HARVEST] WARNING: {tier_label} query hit NaN serialisation error — falling back to next tier...", flush=True)
                continue

            # If blocked by privilege OR returned 0 systems, retry with auto-discovered watchlists.
            if (blocked or len(all_systems) == 0) and _early_watchlists:
                already_tried = set(watchlist_ids or [])
                new_wls = [w for w in _early_watchlists if w not in already_tried]
                if new_wls:
                    reason = 'privilege block' if blocked else '0 systems from unfiltered/configured query'
                    print(f"  [HARVEST] Retrying with {len(new_wls)} auto-scoped watchlist(s) [{tier_label}] (reason: {reason})...", flush=True)
                    seen_serials = {s.get('serialNumber', '') for s in all_systems}
                    for wl_id_auto in new_wls:
                        wl_systems, _, wl_nan2 = _fetch_systems_for_scope(fields, wl_id_auto)
                        if wl_nan2:
                            _any_nan = True
                            break
                        for s in wl_systems:
                            sn = s.get("serialNumber", "")
                            if sn not in seen_serials:
                                seen_serials.add(sn)
                                all_systems.append(s)
                    if _any_nan:
                        print(f"  [HARVEST] WARNING: {tier_label} watchlist retry also hit NaN — falling back to next tier...", flush=True)
                        continue
                    print(f"  [HARVEST] Combined from watchlists [{tier_label}]: {len(all_systems)} unique systems", flush=True)

            if len(all_systems) > 0:
                if attempt == 0:
                    used_tam_query = True
                    print(f"  [HARVEST] {tier_label} query succeeded: {len(all_systems)} systems", flush=True)
                elif attempt == 1:
                    used_tam_query = True  # TAM_SAFE still gives rich data
                    print(f"  [HARVEST] {tier_label} query succeeded: {len(all_systems)} systems (efficiency ratios excluded)", flush=True)
                else:
                    print(f"  [HARVEST] {tier_label} query succeeded: {len(all_systems)} systems", flush=True)
                break
            elif attempt < len(_FIELD_TIERS) - 1:
                print(f"  [HARVEST] WARNING: {tier_label} query returned 0 systems — trying next tier...", flush=True)




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
                    shelfId
                    hardwareModel { name endOfAvailability endOfHwSupport }
                    moduleHardwareModel { name }
                    shelfFirmware { currentVersion recommendedVersion autoUpdateEligible postingDate }
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
                            ' shelves { serialNumber shelfId hardwareModel { name endOfAvailability endOfHwSupport } moduleHardwareModel { name } shelfFirmware { currentVersion recommendedVersion autoUpdateEligible postingDate } }'
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
                    }
                    system { serialNumber hostName }
                    systemRiskDetail
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
        customers = ((cust_resp.get("data") or {}).get("customers", {}).get("customers")) or [] if isinstance(cust_resp, dict) else []

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
            tam_sustainability = ((sust_resp.get("data") or {}).get("sustainabilityScore", {}).get("sustainabilityScores")) or [] if isinstance(sust_resp, dict) else []
            print(f"  [HARVEST] Sustainability scores: {len(tam_sustainability)}", flush=True)
        except Exception as e:
            print(f"  [HARVEST] WARNING: Sustainability failed: {e}", flush=True)

        # ── TAM: OS Version Catalog (paginated — fetches ALL pages) ──
        tam_os_versions = []
        try:
            print("  [HARVEST] Fetching OS version catalog (paginated)...", flush=True)
            _osv_cursor = None
            _osv_page = 0
            _osv_max_pages = 25  # safety cap (~5000 entries max)
            _osv_fields = """
                osVersion majorOsVersion osType operatingMode
                releaseDate endOfVersionFullSupport endOfVersionLimitedSupport endOfSelfServiceSupport
                supportState progressionPath
                bundledSystemFirmwares { type version biosVersion systemModel }
                bundledDriveFirmwares { driveModel version }
                bundledShelfFirmwares { shelfName shelfModuleName firmwareType shelfModuleFirmwareVersion sysShelfModuleFirmwareVersion }
                bundledSecurityFiles { fileType version }"""
            while _osv_page < _osv_max_pages:
                _after_arg = f', after: "{_osv_cursor}"' if _osv_cursor else ""
                _osv_query = (
                    "{ osVersions(pageSize: 200" + _after_arg + """) {
                    cursor
                    osVersions {""" + _osv_fields + """
                    }
                } }"""
                )
                _, _osv_resp = _gql(token, _osv_query)
                _osv_page += 1
                if not isinstance(_osv_resp, dict):
                    break
                _osv_data = ((_osv_resp.get("data") or {}).get("osVersions") or {})
                _osv_page_items = _osv_data.get("osVersions") or []
                if not _osv_page_items:
                    break
                tam_os_versions.extend(_osv_page_items)
                _new_cursor = _osv_data.get("cursor")
                if not _new_cursor or _new_cursor == _osv_cursor:
                    break  # no more pages
                _osv_cursor = _new_cursor
            print(f"  [HARVEST] OS versions: {len(tam_os_versions)} (across {_osv_page} page(s))", flush=True)
        except Exception as e:
            print(f"  [HARVEST] WARNING: OS versions failed: {e}", flush=True)

        # ── Fleet-level Firmware Queries ──
        # These root-level queries return recommended firmware versions across the
        # entire account/estate. Per-system firmware fields (systemFirmware,
        # motherboardFirmware) are often null, but these always return data.
        fleet_sp_firmware   = []  # [{firmwareType, firmwareVersion, status, priority, systemsSummary}]
        fleet_drive_fw      = []  # [{driveModel, firmwareVersion, status, priority, systemsSummary}]
        fleet_shelf_fw      = []  # [{shelfModuleName, firmwareVersion, status, priority, systemsSummary}]
        fleet_dqp           = []  # [{version, status, priority, systemsSummary}]
        try:
            print("  [HARVEST] Fetching fleet SP/BMC firmware recommendations...", flush=True)
            _, _sfw_resp = _gql(token, """{ systemFirmwares(pageSize: 50) {
                firmwareType firmwareVersion status priority creationDate
                systemsSummary { totalSystems upToDate notUpToDate }
            } }""")
            if isinstance(_sfw_resp, dict) and not _sfw_resp.get("errors"):
                fleet_sp_firmware = ((_sfw_resp.get("data") or {}).get("systemFirmwares") or [])
            print(f"  [HARVEST] Fleet SP firmware entries: {len(fleet_sp_firmware)}", flush=True)
        except Exception as e:
            print(f"  [HARVEST] WARNING: Fleet SP firmware failed: {e}", flush=True)

        try:
            print("  [HARVEST] Fetching fleet drive firmware recommendations...", flush=True)
            _, _dfw_resp = _gql(token, """{ driveFirmwares(pageSize: 200) {
                driveModel firmwareVersion status priority creationDate
                systemsSummary { totalSystems upToDate notUpToDate }
            } }""")
            if isinstance(_dfw_resp, dict) and not _dfw_resp.get("errors"):
                fleet_drive_fw = ((_dfw_resp.get("data") or {}).get("driveFirmwares") or [])
            print(f"  [HARVEST] Fleet drive firmware entries: {len(fleet_drive_fw)}", flush=True)
        except Exception as e:
            print(f"  [HARVEST] WARNING: Fleet drive firmware failed: {e}", flush=True)

        try:
            print("  [HARVEST] Fetching fleet shelf firmware recommendations...", flush=True)
            _, _shfw_resp = _gql(token, """{ shelfFirmwares(pageSize: 100) {
                shelfModuleName firmwareVersion status priority creationDate
                systemsSummary { totalSystems upToDate notUpToDate }
            } }""")
            if isinstance(_shfw_resp, dict) and not _shfw_resp.get("errors"):
                fleet_shelf_fw = ((_shfw_resp.get("data") or {}).get("shelfFirmwares") or [])
            print(f"  [HARVEST] Fleet shelf firmware entries: {len(fleet_shelf_fw)}", flush=True)
        except Exception as e:
            print(f"  [HARVEST] WARNING: Fleet shelf firmware failed: {e}", flush=True)

        try:
            print("  [HARVEST] Fetching fleet DQP recommendations...", flush=True)
            _, _dqp_resp = _gql(token, """{ diskQualificationPackages(pageSize: 20) {
                version status priority creationDate
                systemsSummary { totalSystems upToDate notUpToDate }
            } }""")
            if isinstance(_dqp_resp, dict) and not _dqp_resp.get("errors"):
                fleet_dqp = ((_dqp_resp.get("data") or {}).get("diskQualificationPackages") or [])
            print(f"  [HARVEST] Fleet DQP entries: {len(fleet_dqp)}", flush=True)
        except Exception as e:
            print(f"  [HARVEST] WARNING: Fleet DQP failed: {e}", flush=True)

        # Build fast lookup maps for fleet firmware
        # SP/BMC: firmwareType → {firmwareVersion, status, priority, systemsSummary}
        _fleet_sp_map = {}
        for _f in fleet_sp_firmware:
            _ft = (_f.get("firmwareType") or "").upper()
            # Keep highest-priority (CRITICAL > RECOMMENDED > OPTIONAL) entry per type
            _pri_order = {"CRITICAL": 0, "RECOMMENDED": 1, "OPTIONAL": 2}
            if _ft not in _fleet_sp_map or _pri_order.get(_f.get("priority", "").upper(), 9) < _pri_order.get(_fleet_sp_map[_ft].get("priority", "").upper(), 9):
                _fleet_sp_map[_ft] = _f
        # Drive: driveModel → {firmwareVersion, status, priority}
        _fleet_drive_map = {}
        for _f in fleet_drive_fw:
            _dm = (_f.get("driveModel") or "").upper()
            if _dm:
                _fleet_drive_map[_dm] = _f
        # Shelf: shelfModuleName → {firmwareVersion, status, priority}
        _fleet_shelf_map = {}
        for _f in fleet_shelf_fw:
            _sm = (_f.get("shelfModuleName") or "").upper()
            if _sm:
                _fleet_shelf_map[_sm] = _f
        # DQP: latest recommended version
        _fleet_dqp_latest = None
        for _f in fleet_dqp:
            _pri_order = {"CRITICAL": 0, "RECOMMENDED": 1, "OPTIONAL": 2}
            if _fleet_dqp_latest is None or _pri_order.get((_f.get("priority") or "").upper(), 9) < _pri_order.get((_fleet_dqp_latest.get("priority") or "").upper(), 9):
                _fleet_dqp_latest = _f

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
            tam_renewals = ((ren_resp.get("data") or {}).get("systemContractRenewals", {}).get("systems")) or [] if isinstance(ren_resp, dict) else []
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

        # 12b. REST capacity backfill ─────────────────────────────────────────
        # The per-system GQL capacity fragment (... on ONTAPSystem { capacity {} })
        # returns null/zero for accounts where ASUP telemetry isn't flowing into the
        # AIQ backend.  The REST v2 capacity endpoint is a separate data path that
        # often succeeds when GQL does not.
        #
        # Endpoint tried (in order):
        #   GET /v2/capacity/summary/level/system/id/{serial}
        #   GET /v1/capacity/details/level/system/id/{serial}   (legacy, same data)
        #   GET /v2/efficiency/summary/level/system/id/{serial} (efficiency fields)
        #
        # Response shape (v2/capacity/summary):
        #   { "capacity": { "raw": <TB>, "used": <TB>, "available": <TB>,
        #                   "rawKib": <KiB>, "usedKib": <KiB>,
        #                   "utilizationPercent": <float>,
        #                   "qoqUtilizationPercent": <float>,
        #                   "yoyUtilizationPercent": <float>,
        #                   "reportedDate": "YYYY-MM-DD",
        #                   "monthlyCapacityList": [{month, usedTB, rawTB, qoqPct}] } }
        # Field names vary slightly by API version — we check multiple keys.
        serial_to_rest_cap = {}
        _cap_auth_hdr = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        _zero_cap_serials = [
            s.get("serialNumber", "") for s in all_systems
            if not (s.get("capacity") or {}).get("physical", {}).get("rawMarketingKiB")
            and s.get("serialNumber")
        ]
        if _zero_cap_serials:
            print(f"  [HARVEST] REST capacity backfill: {len(_zero_cap_serials)} systems have zero GQL capacity — querying REST...", flush=True)
            _rest_cap_hits = 0
            for _sn in _zero_cap_serials:
                _rest_data = {}
                # Try multiple endpoint variants
                for _cap_path in [
                    f"/v2/capacity/summary/level/system/id/{_sn}",
                    f"/v1/capacity/details/level/system/id/{_sn}",
                ]:
                    try:
                        _st, _raw = _http("GET", f"{REST_BASE}{_cap_path}", _cap_auth_hdr)
                        if _st == 200:
                            _parsed = json.loads(_raw.decode("utf-8", errors="replace"))
                            # Flatten: response may be wrapped in {"capacity": {...}} or direct
                            _cap_block = _parsed.get("capacity") or _parsed.get("data") or _parsed
                            if isinstance(_cap_block, dict) and (
                                _cap_block.get("raw") or _cap_block.get("rawKib") or
                                _cap_block.get("rawMarketingKiB") or _cap_block.get("rawTb")
                            ):
                                _rest_data = _cap_block
                                break
                    except Exception:
                        pass

                if _rest_data:
                    # Normalise all known field-name variants → common keys (KiB)
                    def _to_kib(val_tb=None, val_kib=None, val_kb=None):
                        if val_kib:  return float(val_kib)
                        if val_tb:   return float(val_tb)  * (1024**3)
                        if val_kb:   return float(val_kb)  * 1024
                        return 0.0

                    _r_raw_kib  = _to_kib(
                        val_tb  = _rest_data.get("raw")  or _rest_data.get("rawTb"),
                        val_kib = _rest_data.get("rawKib") or _rest_data.get("rawMarketingKiB"),
                    )
                    _r_used_kib = _to_kib(
                        val_tb  = _rest_data.get("used") or _rest_data.get("usedTb"),
                        val_kib = _rest_data.get("usedKib") or _rest_data.get("usedKiB"),
                    )
                    _r_avail_kib = _to_kib(
                        val_tb  = _rest_data.get("available") or _rest_data.get("availableTb"),
                        val_kib = _rest_data.get("availableKib") or _rest_data.get("availableKiB"),
                    )
                    _r_usbl_kib = _to_kib(
                        val_tb  = _rest_data.get("usable") or _rest_data.get("usableTb"),
                        val_kib = _rest_data.get("usableKib"),
                    ) or (_r_raw_kib - _r_avail_kib if _r_raw_kib and _r_avail_kib else 0)
                    _r_util = (
                        _rest_data.get("utilizationPercent") or
                        _rest_data.get("utilization") or
                        _rest_data.get("utilizationPercentage") or 0
                    )
                    _r_qoq = (
                        _rest_data.get("qoqUtilizationPercent") or
                        _rest_data.get("qoqUtilization") or
                        _rest_data.get("qoqUtilizationPercentage") or 0
                    )
                    _r_yoy = (
                        _rest_data.get("yoyUtilizationPercent") or
                        _rest_data.get("yoyUtilization") or
                        _rest_data.get("yoyUtilizationPercentage") or 0
                    )
                    _r_reported = (
                        _rest_data.get("reportedDate") or
                        _rest_data.get("reportedOn") or
                        _rest_data.get("reportDate") or ""
                    )[:10]
                    # Monthly capacity list
                    _r_monthly = []
                    for _rm in (_rest_data.get("monthlyCapacityList") or
                                _rest_data.get("monthlyCapacity") or []):
                        _r_monthly.append({
                            "month":   _rm.get("month", ""),
                            "usedTB":  _rm.get("usedTB") or _rm.get("used") or 0,
                            "rawTB":   _rm.get("rawTB")  or _rm.get("raw")  or 0,
                            "qoqPct":  _rm.get("qoqPct") or _rm.get("qoqUtilizationPercent") or None,
                        })

                    if _r_raw_kib > 0:
                        serial_to_rest_cap[_sn] = {
                            "rawKiB":       _r_raw_kib,
                            "usedKiB":      _r_used_kib,
                            "usableKiB":    _r_usbl_kib,
                            "utilPct":      _r_util,
                            "qoqPct":       _r_qoq,
                            "yoyPct":       _r_yoy,
                            "reportedOn":   _r_reported,
                            "monthly":      _r_monthly,
                        }
                        _rest_cap_hits += 1

            print(f"  [HARVEST] REST capacity backfill: {_rest_cap_hits}/{len(_zero_cap_serials)} systems populated", flush=True)
        else:
            print(f"  [HARVEST] REST capacity backfill: skipped (all systems have GQL capacity data)", flush=True)

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

                switches.append({
                    "type":              sw_role,
                    "model":             sw_model,
                    "serialNumber":      sw_serial if sw_serial else "Not available",
                    "firmware":          fw  if fw  else "Not reported",
                    "targetFirmware":    target_fw,   # "" → UI shows "N/A"
                    "status":            status,
                    "ipAddress":         sw_ip,
                    "validationDetails": validation,
                    "deviceName":        sw_name,
                    "vendor":            sw_vendor,
                    "isMonitored":       is_monitored,
                    "isDiscovered":      is_discovered,
                })

            # ── Build shelves_out from per-system GQL data (includes live drive firmware) ──
            # Per-system shelves contain: shelfId, serialNumber, hardwareModel, moduleHardwareModel,
            # and drives { totalCount, drives [ { firmwareRevision, vendor, hardwareModel { name } } ] }
            # Cluster-level shelves add: endOfAvailability, endOfHwSupport, shelfFirmware (live)
            _per_sys_shelves_raw = s.get("shelves") or []
            shelves_out = []
            for psh in _per_sys_shelves_raw:
                phm  = psh.get("hardwareModel") or {}
                pmhm = psh.get("moduleHardwareModel") or {}
                # Extract live shelfFirmware from per-system GQL (newly added field)
                _psh_live_shfw = psh.get("shelfFirmware") or {}
                # Extract per-drive firmware inventory from per-system data
                _psh_drives_block = psh.get("drives") or {}
                _psh_drives_list  = _psh_drives_block.get("drives") or [] if isinstance(_psh_drives_block, dict) else []
                _psh_drive_count  = _psh_drives_block.get("totalCount") or len(_psh_drives_list) if isinstance(_psh_drives_block, dict) else 0
                _psh_drive_fw = []
                for _drv in _psh_drives_list:
                    _drv_model = (_drv.get("hardwareModel") or {}).get("name", "") or ""
                    _drv_fw_rev = _drv.get("firmwareRevision", "") or ""
                    _drv_vendor = _drv.get("vendor", "") or ""
                    if _drv_model or _drv_fw_rev:
                        _psh_drive_fw.append({
                            "driveModel": _drv_model,
                            "firmwareRevision": _drv_fw_rev,
                            "vendor": _drv_vendor,
                        })
                shelves_out.append({
                    "serialNumber": psh.get("serialNumber", ""),
                    "shelfId": psh.get("shelfId", ""),
                    "model": phm.get("name", ""),
                    "endOfAvailability": phm.get("endOfAvailability", ""),
                    "endOfHwSupport": phm.get("endOfHwSupport", ""),
                    "moduleType": pmhm.get("name", "") or psh.get("moduleType", ""),
                    # Drive firmware collected live from per-system GQL
                    "drives": _psh_drive_fw,
                    "driveCount": _psh_drive_count,
                    # shelfFirmware: live from per-system GQL (preferred); cluster merge may add more
                    "firmwareVersion": _psh_live_shfw.get("currentVersion", "") or psh.get("firmwareVersion", ""),
                    "recommendedFirmwareVersion": _psh_live_shfw.get("recommendedVersion", "") or psh.get("recommendedFirmwareVersion", ""),
                    "shelfFirmwareAutoUpdate": _psh_live_shfw.get("autoUpdateEligible"),
                    "shelfFirmwarePostingDate": _psh_live_shfw.get("postingDate", ""),
                })

            # ── Merge cluster-level shelves (adds EOS dates + live shelfFirmware) ──
            # Build lookup by serialNumber for merge
            _sh_by_serial = {sh["serialNumber"]: sh for sh in shelves_out if sh.get("serialNumber")}
            cl_shelves = serial_to_cluster_shelves.get(serial, [])
            for csh in cl_shelves:
                hm  = csh.get("hardwareModel") or {}
                mhm = csh.get("moduleHardwareModel") or {}
                _live_shfw = csh.get("shelfFirmware") or {}
                csh_serial = csh.get("serialNumber", "")
                if csh_serial and csh_serial in _sh_by_serial:
                    # Merge EOS dates and live shelf firmware into existing entry
                    _existing = _sh_by_serial[csh_serial]
                    if not _existing.get("endOfAvailability"):
                        _existing["endOfAvailability"] = hm.get("endOfAvailability", "")
                    if not _existing.get("endOfHwSupport"):
                        _existing["endOfHwSupport"] = hm.get("endOfHwSupport", "")
                    if not _existing.get("moduleType"):
                        _existing["moduleType"] = mhm.get("name", "")
                    if _live_shfw.get("currentVersion") and not _existing.get("firmwareVersion"):
                        _existing["firmwareVersion"] = _live_shfw.get("currentVersion", "")
                    if _live_shfw.get("recommendedVersion") and not _existing.get("recommendedFirmwareVersion"):
                        _existing["recommendedFirmwareVersion"] = _live_shfw.get("recommendedVersion", "")
                    if _live_shfw.get("autoUpdateEligible") is not None:
                        _existing["shelfFirmwareAutoUpdate"] = _live_shfw.get("autoUpdateEligible")
                    if _live_shfw.get("postingDate"):
                        _existing["shelfFirmwarePostingDate"] = _live_shfw.get("postingDate", "")
                else:
                    # Cluster-level-only shelf (not in per-system data): add with live firmware
                    shelves_out.append({
                        "serialNumber": csh_serial,
                        "shelfId": csh.get("shelfId", ""),
                        "model": hm.get("name", ""),
                        "endOfAvailability": hm.get("endOfAvailability", ""),
                        "endOfHwSupport": hm.get("endOfHwSupport", ""),
                        "moduleType": mhm.get("name", "") or csh.get("moduleType", ""),
                        "drives": [],
                        "driveCount": 0,
                        "firmwareVersion": _live_shfw.get("currentVersion", "") or csh.get("firmwareVersion", ""),
                        "recommendedFirmwareVersion": _live_shfw.get("recommendedVersion", "") or csh.get("recommendedFirmwareVersion", ""),
                        "shelfFirmwareAutoUpdate": _live_shfw.get("autoUpdateEligible"),
                        "shelfFirmwarePostingDate": _live_shfw.get("postingDate", ""),
                    })

            # ── Cross-reference firmware baselines from OS version catalog ──
            _os_ver_raw = s.get("osVersion") or ""
            _model_name = hw.get("name", "").upper()
            # Find matching catalog entry with progressive fuzzy fallback:
            #   1. Exact match  (e.g. 9.16.1P11)
            #   2. Base without patch suffix  (e.g. 9.16.1)
            #   3. Closest lower version in same major.minor  (e.g. latest 9.16.x)
            #   4. Closest lower version in same major  (e.g. latest 9.x)
            _os_fw_entry = None
            _os_ver_base = _os_ver_raw.split("P")[0] if "P" in _os_ver_raw else _os_ver_raw
            # Derive major.minor prefix for fuzzy matching (e.g. "9.16" from "9.16.1P11")
            _ver_parts = _os_ver_raw.split(".")
            _os_ver_minor_prefix = ".".join(_ver_parts[:2]) if len(_ver_parts) >= 2 else ""
            _os_ver_major_prefix = _ver_parts[0] if _ver_parts else ""
            # Semantic version sort key: converts '9.13.1P4' → (9,13,1,4) for correct ordering
            def _semver_key(entry):
                import re as _re
                raw = (entry.get("osVersion") or "")
                nums = [int(n) for n in _re.split(r'[.P]', raw) if n.isdigit()]
                return tuple(nums)
            # Pass 1: exact
            for _ov in (tam_os_versions or []):
                if _ov.get("osVersion") == _os_ver_raw:
                    _os_fw_entry = _ov
                    break
            # Pass 2: base (strip patch)
            if not _os_fw_entry and _os_ver_base:
                for _ov in (tam_os_versions or []):
                    if _ov.get("osVersion") == _os_ver_base:
                        _os_fw_entry = _ov
                        break
            # Pass 3: closest available entry in same major.minor branch
            if not _os_fw_entry and _os_ver_minor_prefix:
                _branch_candidates = [
                    _ov for _ov in (tam_os_versions or [])
                    if (_ov.get("osVersion") or "").startswith(_os_ver_minor_prefix)
                    and (_ov.get("bundledSystemFirmwares") or [])
                ]
                if _branch_candidates:
                    # Pick the entry with the highest semantic version
                    _os_fw_entry = max(_branch_candidates, key=_semver_key)
            # Pass 4: closest available entry in same major ONTAP version
            if not _os_fw_entry and _os_ver_major_prefix:
                _major_candidates = [
                    _ov for _ov in (tam_os_versions or [])
                    if (_ov.get("osVersion") or "").startswith(_os_ver_major_prefix + ".")
                    and (_ov.get("bundledSystemFirmwares") or [])
                ]
                if _major_candidates:
                    _os_fw_entry = max(_major_candidates, key=_semver_key)
            # SP / BMC firmware baseline (matched by hardware model name)
            _sp_fw_baseline = {}
            _bios_fw_ver = ""
            if _os_fw_entry:
                for _bfw in (_os_fw_entry.get("bundledSystemFirmwares") or []):
                    _bfw_model = (_bfw.get("systemModel") or "").upper()
                    if not _bfw_model or _bfw_model in _model_name or any(
                        part in _model_name for part in _bfw_model.split("-") if len(part) > 2
                    ):
                        _sp_fw_baseline = {
                            "type": _bfw.get("type", "SP"),
                            "version": _bfw.get("version", ""),
                            "biosVersion": _bfw.get("biosVersion", ""),
                        }
                        _bios_fw_ver = _bfw.get("biosVersion", "")
                        break
                if not _sp_fw_baseline and (_os_fw_entry.get("bundledSystemFirmwares") or []):
                    # Fall back to first entry if no model match
                    _bfw0 = _os_fw_entry["bundledSystemFirmwares"][0]
                    _sp_fw_baseline = {
                        "type": _bfw0.get("type", "SP"),
                        "version": _bfw0.get("version", ""),
                        "biosVersion": _bfw0.get("biosVersion", ""),
                    }
                    _bios_fw_ver = _bfw0.get("biosVersion", "")
            _disk_fw_baselines  = (_os_fw_entry.get("bundledDriveFirmwares") or []) if _os_fw_entry else []
            _shelf_fw_baselines = (_os_fw_entry.get("bundledShelfFirmwares") or []) if _os_fw_entry else []

            # ── Backfill shelf firmware from catalog when live API is empty ─────
            # Build lookup: moduleType (e.g. "IOM12C") → catalog firmware baseline
            if _shelf_fw_baselines:
                _shelf_fw_catalog = {
                    (bl.get("shelfModuleName") or "").upper(): bl
                    for bl in _shelf_fw_baselines
                    if bl.get("shelfModuleName")
                }
                for _sh in shelves_out:
                    if not _sh.get("firmwareVersion"):
                        _mtype = (_sh.get("moduleType") or "").upper()
                        _cat_bl = _shelf_fw_catalog.get(_mtype)
                        if _cat_bl:
                            _raw_cat_ver = _cat_bl.get("shelfModuleFirmwareVersion", "")
                            # Normalize firmware filename to short numeric version so it can be
                            # compared directly against the fleet recommendedFirmwareVersion.
                            # Catalog field contains filenames like "IOM12A.0411.SFW"; the fleet
                            # GQL shelfFirmwares returns a short version like "0411".
                            # Extract the first segment of 2-4 pure digits (e.g. "0411", "0303").
                            import re as _re
                            _cat_ver_m = _re.search(r'(?:^|\.)(\d{2,4})(?:\.|$)', _raw_cat_ver)
                            _sh["firmwareVersion"] = _cat_ver_m.group(1) if _cat_ver_m else _raw_cat_ver
                            # recommended priority: fleet-latest → API per-system recommendation → empty (⚠ Unverified).
                            # Never fall back to the catalog version here — catalog = installed (same source = circular comparison).
                            _fleet_sh_ver = (_fleet_shelf_map.get(_mtype) or {}).get("firmwareVersion", "")
                            # Priority: fleet-latest (global authoritative) > API per-system recommendation.
                            # Do NOT overwrite a valid API-provided recommendedFirmwareVersion with an empty
                            # fleet string — that would erroneously cause ⚠ Unverified when AIQ itself
                            # knows the recommended version for this system's shelf module.
                            if _fleet_sh_ver:
                                _sh["recommendedFirmwareVersion"] = _fleet_sh_ver
                            elif not _sh.get("recommendedFirmwareVersion"):
                                # Neither fleet nor API has a recommendation — leave empty → ⚠ Unverified
                                _sh["recommendedFirmwareVersion"] = ""
                            # else: preserve the API's existing per-system recommendedFirmwareVersion
                            _sh["fromCatalog"] = True
            # Override recommendedFirmwareVersion with fleet-latest for LIVE shelves that have a matching fleet entry.
            # This ensures live-data shelves whose recommendedFirmwareVersion came from the ONTAP catalog
            # are corrected to reflect the globally latest recommended version.
            # Catalog-backfilled shelves (fromCatalog=True) are excluded: their firmwareVersion is the
            # ONTAP-bundled baseline for that release, not live-running firmware.  Overwriting with
            # fleet-latest would create false drift (e.g. IOM12@0281 vs fleet@0411) even though the
            # system has never reported its actual running version.
            for _sh in shelves_out:
                if _sh.get("fromCatalog"):
                    continue  # do not override catalog-estimated shelves
                _mtype = (_sh.get("moduleType") or "").upper()
                _fleet_sh_ver = (_fleet_shelf_map.get(_mtype) or {}).get("firmwareVersion", "")
                if _fleet_sh_ver:
                    _sh["recommendedFirmwareVersion"] = _fleet_sh_ver

            # ── Populate DQP from catalog when live API returns empty ──────────
            # The diskQualificationPackage field returns {} for most accounts.
            # The drive firmware catalog (bundledDriveFirmwares) IS populated
            # and represents the DQP version bundled with this ONTAP release.
            # We synthesize a DQP baseline entry from the catalog count/version.
            _live_dqp = s.get("diskQualificationPackage") or {}
            if not _live_dqp.get("currentVersion") and _disk_fw_baselines:
                # Use OS version as the DQP version identifier (ONTAP-bundled DQP)
                _live_dqp = {
                    "currentVersion": _os_ver_raw,
                    "recommendedVersion": _os_ver_raw,
                    "autoUpdateEligible": True,
                    "driveCount": len(_disk_fw_baselines),
                    "fromCatalog": True,
                }

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
            # Tier 2: Fall back to cluster-level if system-level raw is also zero
            if _raw_kib == 0:
                _raw_kib  = cl_cap.get("rawCapacityTB", 0) * (1024**3)
                _used_kib = cl_cap.get("physicalUsedTB", 0) * (1024**3)
                _log_kib  = cl_cap.get("logicalUsedTB", 0) * (1024**3)
                _usbl_kib = cl_cap.get("usableCapacityTB", 0) * (1024**3)
                _qoq      = cl_cap.get("qoqUtilizationPct", 0)
                _yoy      = cl_cap.get("yoyUtilizationPct", 0)
            # Tier 3: REST API backfill — used when both GQL paths return zero capacity
            if _raw_kib == 0 and serial in serial_to_rest_cap:
                _rc = serial_to_rest_cap[serial]
                _raw_kib  = _rc.get("rawKiB", 0)
                _used_kib = _rc.get("usedKiB", 0)
                _usbl_kib = _rc.get("usableKiB", 0)
                _util_pct = _rc.get("utilPct", 0)
                _qoq      = _rc.get("qoqPct", 0)
                _yoy      = _rc.get("yoyPct", 0)
                # If REST monthly data available and GQL monthly is empty, use REST's
                if not _sys_monthly and _rc.get("monthly"):
                    _sys_monthly = _rc["monthly"]

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
                # systemFirmware from API is a single dict {type, currentVersion, recommendedVersion,
                # autoUpdateEligible, postingDate} or null/empty. Normalise to a list so app.js can
                # uniformly call .forEach(). Resolution hierarchy:
                #   1. Live: API returned currentVersion → use directly (green ✓ Current / ⚠ UPDATE)
                #   2. Semi-live: API returned recommendedVersion but no currentVersion → the API
                #      knows this system's recommended firmware; use catalog baseline as the estimated
                #      installed version for comparison. If they match → green ✓ Est. Current.
                #      If they differ → orange ⚠ UPDATE. Mark _fromCatalog=True so UI can differentiate.
                #   3. Fleet-only: API returned nothing useful → backfill from fleet-level GQL map
                #      (recommendedVersion only, no per-system currentVersion). Show ⚠ Unverified.
                "systemFirmware": (lambda _sf: (
                    # Path 1: Live per-system currentVersion from API
                    [_sf] if isinstance(_sf, dict) and _sf.get("currentVersion") else
                    # Path 2: API has recommendedVersion but no currentVersion.
                    # Use catalog SP baseline as estimated installed version for comparison.
                    (
                        [{
                            "type": (_sf.get("type") or _sp_fw_baseline.get("type") or "SP"),
                            "currentVersion": _sp_fw_baseline.get("version", ""),  # catalog-estimated installed version
                            "recommendedVersion": _sf.get("recommendedVersion", ""),  # API's per-system recommendation
                            "autoUpdateEligible": _sf.get("autoUpdateEligible"),
                            "postingDate": _sf.get("postingDate", ""),
                            "_fromCatalog": True,  # estimated — not live-confirmed installed version
                        }]
                        if (isinstance(_sf, dict) and _sf.get("recommendedVersion") and _sp_fw_baseline.get("version"))
                        else
                        # Path 3: Fleet-only backfill (no per-system data at all)
                        [{
                            "type": _fv.get("firmwareType", "SP"),
                            "currentVersion": "",  # live current not available per-system from fleet queries
                            "recommendedVersion": _fv.get("firmwareVersion", ""),
                            "autoUpdateEligible": None,
                            "postingDate": _fv.get("creationDate", ""),
                            "_fromFleet": True,
                        } for _fv in _fleet_sp_map.values()]
                        if _fleet_sp_map else []
                    )
                ))(s.get("systemFirmware") or {}),
                "motherboardFirmware": s.get("motherboardFirmware") or {},
                # DQP: prefer live per-system, then catalog, then fleet latest
                "diskQualificationPackage": (
                    _live_dqp or s.get("diskQualificationPackage")
                    or ({
                        "currentVersion": "",
                        "recommendedVersion": _fleet_dqp_latest.get("version", ""),
                        "autoUpdateEligible": True,
                        "_fromFleet": True,
                    } if _fleet_dqp_latest else {})
                ) or {},
                # ── Drive firmware: live per-system list via drivesSummary (GQL field that replaced
                # the defunct driveFirmware[] field). Each entry has driveModel/model, count, and
                # firmware { currentVersion, recommendedVersion, autoUpdateEligible, postingDate }.
                # Firmware versions are independent of OS version — flag any downrev component.
                # Normalised to a flat list matching the old driveFirmware[] shape for compatibility.
                "driveFirmware": (
                    (lambda _ds: [
                        {
                            "driveModel": d.get("driveModel") or d.get("model", ""),
                            "count": d.get("count", 0),
                            "currentVersion": (d.get("firmware") or {}).get("currentVersion", ""),
                            "recommendedVersion": (d.get("firmware") or {}).get("recommendedVersion", ""),
                            "autoUpdateEligible": (d.get("firmware") or {}).get("autoUpdateEligible"),
                            "postingDate": (d.get("firmware") or {}).get("postingDate", ""),
                        } for d in _ds if d.get("driveModel") or d.get("model")
                    ] if _ds else []
                    )(s.get("drivesSummary") or [])
                ),
                # ── Raw drivesSummary passthrough (for debugging/export) ──
                "drivesSummary": s.get("drivesSummary") or [],
                "autoUpdateSettings": s.get("autoUpdateSettings") or {},
                # ── Firmware baselines cross-referenced from OS version catalog ──
                "spFirmwareBaseline":    _sp_fw_baseline,    # {type, version, biosVersion} expected for this ONTAP version
                "biosVersion":           _bios_fw_ver,       # BIOS version from catalog
                "diskFirmwareBaselines": _disk_fw_baselines, # [{driveModel, version}] bundled with this ONTAP release
                "shelfFirmwareBaselines": _shelf_fw_baselines, # [{shelfModuleName, shelfModuleFirmwareVersion, ...}]
                # ── Fleet-level firmware recommendation maps (from root-level GQL queries) ──
                # ── Ground-truth OS version baselines (from firmware_baselines.json) ──
                "firmwareBaselines":      FIRMWARE_BASELINES,         # {ontap, storageGrid, santricity, ...} latest GA versions
                # ── Fleet-level firmware recommendation maps (from root-level GQL queries) ──
                "fleetSpFirmwareMap":     _fleet_sp_map,     # {firmwareType.upper() → {firmwareVersion, status, priority}} global fleet latest SP/BMC
                "fleetDriveFirmwareMap":  _fleet_drive_map,  # {driveModel → {firmwareVersion, status, priority}}
                "fleetShelfFirmwareMap":  _fleet_shelf_map,  # {shelfModuleName → {firmwareVersion, status, priority}}
                "fleetDqpLatest":         _fleet_dqp_latest or {},  # latest DQP from fleet query
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
            "tamRenewals": tam_renewals,
        }

        print(f"  [HARVEST] Done in {duration_ms}ms: {len(systems_out)} systems, {len(all_clusters)} clusters, {len(all_risks)} unique risks, {len(all_risk_instances)} risk instances, {len(all_cases)} cases", flush=True)

        # Save to cache
        db = _init_db()
        try:
            _save_harvest(db, result, duration_ms)
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
        print(f"  [BACKGROUND] Starting background re-sync{scope_msg}...", flush=True)
        _do_full_harvest(watchlist_ids=wl_ids)
        print("  [BACKGROUND] Background re-sync complete.", flush=True)
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


def _enrich_fetch(url, timeout=12):
    """Fetch URL, return (text, error). Uses the shared proxy-aware opener so that
    on corporate networks (Zscaler/WPAD) the request is correctly routed through
    the system HTTP proxy — docs.netapp.com, nvd.nist.gov, security.netapp.com
    are all proxied on corporate networks and fail silently without this.
    Falls back to a cert-store refresh + opener rebuild on any TLS error."""
    global _opener_cache
    req = urllib.request.Request(url, headers={'User-Agent': _ENRICH_UA})
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
    """Remove HTML tags, decode entities, collapse whitespace."""
    class Stripper(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []
        def handle_data(self, data):
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
    """
    url = f'https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={urllib.parse.quote(cve_id)}'
    if api_key:
        url += f'&apiKey={api_key}'
    text, err = _enrich_fetch(url)
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


def scan_and_persist_advisories():
    """
    Full advisory scan pipeline:
    1. Fetch the NTAP advisory index from security.netapp.com
    2. Collect all advisory IDs (NTAP-YYYYMMDD-XXXX format)
    3. Load existing IDs from security_bulletins.json
    4. For each NEW advisory: fetch detail page + NVD CVSS data
    5. Upsert into security_bulletins.json (atomic write)
    Returns dict: {added, updated, total, scanned, errors, newIds}
    """
    import time
    added = updated = errors = 0
    new_ids = []

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
                nvd_text, nvd_err = _enrich_fetch(nvd_url, timeout=15)
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


def _search_nvd_for_version(version, cpe_product_keyword):
    """
    Query NVD CVE API v2 by keyword+version to find CVEs affecting this version.
    Returns list of {id, description, cvss, severity, publishedDate} dicts.
    """
    results = []
    try:
        # NVD keyword search: product + version
        q = urllib.parse.quote(f'{cpe_product_keyword} {version}')
        url = f'https://services.nvd.nist.gov/rest/json/cves/2.0?keywordSearch={q}&resultsPerPage=10'
        text, err = _enrich_fetch(url, timeout=20)
        if err or not text:
            return results
        data = json.loads(text)
        for item in data.get('vulnerabilities', []):
            vuln = item.get('cve', {})
            cve_id = vuln.get('id', '')
            descs = vuln.get('descriptions', [])
            desc  = next((d['value'] for d in descs if d.get('lang') == 'en'), '')
            if not desc or version[:4] not in desc and version.split('.')[0] not in desc:
                # Skip CVEs that don't actually mention this version family
                pass  # still include — keyword search already filtered
            metrics = vuln.get('metrics', {})
            cvss_score = None
            severity   = 'UNKNOWN'
            for key in ('cvssMetricV31', 'cvssMetricV30', 'cvssMetricV2'):
                if key in metrics and metrics[key]:
                    m = metrics[key][0].get('cvssData', {})
                    cvss_score = m.get('baseScore')
                    severity   = (m.get('baseSeverity') or 'UNKNOWN').upper()
                    break
            published = vuln.get('published', '')[:10]
            if cve_id:
                results.append({
                    'id':            cve_id,
                    'description':   desc[:400],
                    'cvss':          cvss_score,
                    'severity':      severity,
                    'publishedDate': published,
                })
    except Exception:
        pass
    return results[:8]


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

    # ── Motivation ────────────────────────────────────────────────────────────
    parts = []
    if result['knownIssues']:
        parts.append(f"{len(result['knownIssues'])} known issue(s)")
    if result['relatedCVEs']:
        parts.append(f"{len(result['relatedCVEs'])} CVE(s) found via NVD")
    if result['relatedAdvisories']:
        parts.append(f"{len(result['relatedAdvisories'])} PSIRT advisory/advisories")
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

    # ── Motivation ────────────────────────────────────────────────────────────
    parts = []
    if result['knownIssues']:
        parts.append(f"{len(result['knownIssues'])} known issue(s)")
    if result['relatedCVEs']:
        parts.append(f"{len(result['relatedCVEs'])} CVE(s) found via NVD")
    if result['relatedAdvisories']:
        parts.append(f"{len(result['relatedAdvisories'])} PSIRT advisory/advisories")
    result['upgradeMotivation'] = '. '.join(parts) if parts else 'No major issues found in public sources for this version.'

    return result if result['sources'] else None



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

    # ── Version types: return 'pending' — background thread will enrich ───────
    # Never do live fetches here; the server is single-threaded and external
    # HTTP calls (docs.netapp.com, NVD, PSIRT) take 5-20s each, blocking ALL
    # other requests including harvest, UI, etc.
    if enrich_type in _VERSION_ENRICH_TYPES:
        return {
            'status': 'pending',
            'message': 'Version enrichment is handled by the background sync thread. '
                       'Data will be available after the next sync completes.',
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
        elif self.path.startswith('/api/enrich'):
            self.handle_enrich()
        elif self.path.startswith('/api/bulletins/scan'):
            self.handle_bulletins_scan()
        elif self.path.startswith('/api/bulletins'):
            self.handle_bulletins_get()
        elif self.path.startswith('/api/baselines'):
            self.handle_baselines_get()
        elif self.path.startswith('/api/asup/imports'):
            self.handle_asup_list()
        elif self.path == '/api/asup/import':
            self.handle_asup_import()
        elif self.path == '/api/asup/customers':
            self.handle_asup_customers()
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
        elif self.path == '/api/asup/import':
            self.handle_asup_import()
        elif self.path == '/api/asup/associate':
            self.handle_asup_associate()
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

    def handle_baselines_get(self):
        """GET /api/baselines — Serve firmware_baselines.json to the client.

        Returns the ground-truth latest GA version catalog used by app.js to
        populate Section 5a (Software Version Currency) for both live API
        systems and mock-mode systems. The file is updated daily by the
        Reference Library scan cron agent.
        """
        try:
            # Reload from disk on every request so updates from the daily scan
            # are reflected without restarting the server.
            if FW_BASELINES_PATH.exists():
                data = json.loads(FW_BASELINES_PATH.read_text(encoding="utf-8"))
            else:
                data = {}
            res = json.dumps(data, default=str).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(res)
        except Exception as e:
            print(f"  [BASELINES] GET error: {e}", flush=True)
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def handle_bulletins_get(self):
        """GET /api/bulletins — Return the full security advisory database.

        Reads security_bulletins.json — the single authoritative store for all
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
        the current security_bulletins.json, fetches detail+CVSS for any new ones,
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
        - All EXISTING entries in security_bulletins.json are preserved.
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
