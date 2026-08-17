"""
asup_parser.py - ARIA AutoSupport Bundle Import Parser
=======================================================
Parses NetApp AutoSupport (ASUP) bundles in any format (7z, tgz, zip, xml.gz, xml)
into ARIA normalized system schema for offline use when Active IQ is unreachable.
"""

import io
import os
import re
import json
import gzip
import tarfile
import zipfile
import tempfile
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

_CLUSTER_INFO_STEMS   = {"cluster-info", "clusterinfo", "cluster_info"}
_VERSION_STEMS        = {"version"}
_AGGR_STEMS           = {"aggr-status-r", "aggr-status", "aggr_status", "aggrstatusresponse"}
_DF_STEMS             = {"df-r", "df", "df-complete"}
_SYSCONFIG_STEMS      = {"sysconfig-a", "sysconfig"}
_SNAPMIRROR_STEMS     = {"snapmirror-get-status", "snapmirror_get_status", "snapmirror"}
_AUTOSUPPORT_STEMS    = {"autosupport", "autosupport-history"}
_HA_STEMS             = {"storage-failover", "ha-config"}
# ── Added from NetAppModeler's parser.js (ported, not copied — same source
# formats, translated to Python), see CHANGELOG "ASUP parser enhancements
# ported from NetAppModeler" ──────────────────────────────────────────────
_LICENSES_STEMS       = {"licenses", "license-show", "license_show", "cluster-licenses-v2-asup"}
_AGGR_INFO_STEMS      = {"aggr-info", "aggr_info"}
_SHELF_XML_STEMS      = {"storage-shelf", "storage_shelf"}
_SHELF_TXT_STEMS      = {"storage-shelf", "storage_shelf"}  # same file can carry both the XML ROWs and the text blocks

# Structured licenses.xml <package> name -> the canonical label ARIA/AIQ use
# elsewhere for the same feature (matches Active IQ's licenses.package values
# where they overlap, so the UI doesn't need two naming schemes).
_LICENSE_PACKAGE_NAMES = {
    "Base": "Cluster", "NFS": "NFS", "CIFS": "CIFS", "FCP": "FCP", "iSCSI": "iSCSI",
    "SnapMirror": "SnapMirror", "FlexClone": "FlexClone", "FabricPool": "FabricPool",
    "MetroCluster": "MetroCluster", "NVMe": "NVMe", "NVMe_tcp": "NVMe",
}
_KNOWN_SHELF_MODELS = {"DS2246", "DS4246", "DS4486", "DS224C", "DS460C", "DS212C", "DS212", "NS224", "NS212"}

def _try_7z(data_bytes, extract_dir):
    # ── Attempt 1: py7zr (pure-Python, no external binary needed) ──────────
    try:
        import py7zr
        with py7zr.SevenZipFile(io.BytesIO(data_bytes), mode="r") as z:
            z.extractall(path=extract_dir)
        return True, None
    except ImportError:
        pass
    except Exception as e:
        return False, f"py7zr: {e}"

    # ── Attempt 2: system 7z / 7-Zip CLI ────────────────────────────────────
    import subprocess, sys as _sys
    _7Z_CANDIDATES = ["7z", "7za"]
    # Common Windows 7-Zip install paths (both 64-bit and 32-bit)
    if _sys.platform == "win32":
        _7Z_CANDIDATES += [
            r"C:\Program Files\7-Zip\7z.exe",
            r"C:\Program Files (x86)\7-Zip\7z.exe",
        ]
    for cmd in _7Z_CANDIDATES:
        try:
            tmp = Path(extract_dir) / "_in.7z"
            tmp.write_bytes(data_bytes)
            r = subprocess.run([cmd, "x", str(tmp), f"-o{extract_dir}", "-y"],
                               capture_output=True, timeout=120)
            tmp.unlink(missing_ok=True)
            if r.returncode == 0:
                return True, None
        except FileNotFoundError:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            continue
        except Exception as e:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            return False, f"7z CLI ({cmd}): {e}"

    return False, ("7z unavailable. Install py7zr (`pip install py7zr`) or 7-Zip, "
                   "or extract the .7z manually and import the inner .tgz or .xml.")

