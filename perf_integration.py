"""StoragePerf (Plumb) performance integration.

Active IQ says what a system IS and what NetApp saw in its AutoSupport. It cannot
say how the system is performing right now, or whether a slowness complaint is the
array or the network in front of it. StoragePerf (Plumb) measures exactly that on
the customer's site and publishes a versioned JSON snapshot ("plumb.aria-export/1").

ARIA gets that snapshot two ways, both ending in the same table:

  * PULL   -- the customer's Plumb is reachable from the MSP (VPN, routed network):
              a "source" (customer + base URL + optional token) is fetched on demand
              and on a schedule from GET <base_url>/api/aria/export.
  * IMPORT -- it is not (dark site, no VPN): the customer sends the JSON file
              (Plumb: Config > ARIA integration > Download, or the scheduled files in
              data/aria-exports/) and it is uploaded here.

Snapshots are kept per customer (history, so trends can be shown), and the browser
matches arrays to systems by serial number / cluster name. Nothing here writes to
Plumb or to Active IQ: it is read-only in both directions.
"""
import json
import ssl
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

SCHEMA_PREFIX = "plumb.aria-export/"
SUPPORTED_MAJOR = "1"
MAX_PAYLOAD_BYTES = 30 * 1024 * 1024
KEEP_SNAPSHOTS_PER_CUSTOMER = 60
PULL_TIMEOUT_S = 180  # a multi-week export over many arrays is genuinely slow to build


def _now():
    return datetime.now(timezone.utc).isoformat()


