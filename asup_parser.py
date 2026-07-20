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

def _try_7z(data_bytes, extract_dir):
    try:
        import py7zr
        with py7zr.SevenZipFile(io.BytesIO(data_bytes), mode="r") as z:
            z.extractall(path=extract_dir)
        return True, None
    except ImportError:
        pass
    except Exception as e:
        return False, f"py7zr: {e}"
    try:
        import subprocess
        tmp = Path(extract_dir) / "_in.7z"
        tmp.write_bytes(data_bytes)
        r = subprocess.run(["7z", "x", str(tmp), f"-o{extract_dir}", "-y"], capture_output=True, timeout=120)
        tmp.unlink(missing_ok=True)
        if r.returncode == 0:
            return True, None
        return False, f"7z exit {r.returncode}"
    except FileNotFoundError:
        pass
    except Exception as e:
        return False, f"7z CLI: {e}"
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
                        sg_info, eseries_info, version_str):
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
        "risks":[],"cases":[],"securityBulletins":[],"lifecycleEvents":[],"pvrs":[],"licenses":[],
        "efficiencyRatio":None,"dataReductionRatioSys":None,"savedKiB":None,"dedupSavedKiB":None,"compactionSavedKiB":None,
        "shelves":[],"switches":[],"systemFirmware":[],"portInterface":{},"networkPorts":{},"vcenters":[],
        "sustainabilityScores":[],"monthlyUptimeStats":[],"monthlyCarbonStats":[],"monthlyResolvedRisksStats":[],
        "monthlyArpStats":[],"monthlyAutoResolvedCases":[],"downtimeEvents":{},"sazTotalRawKiB":0,"sazUsedKiB":0,"sazAvailableKiB":0,
        "_source":"asup_import","_importedAt":now,"_asupFilename":"",
    }

def _build_coverage(cluster, sysconfig, aggrs, df_info, snapmirrors,
                    asup_info, ha_config, sg_info, eseries_info, version_str, manifest_info, warnings):
    c=cluster or {}; sc=sysconfig or {}
    sections=[
        {"label":"System Identity (name, serial)","found":bool(c.get("clusterName") or (sg_info or {}).get("clusterName") or (eseries_info or {}).get("clusterName"))},
        {"label":"OS / Firmware Version","found":bool(version_str or c.get("ontapVersion") or (sg_info or {}).get("sgVersion") or (eseries_info or {}).get("santricity"))},
        {"label":"Platform Model","found":bool(sc.get("platform") or c.get("platform") or (eseries_info or {}).get("platform"))},
        {"label":"Capacity Data (aggr/volumes)","found":bool(aggrs or df_info or (sg_info or {}).get("rawCapacityBytes"))},
        {"label":"HA Configuration","found":ha_config is not None,"note":"N/A for StorageGRID/E-Series" if (sg_info or eseries_info) else ""},
        {"label":"SnapMirror Relationships","found":bool(snapmirrors)},
        {"label":"AutoSupport Config","found":bool(asup_info)},
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
            ha_raw=_find_file(index,_HA_STEMS); ha_config=_parse_ha(ha_raw) if ha_raw else None
            ver_raw=_find_file(index,_VERSION_STEMS); version_str=_parse_version_txt(ver_raw) if ver_raw else None
            if not cluster and not sysconfig and not aggrs:
                sg_test=_parse_storagegrid_bundle(extract_dir)
                if sg_test: sg_info=sg_test; product_hint="storagegrid"
                else:
                    es_test=_parse_eseries_bundle(extract_dir)
                    if es_test: eseries_info=es_test; product_hint="eseries"
                    else: warnings.append("No recognisable ONTAP/StorageGRID/E-Series data. Bundle may be incomplete.")
        system=_build_system_dict(cluster,sysconfig,aggrs,df_info,snapmirrors,asup_info,ha_config,
                                   customer_name,product_hint,sg_info,eseries_info,version_str)
        system["_asupFilename"]=filename
        if not customer_name: system["customerName"]=system.get("clusterName") or Path(filename).stem
        coverage=_build_coverage(cluster,sysconfig,aggrs,df_info,snapmirrors,asup_info,ha_config,
                                  sg_info,eseries_info,version_str,manifest_info,warnings)
        return {"ok":True,"system":system,"coverage":coverage,"warnings":warnings,"error":None}
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)