def _extract_bundle(filename, data_bytes, extract_dir):
    fl = filename.lower()
    warnings = []
    if fl.endswith(".7z") or (len(data_bytes) >= 2 and data_bytes[:2] == b"7z"):
        ok, w = _try_7z(data_bytes, extract_dir)
        if not ok: return False, w, "unknown"
        if warnings: pass
        inner = Path(extract_dir) / "body.7z"
        if inner.exists():
            idir = Path(extract_dir) / "_body"; idir.mkdir(exist_ok=True)
            ok2, w2 = _try_7z(inner.read_bytes(), str(idir))
            if ok2:
                inner.unlink(missing_ok=True)
                for f in idir.iterdir(): shutil.move(str(f), extract_dir)
                try: idir.rmdir()
                except: pass
            else: warnings.append(f"Inner body.7z: {w2}")
        return True, "; ".join(warnings) or None, "ontap"
    if fl.endswith((".tgz", ".tar.gz", ".tar")):
        try:
            with tarfile.open(fileobj=io.BytesIO(data_bytes)) as t: t.extractall(extract_dir)
            members = [m.name.lower() for m in tarfile.open(fileobj=io.BytesIO(data_bytes)).getmembers()]
            hint = "storagegrid" if any("node-info" in m or "grid-health" in m for m in members) else "ontap"
            return True, None, hint
        except Exception as e: return False, f"tar: {e}", "unknown"
    if fl.endswith(".zip") or (len(data_bytes) >= 2 and data_bytes[:2] == b"PK"):
        try:
            with zipfile.ZipFile(io.BytesIO(data_bytes)) as z: z.extractall(extract_dir)
            names = [n.lower() for n in zipfile.ZipFile(io.BytesIO(data_bytes)).namelist()]
            hint = "eseries" if any("support-data" in n or "controller-info" in n for n in names) else "ontap"
            return True, None, hint
        except Exception as e: return False, f"zip: {e}", "unknown"
    if fl.endswith(".gz") and not fl.endswith((".tgz", ".tar.gz")):
        try:
            inner = gzip.decompress(data_bytes)
            (Path(extract_dir) / Path(fl[:-3]).name).write_bytes(inner)
            return True, None, "ontap"
        except Exception as e: return False, f"gzip: {e}", "unknown"
    if fl.endswith(".xml") or (len(data_bytes) >= 5 and data_bytes[:5] in (b"<?xml", b"<asup", b"<AUTO")):
        (Path(extract_dir) / "asup.xml").write_bytes(data_bytes)
        return True, None, "ontap"
    return False, f"Unsupported format '{filename}'. Supported: .7z .tgz .tar.gz .zip .xml .xml.gz .gz", "unknown"

def _build_file_index(extract_dir):
    index = {}
    manifest_info = {"truncated": [], "missing": []}
    for root, _dirs, files in os.walk(extract_dir):
        for fname in files:
            fp = Path(root) / fname
            for stem in [fp.stem.lower(), fp.stem.lower().replace("-","_"), fp.stem.lower().replace("_","-")]:
                index[stem] = fp
    for key, fp in list(index.items()):
        if "manifest" in key and fp.suffix.lower() == ".xml":
            try:
                for item in ET.parse(str(fp)).getroot().iter():
                    status = item.get("collection-status") or item.get("status") or ""
                    name   = item.get("name") or item.get("filename") or item.text or ""
                    if "truncat" in status.lower(): manifest_info["truncated"].append(name)
                    elif "error" in status.lower() or "fail" in status.lower(): manifest_info["missing"].append(name)
            except: pass
            break
    return index, manifest_info

def _find_file(index, stems):
    for s in stems:
        for v in [s, s.replace("-","_"), s.replace("_","-")]:
            if v in index:
                try: return index[v].read_bytes()
                except: pass
    return None

def _safe_xml(b):
    if not b: return None
    try:
        return ET.fromstring(b.decode("utf-8", errors="replace").lstrip("\ufeff"))
    except ET.ParseError:
        try:
            text = b.decode("utf-8", errors="replace")
            lc = text.rfind("</")
            if lc > 0:
                end = text.find(">", lc)
                if end > 0: return ET.fromstring(f"<root>{text[:end+1]}</root>")
        except: pass
    except: pass
    return None

def _safe_text(b): return b.decode("utf-8", errors="replace") if b else ""
def _pf(s, d=0.0):
    try: return float(str(s).replace(",","").strip())
    except: return d
def _kib_to_tb(kib): return round(kib / (1024**3), 2) if kib else 0.0

def _parse_cluster_info(b):
    root = _safe_xml(b)
    if root is None: return None
    def _ft(*tags):
        for t in tags:
            for el in root.iter(t):
                v = (el.text or "").strip()
                if v: return v
        return ""
    nodes = []
    for n in root.iter("node"):
        nn = (n.findtext("node-name") or n.findtext("name") or n.get("name") or "").strip()
        ns = (n.findtext("system-serial-number") or n.findtext("serial-number") or "").strip()
        if nn or ns: nodes.append({"nodeName": nn, "serialNumber": ns})
    r = {"clusterName": _ft("cluster-name","clusterName","name"),
         "serialNumber": _ft("system-serial-number","serialNumber","serial-number","serial"),
         "ontapVersion": _ft("version","ontap-version","os-version","softwareVersion"),
         "platform": _ft("system-type","platform","model","system-model"),
         "nodes": nodes, "nodeCount": len(nodes) if nodes else 1}
    return r if any(v for v in r.values() if v and v != 1) else None