def init_tables(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS perf_sources (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name  TEXT NOT NULL,
            label          TEXT DEFAULT '',
            base_url       TEXT NOT NULL,
            token          TEXT DEFAULT '',
            interval_hours INTEGER DEFAULT 24,
            enabled        INTEGER DEFAULT 1,
            verify_tls     INTEGER DEFAULT 1,
            period_hours   INTEGER DEFAULT 168,
            last_pull_at   TEXT DEFAULT '',
            last_status    TEXT DEFAULT '',
            last_error     TEXT DEFAULT '',
            created_at     TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS perf_snapshots (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id     INTEGER,
            customer_name TEXT NOT NULL,
            site_label    TEXT DEFAULT '',
            plumb_version TEXT DEFAULT '',
            generated_at  TEXT NOT NULL,
            period_hours  REAL DEFAULT 0,
            array_count   INTEGER DEFAULT 0,
            via           TEXT NOT NULL,
            filename      TEXT DEFAULT '',
            mock_data     INTEGER DEFAULT 0,
            payload_json  TEXT NOT NULL,
            imported_at   TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_perf_snapshots_customer ON perf_snapshots(customer_name, generated_at);
    """)
    db.commit()


# ── validation ─────────────────────────────────────────────────────────────────
def validate_export(obj, allow_mock=False):
    """Return (ok, error). Deliberately strict about the envelope and lenient about
    everything inside it: consumers must ignore fields they don't know."""
    if not isinstance(obj, dict):
        return False, "The file is not a StoragePerf ARIA export (expected a JSON object)."
    schema = str(obj.get("schema") or "")
    if not schema.startswith(SCHEMA_PREFIX):
        return False, "The file is not a StoragePerf ARIA export (missing schema '%s...')." % SCHEMA_PREFIX
    if schema[len(SCHEMA_PREFIX):].split(".")[0] != SUPPORTED_MAJOR:
        return False, ("This export uses schema '%s'; this version of ARIA understands major version %s. "
                       "Update ARIA or re-export from a matching StoragePerf." % (schema, SUPPORTED_MAJOR))
    arrays = obj.get("arrays")
    if not isinstance(arrays, list):
        return False, "The export has no 'arrays' list."
    for a in arrays:
        if not isinstance(a, dict) or not a.get("id"):
            return False, "The export contains an array entry without an 'id'."
    if obj.get("mock_data") and not allow_mock:
        return False, ("This export was produced by StoragePerf's built-in demo fleet (mock data), "
                       "not by real monitored systems. Turn mock data off in StoragePerf and export again.")
    return True, ""


def normalize_base_url(url):
    url = (url or "").strip().rstrip("/")
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise ValueError("Base URL must start with http:// or https:// (for example http://plumb.customer.example:8000).")
    for suffix in ("/api/aria/export", "/api/aria/info", "/api"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    return url


# ── storage ────────────────────────────────────────────────────────────────────
def store_snapshot(db, payload, customer_name, via, source_id=None, filename="", allow_mock=False):
    ok, err = validate_export(payload, allow_mock=allow_mock)
    if not ok:
        raise ValueError(err)
    customer_name = (customer_name or "").strip()
    if not customer_name:
        raise ValueError("A customer must be chosen so the snapshot can be matched to that customer's systems.")
    generated = str(payload.get("generated_at") or _now())
    cur = db.execute(
        """INSERT INTO perf_snapshots
             (source_id, customer_name, site_label, plumb_version, generated_at, period_hours,
              array_count, via, filename, mock_data, payload_json, imported_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (source_id, customer_name, str(payload.get("site") or ""), str(payload.get("plumb_version") or ""),
         generated, float(payload.get("period_hours") or 0), len(payload.get("arrays") or []), via, filename,
         1 if payload.get("mock_data") else 0, json.dumps(payload, separators=(",", ":")), _now()))
    snap_id = cur.lastrowid
    db.execute(
        """DELETE FROM perf_snapshots WHERE customer_name = ? AND id NOT IN
             (SELECT id FROM perf_snapshots WHERE customer_name = ? ORDER BY generated_at DESC, id DESC LIMIT ?)""",
        (customer_name, customer_name, KEEP_SNAPSHOTS_PER_CUSTOMER))
    db.commit()
    return snap_id


_SNAP_META = ("id, source_id, customer_name, site_label, plumb_version, generated_at, period_hours, "
              "array_count, via, filename, mock_data, imported_at")


def _meta(row):
    return {"id": row[0], "sourceId": row[1], "customerName": row[2], "siteLabel": row[3], "plumbVersion": row[4],
            "generatedAt": row[5], "periodHours": row[6], "arrayCount": row[7], "via": row[8], "filename": row[9],
            "mockData": bool(row[10]), "importedAt": row[11]}


def latest_snapshots(db):
    """Newest snapshot per customer, payload included."""
    rows = db.execute(
        "SELECT " + _SNAP_META + ", payload_json FROM perf_snapshots s WHERE id = "
        "(SELECT id FROM perf_snapshots WHERE customer_name = s.customer_name ORDER BY generated_at DESC, id DESC LIMIT 1) "
        "ORDER BY customer_name").fetchall()
    out = []
    for r in rows:
        m = _meta(r)
        try:
            m["payload"] = json.loads(r[12])
        except ValueError:
            continue
        out.append(m)
    return out


def list_snapshots(db, customer_name=None, limit=60):
    if customer_name:
        rows = db.execute("SELECT " + _SNAP_META + " FROM perf_snapshots WHERE customer_name = ? "
                          "ORDER BY generated_at DESC, id DESC LIMIT ?", (customer_name, limit)).fetchall()
    else:
        rows = db.execute("SELECT " + _SNAP_META + " FROM perf_snapshots ORDER BY generated_at DESC, id DESC LIMIT ?",
                          (limit,)).fetchall()
    return [_meta(r) for r in rows]


def delete_snapshot(db, snap_id):
    db.execute("DELETE FROM perf_snapshots WHERE id = ?", (snap_id,))
    db.commit()


# ── sources ────────────────────────────────────────────────────────────────────
_SRC_COLS = ("id, customer_name, label, base_url, token, interval_hours, enabled, verify_tls, period_hours, "
             "last_pull_at, last_status, last_error")


def _source(row, include_token=False):
    d = {"id": row[0], "customerName": row[1], "label": row[2], "baseUrl": row[3], "hasToken": bool(row[4]),
         "intervalHours": row[5], "enabled": bool(row[6]), "verifyTls": bool(row[7]), "periodHours": row[8],
         "lastPullAt": row[9], "lastStatus": row[10], "lastError": row[11]}
    if include_token:
        d["token"] = row[4]
    return d


def list_sources(db, include_token=False):
    return [_source(r, include_token) for r in
            db.execute("SELECT " + _SRC_COLS + " FROM perf_sources ORDER BY customer_name, label").fetchall()]


def get_source(db, source_id, include_token=True):
    r = db.execute("SELECT " + _SRC_COLS + " FROM perf_sources WHERE id = ?", (source_id,)).fetchone()
    return _source(r, include_token) if r else None


def upsert_source(db, body):
    customer = (body.get("customerName") or "").strip()
    if not customer:
        raise ValueError("Choose the customer this StoragePerf belongs to.")
    base_url = normalize_base_url(body.get("baseUrl"))
    interval = max(0, int(body.get("intervalHours") if body.get("intervalHours") is not None else 24))
    period = max(1, min(24 * 90, int(body.get("periodHours") or 168)))
    vals = (customer, (body.get("label") or "").strip(), base_url, interval, 1 if body.get("enabled", True) else 0,
            1 if body.get("verifyTls", True) else 0, period)
    sid = body.get("id")
    if sid:
        cur = db.execute("SELECT token FROM perf_sources WHERE id = ?", (sid,)).fetchone()
        if not cur:
            raise ValueError("Unknown source.")
        token = body.get("token") if body.get("token") else cur[0]  # blank = keep the stored token
        if body.get("clearToken"):
            token = ""
        db.execute("UPDATE perf_sources SET customer_name=?, label=?, base_url=?, interval_hours=?, enabled=?, "
                   "verify_tls=?, period_hours=?, token=? WHERE id=?", vals + (token, sid))
    else:
        cur = db.execute("INSERT INTO perf_sources (customer_name, label, base_url, interval_hours, enabled, verify_tls, "
                         "period_hours, token, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         vals + ((body.get("token") or "").strip(), _now()))
        sid = cur.lastrowid
    db.commit()
    return sid


def delete_source(db, source_id):
    db.execute("DELETE FROM perf_sources WHERE id = ?", (source_id,))
    db.commit()


# ── pulling ────────────────────────────────────────────────────────────────────
def _open(url, token, verify_tls, timeout):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "ARIA-perf-integration"})
    if token:
        req.add_header("Authorization", "Bearer " + token)
    ctx = None
    if url.startswith("https") and not verify_tls:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.urlopen(req, timeout=timeout, context=ctx)


def _explain(exc):
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 401:
            return "StoragePerf rejected the token (HTTP 401). Check the ARIA export token in StoragePerf > Config."
        if exc.code == 404:
            return ("StoragePerf answered 404 for /api/aria/export -- it is running a version without the ARIA "
                    "integration (needs StoragePerf 0.21.0 or later).")
        return "StoragePerf returned HTTP %s." % exc.code
    if isinstance(exc, urllib.error.URLError):
        return "Could not reach StoragePerf: %s" % (getattr(exc, "reason", exc),)
    if isinstance(exc, (TimeoutError, ssl.SSLError)) or "timed out" in str(exc):
        return "StoragePerf did not answer in time (%s)." % exc
    return str(exc)


def test_source(base_url, token="", verify_tls=True):
    """GET /api/aria/info -- cheap connectivity/auth/version check."""
    base_url = normalize_base_url(base_url)
    try:
        with _open(base_url + "/api/aria/info", token, verify_tls, 20) as resp:
            info = json.loads(resp.read(1024 * 1024).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 -- surfaced to the user verbatim below
        return {"ok": False, "error": _explain(exc)}
    if not str(info.get("schema") or "").startswith(SCHEMA_PREFIX):
        return {"ok": False, "error": "That address answered, but it is not a StoragePerf with the ARIA integration."}
    return {"ok": True, "info": info}


def pull_source(db, source):
    """Fetch one source's export and store it. Returns the new snapshot id; raises ValueError with a
    user-presentable message on failure (and records it on the source row either way)."""
    url = "%s/api/aria/export?hours=%d" % (source["baseUrl"], int(source.get("periodHours") or 168))
    err = ""
    try:
        try:
            with _open(url, source.get("token", ""), source.get("verifyTls", True), PULL_TIMEOUT_S) as resp:
                raw = resp.read(MAX_PAYLOAD_BYTES + 1)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(_explain(exc))
        if len(raw) > MAX_PAYLOAD_BYTES:
            raise ValueError("The export is larger than %d MB; shorten the period." % (MAX_PAYLOAD_BYTES // 1048576))
        try:
            payload = json.loads(raw.decode("utf-8"))
        except ValueError:
            raise ValueError("StoragePerf answered, but not with JSON.")
        return store_snapshot(db, payload, source["customerName"], "pull", source_id=source["id"])
    except ValueError as exc:
        err = str(exc)
        raise
    finally:
        db.execute("UPDATE perf_sources SET last_pull_at=?, last_status=?, last_error=? WHERE id=?",
                   (_now(), "error" if err else "ok", err, source["id"]))
        db.commit()


def due_sources(db, now=None):
    now = now or datetime.now(timezone.utc)
    due = []
    for s in list_sources(db, include_token=True):
        if not s["enabled"] or s["intervalHours"] <= 0:
            continue
        if s["lastPullAt"]:
            try:
                last = datetime.fromisoformat(s["lastPullAt"])
                if (now - last).total_seconds() < s["intervalHours"] * 3600:
                    continue
            except ValueError:
                pass
        due.append(s)
    return due


class PerfPuller(threading.Thread):
    """Wakes every few minutes and pulls whichever sources are due. A source that keeps failing is retried
    at its normal interval (last_pull_at is stamped on failure too), so an unreachable customer never turns
    into a tight retry loop."""

    def __init__(self, open_db, tick_seconds=300):
        super().__init__(daemon=True, name="perf-puller")
        self._open_db = open_db
        self._tick = tick_seconds
        self._stop = threading.Event()

    def run(self):
        self._stop.wait(60)  # let startup finish first
        while not self._stop.is_set():
            try:
                db = self._open_db()
                try:
                    for src in due_sources(db):
                        try:
                            pull_source(db, src)
                            print("  [PERF] Pulled StoragePerf export for %s" % src["customerName"], flush=True)
                        except ValueError as exc:
                            print("  [PERF] Pull for %s failed: %s" % (src["customerName"], exc), flush=True)
                finally:
                    db.close()
            except Exception as exc:  # noqa: BLE001 -- the loop must never die
                print("  [PERF] Puller error: %s" % exc, flush=True)
            self._stop.wait(self._tick)

    def stop(self):
        self._stop.set()


def now_ms():
    return int(time.time() * 1000)