def _parse_version_txt(b):
    text = _safe_text(b)
    m = re.search(r"NetApp Release\s+([\d.P]+)", text, re.IGNORECASE)
    if m: return m.group(1)
    m = re.search(r"\b(9\.\d+\.\d+(?:P\d+)?(?:RC\d+)?)\b", text)
    return m.group(1) if m else None

def _parse_sysconfig(b):
    text = _safe_text(b)
    r = {}
    m = re.search(r"(?:System Type|Model Name|Platform)[:\s]+([A-Z]{2,5}[-\s]?[A-Z0-9]+)", text, re.IGNORECASE)
    if m: r["platform"] = m.group(1).strip().upper().replace(" ","-")
    m = re.search(r"(\d+)\s+(?:disks?|drives?)\s+(?:installed|found|total)", text, re.IGNORECASE)
    if m: r["diskCount"] = int(m.group(1))
    return r if r else None

def _parse_aggr_status(b):
    aggrs = []
    root = _safe_xml(b)
    if root is not None:
        for a in root.iter("aggr-attributes"):
            name  = (a.findtext("aggregate-name") or a.findtext("name") or "").strip()
            state = (a.findtext("aggr-raid-attributes/state") or a.findtext("state") or "").strip()
            se = a.find("aggr-space-attributes")
            total = _pf((se.findtext("size-total")     if se else "") or 0)
            used  = _pf((se.findtext("size-used")      if se else "") or 0)
            avail = _pf((se.findtext("size-available") if se else "") or 0)
            if name: aggrs.append({"name":name,"state":state,"totalKiB":total/1024,"usedKiB":used/1024,"availKiB":avail/1024})
        if aggrs: return aggrs
    text = _safe_text(b)
    _mul = {"KB":1,"MB":1024,"GB":1024**2,"TB":1024**3}
    pat = re.compile(r"^(\S+)\s+(\w+)\s+([\d.]+)\s*([TGMK]B)\s+([\d.]+)\s*([TGMK]B)\s+([\d.]+)\s*([TGMK]B)", re.MULTILINE|re.IGNORECASE)
    for m in pat.finditer(text):
        aggrs.append({"name":m.group(1),"state":m.group(2),
                      "totalKiB":_pf(m.group(3))*_mul.get(m.group(4).upper(),1),
                      "usedKiB": _pf(m.group(5))*_mul.get(m.group(6).upper(),1),
                      "availKiB":_pf(m.group(7))*_mul.get(m.group(8).upper(),1)})
    return aggrs if aggrs else None

def _parse_df(b):
    root = _safe_xml(b); vols = []
    if root is not None:
        for v in root.iter("volume-attributes"):
            used  = _pf(v.findtext("volume-space-attributes/size-used") or 0)
            avail = _pf(v.findtext("volume-space-attributes/size-available") or 0)
            vols.append({"usedKiB":used/1024,"availKiB":avail/1024})
        if vols: return {"volumeCount":len(vols),"totalUsedKiB":sum(v["usedKiB"] for v in vols),"totalAvailKiB":sum(v["availKiB"] for v in vols)}
    text = _safe_text(b)
    for m in re.finditer(r"^\S+\s+(\d+)\s+(\d+)\s+(\d+)", text, re.MULTILINE):
        vols.append({"totalKiB":int(m.group(1)),"usedKiB":int(m.group(2)),"availKiB":int(m.group(3))})
    if vols: return {"volumeCount":len(vols),"totalUsedKiB":sum(v["usedKiB"] for v in vols),"totalAvailKiB":sum(v["availKiB"] for v in vols)}
    return None

def _parse_snapmirror(b):
    rels = []; root = _safe_xml(b)
    if root is not None:
        for sm in root.iter("snapmirror-info"):
            rels.append({"source":(sm.findtext("source-location") or "").strip(),
                         "destination":(sm.findtext("destination-location") or "").strip(),
                         "state":(sm.findtext("mirror-state") or sm.findtext("state") or "").strip(),
                         "lagSeconds":_pf(sm.findtext("lag-time") or 0)})
        if rels: return rels
    for m in re.finditer(r"(\S+:\S+)\s+(\S+:\S+)\s+(\w+)\s+([\d:]+)", _safe_text(b), re.MULTILINE):
        pts = (m.group(4).split(":")+["0","0"])[:3]
        rels.append({"source":m.group(1),"destination":m.group(2),"state":m.group(3),"lagSeconds":int(pts[0])*3600+int(pts[1])*60+int(pts[2])})
    return rels if rels else None

def _parse_autosupport_xml(b):
    root = _safe_xml(b)
    if root is None: return None
    r = {"enabled":(root.findtext(".//autosupport-enabled") or root.findtext(".//is-enabled") or "").strip().lower() in ("true","1","yes","on"),
         "transport":(root.findtext(".//transport") or root.findtext(".//autosupport-transport") or "").strip(),
         "lastSent":(root.findtext(".//last-timestamp") or root.findtext(".//timestamp") or "").strip(),
         "onDemand":(root.findtext(".//is-ondemand-enabled") or "").strip().lower() in ("true","1")}
    return r if any(r.values()) else None

def _parse_ha(b):
    text = _safe_text(b).lower()
    if not text: return None
    if "takeover is possible" in text or "storage failover is enabled" in text: return True
    if "takeover is disabled" in text or "storage failover is disabled" in text: return False
    if re.search(r"partner.*(?:ready|connected)", text): return True
    return None

def _parse_licenses_xml(b):
    """Structured cluster_licenses_v2_asup export (licenses.xml). Ported from
    NetAppModeler's parser.js: some real ASUP bundles carry NO plain-text
    "license show" CLI output at all, only this XML — a bundle with only that
    format previously left every license unreported. Returns a list of
    {"package": <canonical name>, "status": "active"|"expired", "details": str}
    or None if no recognized <asup:ROW> license entries are found.
    """
    text = _safe_text(b)
    if not text:
        return None
    licenses = []
    for row in re.finditer(r"<asup:ROW\b[^>]*>(.*?)</asup:ROW>", text, re.DOTALL | re.IGNORECASE):
        row_text = row.group(1)
        pkg_m = re.search(r"<package>([^<]+)</package>", row_text)
        type_m = re.search(r"<type>([^<]+)</type>", row_text)
        if not pkg_m or not type_m:
            continue
        canonical = _LICENSE_PACKAGE_NAMES.get(pkg_m.group(1).strip())
        if not canonical:
            continue  # not a package this system's UI tracks (e.g. SnapRestore)
        status, details = "active", ""
        if type_m.group(1).strip() == "demo":
            # Demo/eval entitlements carry an "expires" date inside an escaped-JSON
            # entitlement-info blob rather than a real permanent grant.
            exp_m = re.search(r'&quot;expires&quot;\s*:\s*&quot;([^&]+)&quot;', row_text)
            if exp_m:
                try:
                    exp_date = datetime.fromisoformat(exp_m.group(1).strip().replace("Z", "+00:00"))
                    if exp_date.tzinfo is None:
                        exp_date = exp_date.replace(tzinfo=timezone.utc)
                    if exp_date < datetime.now(timezone.utc):
                        status, details = "expired", f"Expired: {exp_m.group(1).strip()}"
                except Exception:
                    pass
        existing = next((l for l in licenses if l["package"].upper() == canonical.upper()), None)
        if existing:
            existing["status"], existing["details"] = status, details
        else:
            licenses.append({"package": canonical, "status": status, "details": details})
    return licenses or None

def _parse_aggr_info_xml(b):
    """Structured aggr-info.xml export. Ported from NetAppModeler's parser.js:
    "aggr status -r" (the primary aggregate parse in _parse_aggr_status) only
    ever carries RAID/disk membership, never capacity numbers, on some real
    bundles — this file has authoritative <name>/<size>/<available_size>/
    <usedsize> fields in bytes per <asup:ROW> (size == available_size +
    usedsize, verified byte-for-byte against real data). Returns
    {aggr_name: {"totalKiB", "usedKiB", "availKiB"}} or None.
    """
    text = _safe_text(b)
    if not text:
        return None
    out = {}
    for row in re.finditer(r"<asup:ROW\b[^>]*>(.*?)</asup:ROW>", text, re.DOTALL | re.IGNORECASE):
        row_text = row.group(1)
        name_m = re.search(r"<name>([^<]+)</name>", row_text)
        size_m = re.search(r"<size>(\d+)</size>", row_text)
        avail_m = re.search(r"<available_size>(\d+)</available_size>", row_text)
        used_m = re.search(r"<usedsize>(\d+)</usedsize>", row_text)
        if name_m and size_m and avail_m and used_m:
            out[name_m.group(1).strip()] = {
                "totalKiB": int(size_m.group(1)) / 1024,
                "usedKiB": int(used_m.group(1)) / 1024,
                "availKiB": int(avail_m.group(1)) / 1024,
            }
    return out or None

def _parse_sas_host_adapters(b):
    """Onboard SAS storage ports from a `sysconfig -a`-style dump. Ported from
    NetAppModeler's parser.js: lines like "slot 0: SAS Host Adapter 0a
    (PMC-Sierra PM8001 rev. C, SAS, <UP>)" are a different line shape than
    Ethernet "port <name> <up|down> ..." lines, so a generic port parser never
    catches them — confirmed against a real customer bundle where a platform's
    static port-count catalog entry (2 ports) was wrong versus the real ASUP
    (4 real SAS Host Adapters). Returns a list of {"name", "status"} ("up"/
    "down") or None. This does not attempt per-node attribution (AIQscraper's
    schema is cluster/system-level, not the multi-node text-block model
    NetAppModeler's UI needs) -- every adapter found in the dump is returned.
    """
    text = _safe_text(b)
    if not text:
        return None
    ports = []
    seen = set()
    for m in re.finditer(r"SAS Host Adapter\s+(\S+)\s*\([^)]*<(UP|DOWN)>[^)]*\)", text, re.IGNORECASE):
        name = m.group(1).strip()
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        ports.append({"name": name, "status": m.group(2).strip().lower()})
    return ports or None

def _parse_shelves(shelf_xml_bytes, shelf_txt_bytes):
    """Disk shelf inventory. Ported from NetAppModeler's parser.js Pass 6:
    STORAGE-SHELF.txt's "Shelf name:/Shelf id:/Shelf S/N:" key-value format is,
    on some real bundles, the ONLY shelf-listing format present (no SES
    Configuration blocks). That format alone has no model field; storage-
    shelf.xml's <product_id>/<serial_number> pairs (adjacent per its own field
    order) cross-reference by serial number to recover the model. Both files
    are commonly the same underlying ASUP file under different stems, so both
    byte blobs are passed in and treated as one combined text. Returns a list
    of {"id", "model", "serialNumber"} or None.
    """
    combined = (_safe_text(shelf_xml_bytes) or "") + "\n" + (_safe_text(shelf_txt_bytes) or "")
    if not combined.strip():
        return None

    product_id_by_serial = {}
    for m in re.finditer(r"<product_id>([^<]*)</product_id>\s*<serial_number>([^<]*)</serial_number>",
                          combined, re.IGNORECASE):
        pid, serial = m.group(1).strip(), m.group(2).strip()
        if pid and serial:
            product_id_by_serial[serial] = pid

    def _resolve_model(product_id):
        if not product_id:
            return None
        stripped = re.sub(r"-\d+$", "", product_id).upper()
        if stripped in _KNOWN_SHELF_MODELS:
            return stripped
        if (stripped + "C") in _KNOWN_SHELF_MODELS:
            return stripped + "C"
        return stripped

    shelves = []
    seen_serials = set()
    for m in re.finditer(
        r"Shelf name:\s*(\S+)\s*[\r\n]+\s*Shelf id:\s*(\d+)[\s\S]{0,200}?Shelf S/N:\s*(\S+)",
        combined, re.IGNORECASE,
    ):
        shelf_id, serial = m.group(2).strip(), m.group(3).strip()
        if serial in seen_serials:
            continue  # same physical shelf reported again via the other IOM module
        seen_serials.add(serial)
        model = _resolve_model(product_id_by_serial.get(serial))
        shelves.append({"id": shelf_id, "model": model or "Unknown", "serialNumber": serial})
    return shelves or None

def _parse_storagegrid_bundle(extract_dir):
    r = {}
    for fp in Path(extract_dir).rglob("*.json"):
        try: data = json.loads(fp.read_text("utf-8", errors="replace"))
        except: continue
        stem = fp.stem.lower()
        if any(s in stem for s in ("node","grid","health")):
            if isinstance(data, dict):
                r.setdefault("clusterName",  data.get("gridName") or data.get("name") or "")
                r.setdefault("serialNumber", data.get("serialNumber") or data.get("id") or "")
                r.setdefault("sgVersion",    data.get("storagegridVersion") or data.get("version") or "")
                r.setdefault("nodeCount",    len(data.get("nodes",[])))
            elif isinstance(data,list): r.setdefault("nodeCount", len(data))
        if "capacity" in stem or "storage" in stem:
            if isinstance(data, dict):
                r.setdefault("rawCapacityBytes",  data.get("rawCapacity") or data.get("totalRawCapacity") or 0)
                r.setdefault("usedCapacityBytes", data.get("usedCapacity") or 0)
    return r if r else None

def _parse_eseries_bundle(extract_dir):
    r = {}
    for fp in Path(extract_dir).rglob("*.xml"):
        root = _safe_xml(fp.read_bytes())
        if root is None: continue
        stem = fp.stem.lower()
        if any(s in stem for s in ("support","config","controller","system")):
            r.setdefault("clusterName",  (root.findtext(".//storage-system-name") or root.findtext(".//array-name") or "").strip())
            r.setdefault("serialNumber", (root.findtext(".//serial-number") or root.findtext(".//chassis-serial-number") or "").strip())
            r.setdefault("santricity",   (root.findtext(".//firmware-version") or root.findtext(".//osVersion") or "").strip())
            r.setdefault("platform",     (root.findtext(".//model-number") or root.findtext(".//model") or "").strip())
            tb = root.find(".//total-storage-configured")
            if tb is not None and tb.text: r.setdefault("rawCapacityBytes", _pf(tb.text) * (1024**4))
    for fp in Path(extract_dir).rglob("*.json"):
        try: data = json.loads(fp.read_text("utf-8", errors="replace"))
        except: continue
        if isinstance(data, dict):
            r.setdefault("clusterName",  data.get("name") or "")
            r.setdefault("serialNumber", data.get("chassisSerialNumber") or "")
            r.setdefault("platform",     data.get("model") or "")
    return r if r else None

def _build_system_dict(cluster, sysconfig, aggrs, df_info, snapmirrors,
                        asup_info, ha_config, customer_name, product_hint,
                        sg_info, eseries_info, version_str,
                        licenses=None, aggr_info_capacity=None, shelves=None, sas_ports=None):
    now = datetime.now(timezone.utc).isoformat()
    if product_hint == "storagegrid" and sg_info:
        sys_name=sg_info.get("clusterName") or "StorageGRID"; serial=sg_info.get("serialNumber") or f"SG-{now[:10]}"
        os_version=sg_info.get("sgVersion") or ""; platform="StorageGRID"; node_count=sg_info.get("nodeCount") or 1
        raw_kib=(sg_info.get("rawCapacityBytes") or 0)/1024; used_kib=(sg_info.get("usedCapacityBytes") or 0)/1024
    elif product_hint == "eseries" and eseries_info:
        sys_name=eseries_info.get("clusterName") or "E-Series"; serial=eseries_info.get("serialNumber") or f"ES-{now[:10]}"
        os_version=eseries_info.get("santricity") or ""; platform=eseries_info.get("platform") or "E-Series"; node_count=2
        raw_kib=(eseries_info.get("rawCapacityBytes") or 0)/1024; used_kib=0.0
    else:
        c=cluster or {}; sc=sysconfig or {}
        sys_name=c.get("clusterName") or ""; serial=c.get("serialNumber") or f"ASUP-{now[:10]}"
        os_version=version_str or c.get("ontapVersion") or ""; platform=sc.get("platform") or c.get("platform") or ""
        node_count=c.get("nodeCount") or 1
        # aggr-info.xml (structured, byte-accurate) overrides "aggr status -r" text-parsed
        # capacity per aggregate by name — some real bundles carry only the RAID/disk-
        # membership text dump (no capacity numbers at all), which aggr-info.xml alone has.
        if aggr_info_capacity and aggrs:
            for a in aggrs:
                override = aggr_info_capacity.get(a.get("name"))
                if override:
                    a.update(override)
        elif aggr_info_capacity and not aggrs:
            aggrs = [{"name": name, **caps} for name, caps in aggr_info_capacity.items()]
        raw_kib=sum(a.get("totalKiB",0) for a in (aggrs or [])); used_kib=sum(a.get("usedKiB",0) for a in (aggrs or []))
        if not raw_kib and df_info:
            used_kib=df_info.get("totalUsedKiB",0); avail_kib=df_info.get("totalAvailKiB",0); raw_kib=used_kib+avail_kib
    util_pct=round((used_kib/raw_kib*100) if raw_kib else 0, 1); asup=asup_info or {}
    return {
        "systemName":sys_name,"customerName":customer_name or sys_name or "Offline Import",
        "serialNumber":serial,"clusterName":sys_name,"osVersion":os_version,"platform":platform,
        "nodeCount":node_count,"productType":product_hint,
        "clusterRawCapacityTB":_kib_to_tb(raw_kib),"clusterUsableCapacityTB":_kib_to_tb(raw_kib),
        "clusterPhysicalUsedTB":_kib_to_tb(used_kib),"clusterLogicalUsedTB":None,
        "clusterCapacityUtilPct":util_pct,"capacityUsedKB":round(used_kib),
        "capacityAvailableKB":round(max(0,raw_kib-used_kib)),"capacityAllocatedKB":0,
        "dataReductionRatio":None,"clusterQoQUtilPct":None,"clusterYoYUtilPct":None,
        "clusterCapacityReportedOn":now[:10],"clusterMonthlyCapacity":[],
        "isHAConfigured":ha_config,"snapMirrorCount":len(snapmirrors) if snapmirrors else 0,
        "snapMirrorRelationships":snapmirrors or [],
        "asupStatus":"enabled" if asup.get("enabled") else ("disabled" if asup_info else None),
        "asupTransport":asup.get("transport") or None,"asupOnDemand":asup.get("onDemand") or None,
        "latestAsupDate":asup.get("lastSent") or now[:10],"latestAsupSubject":"ARIA Offline Import",
        "latestAsupType":"manual","latestAsupIsManual":True,"latestAsupId":"","asupHistory":[],"asupByType":[],
        "isARPEnabled":None,"isMetroCluster":None,"isAllFlashOptimized":None,"isFlexPod":None,"autoUpdateEnabled":None,
        "contractActive":None,"contractEndDate":None,"contractHWEndDate":None,"contractSWEndDate":None,
        "warrantyEndDate":None,"serviceLevel":None,"hwEndOfAvailability":None,"hwEndOfSupport":None,"eosEarliest":None,
        "swRecMin":None,"swRecLatest":None,"swEndOfFullSupport":None,"swEndOfLimitedSupport":None,"swEndOfSelfService":None,
        "risks":[],"cases":[],"securityBulletins":[],"lifecycleEvents":[],"pvrs":[],"licenses":licenses or [],
        "efficiencyRatio":None,"dataReductionRatioSys":None,"savedKiB":None,"dedupSavedKiB":None,"compactionSavedKiB":None,
        "shelves":shelves or [],"switches":[],"systemFirmware":[],"portInterface":{},"networkPorts":{},"vcenters":[],
        # SAS Host Adapter ports parsed directly from sysconfig -a text (see
        # _parse_sas_host_adapters) -- deliberately a separate honest field, not
        # shoehorned into "networkPorts" (that field's real-API shape is Ethernet-
        # only: CLUSTER/DATA/etc. roles) or "portInterface" (ONTAP's onboard-port/
        # adapter-card schema, which this text format doesn't map onto cleanly).
        "storagePorts":sas_ports or [],
        "sustainabilityScores":[],"monthlyUptimeStats":[],"monthlyCarbonStats":[],"monthlyResolvedRisksStats":[],
        "monthlyArpStats":[],"monthlyAutoResolvedCases":[],"downtimeEvents":{},"sazTotalRawKiB":0,"sazUsedKiB":0,"sazAvailableKiB":0,
        "_source":"asup_import","_importedAt":now,"_asupFilename":"",
    }

def _build_coverage(cluster, sysconfig, aggrs, df_info, snapmirrors,
                    asup_info, ha_config, sg_info, eseries_info, version_str, manifest_info, warnings,
                    licenses=None, shelves=None, sas_ports=None):
    c=cluster or {}; sc=sysconfig or {}
    sections=[
        {"label":"System Identity (name, serial)","found":bool(c.get("clusterName") or (sg_info or {}).get("clusterName") or (eseries_info or {}).get("clusterName"))},
        {"label":"OS / Firmware Version","found":bool(version_str or c.get("ontapVersion") or (sg_info or {}).get("sgVersion") or (eseries_info or {}).get("santricity"))},
        {"label":"Platform Model","found":bool(sc.get("platform") or c.get("platform") or (eseries_info or {}).get("platform"))},
        {"label":"Capacity Data (aggr/volumes)","found":bool(aggrs or df_info or (sg_info or {}).get("rawCapacityBytes"))},
        {"label":"HA Configuration","found":ha_config is not None,"note":"N/A for StorageGRID/E-Series" if (sg_info or eseries_info) else ""},
        {"label":"SnapMirror Relationships","found":bool(snapmirrors)},
        {"label":"AutoSupport Config","found":bool(asup_info)},
        {"label":"Software Licenses","found":bool(licenses),"note":"N/A for StorageGRID/E-Series" if (sg_info or eseries_info) else ""},
        {"label":"Disk Shelf Inventory","found":bool(shelves),"note":"N/A for StorageGRID/E-Series" if (sg_info or eseries_info) else ""},
        {"label":"SAS Storage Ports","found":bool(sas_ports),"note":"N/A for StorageGRID/E-Series" if (sg_info or eseries_info) else ""},
    ]
    unavailable=[
        {"label":"Support Cases","reason":"Requires Active IQ API"},
        {"label":"Contract / Lifecycle","reason":"Requires Active IQ API"},
        {"label":"Account Personnel","reason":"Requires Active IQ API (CRM)"},
        {"label":"Risk Scores","reason":"Requires Active IQ API (NetApp-computed)"},
        {"label":"Recommendations","reason":"Requires Active IQ API"},
    ]
    computed=[
        {"label":"CVE / Security Advisory Matching","note":"Matched from OS version by Reference Library"},
        {"label":"Upgrade Path Calculation","note":"Computed from OS version by ARIA engine"},
        {"label":"EOA / Hardware Detection","note":"Computed from platform by Reference Library"},
        {"label":"TAM/MSP 15-Point Readiness","note":"Partial; AIQ-dependent checks show N/A"},
    ]
    return {"sections":sections,"unavailable":unavailable,"computed":computed,
            "truncated":manifest_info.get("truncated",[]),"warnings":warnings}

def parse_bundle(filename, data_bytes, customer_name=""):
    """Main entry point. Returns {ok, system, coverage, warnings, error}."""
    warnings=[]; extract_dir=tempfile.mkdtemp(prefix="aria_asup_")
    try:
        ok, extract_warn, product_hint = _extract_bundle(filename, data_bytes, extract_dir)
        if extract_warn: warnings.append(extract_warn)
        if not ok: return {"ok":False,"system":None,"coverage":{},"warnings":warnings,"error":extract_warn}
        index, manifest_info = _build_file_index(extract_dir)
        sg_info=eseries_info=cluster=sysconfig=None; aggrs=df_info=snapmirrors=asup_info=None; ha_config=version_str=None
        if product_hint == "storagegrid":
            sg_info = _parse_storagegrid_bundle(extract_dir)
            if not sg_info: warnings.append("No recognisable StorageGRID data found.")
        elif product_hint == "eseries":
            eseries_info = _parse_eseries_bundle(extract_dir)
            if not eseries_info: warnings.append("No recognisable E-Series data found.")
        else:
            def _tp(stems, parser, label):
                raw = _find_file(index, stems)
                if raw is None: return None
                try:
                    r = parser(raw)
                    if r is None: warnings.append(f"{label}: found but unparseable")
                    return r
                except Exception as e: warnings.append(f"{label}: {e}"); return None
            cluster     = _tp(_CLUSTER_INFO_STEMS, _parse_cluster_info,    "CLUSTER-INFO")
            sysconfig   = _tp(_SYSCONFIG_STEMS,    _parse_sysconfig,       "SYSCONFIG")
            aggrs       = _tp(_AGGR_STEMS,          _parse_aggr_status,    "AGGR-STATUS")
            df_info     = _tp(_DF_STEMS,            _parse_df,             "DF")
            snapmirrors = _tp(_SNAPMIRROR_STEMS,    _parse_snapmirror,     "SNAPMIRROR")
            asup_info   = _tp(_AUTOSUPPORT_STEMS,   _parse_autosupport_xml,"AUTOSUPPORT")
            licenses    = _tp(_LICENSES_STEMS,      _parse_licenses_xml,   "LICENSES")
            aggr_info_capacity = _tp(_AGGR_INFO_STEMS, _parse_aggr_info_xml, "AGGR-INFO")
            ha_raw=_find_file(index,_HA_STEMS); ha_config=_parse_ha(ha_raw) if ha_raw else None
            ver_raw=_find_file(index,_VERSION_STEMS); version_str=_parse_version_txt(ver_raw) if ver_raw else None
            # Same file commonly carries both the shelf XML <product_id>/<serial_number>
            # rows and the "Shelf name:/id:/S/N:" text blocks under one stem.
            shelf_raw = _find_file(index, _SHELF_XML_STEMS)
            try:
                shelves = _parse_shelves(shelf_raw, shelf_raw)
                if shelf_raw is not None and shelves is None:
                    warnings.append("STORAGE-SHELF: found but unparseable")
            except Exception as e:
                warnings.append(f"STORAGE-SHELF: {e}"); shelves = None
            # SAS Host Adapter ports need the raw sysconfig text (the already-parsed
            # `sysconfig` dict above only keeps platform/disk-count, not port lines).
            sysconfig_raw = _find_file(index, _SYSCONFIG_STEMS)
            try:
                sas_ports = _parse_sas_host_adapters(sysconfig_raw) if sysconfig_raw else None
            except Exception as e:
                warnings.append(f"SAS-ADAPTERS: {e}"); sas_ports = None
            if not cluster and not sysconfig and not aggrs:
                sg_test=_parse_storagegrid_bundle(extract_dir)
                if sg_test: sg_info=sg_test; product_hint="storagegrid"
                else:
                    es_test=_parse_eseries_bundle(extract_dir)
                    if es_test: eseries_info=es_test; product_hint="eseries"
                    else: warnings.append("No recognisable ONTAP/StorageGRID/E-Series data. Bundle may be incomplete.")
        system=_build_system_dict(cluster,sysconfig,aggrs,df_info,snapmirrors,asup_info,ha_config,
                                   customer_name,product_hint,sg_info,eseries_info,version_str,
                                   licenses=locals().get("licenses"), aggr_info_capacity=locals().get("aggr_info_capacity"),
                                   shelves=locals().get("shelves"), sas_ports=locals().get("sas_ports"))
        system["_asupFilename"]=filename
        if not customer_name: system["customerName"]=system.get("clusterName") or Path(filename).stem
        coverage=_build_coverage(cluster,sysconfig,aggrs,df_info,snapmirrors,asup_info,ha_config,
                                  sg_info,eseries_info,version_str,manifest_info,warnings,
                                  licenses=locals().get("licenses"), shelves=locals().get("shelves"),
                                  sas_ports=locals().get("sas_ports"))
        return {"ok":True,"system":system,"coverage":coverage,"warnings":warnings,"error":None}
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)
