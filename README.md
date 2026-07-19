# NetApp Active IQ Advisor Dashboard

[![Version](https://img.shields.io/badge/version-3.3.1-0066cc)](CHANGELOG.md)
[![License](https://img.shields.io/badge/license-Proprietary-red)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-3776AB?logo=python&logoColor=white)]()
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)]()
[![AI Free](https://img.shields.io/badge/AI--Free-100%25-critical)]()

> **One tool. Your entire fleet. Customer-ready deliverables. In under two minutes.**
>
> Built for NetApp Technical Account Managers, Sales Engineers, and Managed Service Providers who need to walk into every customer meeting fully prepared — with real data, real risks, and ready-to-share reports.

---

## Table of Contents

1. [Why This Tool — vs. Active IQ Directly](#1-why-this-tool--vs-active-iq-directly)
2. [What It Delivers](#2-what-it-delivers)
3. [Use Cases](#3-use-cases)
4. [Getting Started](#4-getting-started)
5. [Dashboard Guide](#5-dashboard-guide)
6. [Action Planner — All 15 Sections](#6-action-planner--all-15-sections)
7. [Downloadable Deliverables](#7-downloadable-deliverables)
8. [Security & Data Privacy](#8-security--data-privacy)
9. [Troubleshooting](#9-troubleshooting)
10. [Internal Architecture](#10-internal-architecture) *(Addendum — for developers)*
11. [Legal & Intellectual Property](#11-legal--intellectual-property)

---

## 1. Why This Tool — vs. Active IQ Directly

Active IQ is excellent for monitoring a single customer. This tool is built for TAMs, SEs, and MSPs who manage **multiple customers and large mixed portfolios** — where Active IQ's UI quickly becomes a bottleneck.

### What Active IQ gives you

- A web dashboard scoped to one customer at a time
- Risks, advisories, and capacity alerts for systems you navigate to manually
- Case history and contract dates — per system, per customer
- Sustainability scores and recommendations

### What this tool adds on top

| Gap in Active IQ | What the Advisor Dashboard does |
|---|---|
| **One customer at a time** — you must manually switch contexts and re-filter for every account | **Cross-customer fleet view** — all customers, all systems in a single pane. Filter to any customer in one click |
| **No deliverable generation** — you take screenshots or copy/paste into documents | **Six ready-to-share deliverables** — QBR Pack, Customer Success Plan, MSP Report, Handover Brief, CLI Runbook — generated in seconds |
| **No upgrade path calculator** — AIQ shows your current version; you have to figure out the hop sequence yourself | **Automatic hop-by-hop upgrade paths** — direct paths where available; multi-hop sequences with intermediate versions and per-version notes for ONTAP, StorageGRID, and SANtricity |
| **CVE matching is generic** — you see advisories but must manually check which of your systems are actually affected | **Per-system CVE cross-referencing** — every system's ONTAP version is tested against **tracked CVEs** (from MITRE, NVD, CISA KEV, NetApp PSIRT, GitHub) with CVSS scores, affected ranges, fix versions, and exact CLI remediation steps. Includes 2 CISA KEV-confirmed actively exploited entries. |
| **Capacity trend is per-system** — no fleet-wide growth rate or cross-customer runway view | **Fleet-wide capacity projection** — 6-month historical trend, growth rate in GB/day, per-node breakdown, and runway estimate per node |
| **Efficiency includes snapshot savings** — the displayed ratio is inflated | **Correct data reduction ratio** — uses dedupe + compression only (no snapshots). Snapshot-inclusive ratio shown separately for reference |
| **No ITIL-aligned change control output** — risks are described but remediation isn't structured for change management | **CLI Runbook with ITIL tiers** — every remediation step classified as Non-Disruptive / Disruptive / Destructive, formatted as change tickets for CAB approval |
| **No Reference Library enrichment** — you must manually cross-reference EOA lists, firmware baselines, and MetroCluster ISL specs | **Automatic enrichment** — EOA hardware flags, firmware baseline checks, MetroCluster ISL validation, Kerberos AES detection, SnapMirror policy audit, etc |
| **No account handover support** — transitioning an account means extensive manual documentation | **Account Handover Brief** — structured briefing generated in one click covering fleet context, open risks, contracts, contacts, and pending actions |
| **ARP and ASUP health require individual system checks** — no fleet-wide audit | **Fleet-wide operational health** — ARP enablement, AutoSupport recency, firmware currency, and reboot timeline across all systems at once |
| **Sustainability requires per-customer navigation** | **Cross-customer ESG dashboard** — fleet sustainability score, carbon/energy data, and data reduction ratios all in one view |

### Where this tool is most effective

1. **Portfolio-level preparation** — walking into any QBR or account review with all data ready, not just the one customer you happened to check that morning
2. **Security posture triage** — instantly knowing which systems across all customers are affected by a new CVE, without clicking through each account individually
3. **Contract and renewal pipeline management** — surfacing all expiring contracts across the entire portfolio in one view, ranked by urgency
4. **MSP monthly reporting at scale** — generating per-customer service reports across 20+ customers in minutes rather than hours
5. **Change management readiness** — producing ITIL-formatted CLI runbooks for CAB submission, not just a list of risks

---

## 2. What It Delivers

In a single sync, the tool harvests your complete fleet telemetry from the Active IQ API, enriches it with a curated Reference Library, and renders it as a fully interactive dashboard with six downloadable customer-facing deliverables.

**Harvested from Active IQ:**
- Every system and cluster across your entire portfolio
- All open and resolved technical risks and advisories
- Support case history per system
- Contract status, expiry dates, and service tiers
- End-of-Availability and End-of-Support lifecycle milestones
- Sustainability and energy efficiency scores
- Capacity trends and storage efficiency ratios
- AutoSupport status, firmware currency, and Anti-Ransomware Protection (ARP) coverage
- OS version catalog for upgrade path calculation
- Account personnel (Sales Rep, CSM, SAM, ASP, Propensity)

**Added by the Reference Library (not in Active IQ):**
- EOA hardware flags for AFF, ASA, FAS, StorageGRID, and E-Series platforms
- **CVE cross-referencing** — Unique CVEs across advisory entries sourced from MITRE, NVD/NIST, CISA KEV, NetApp PSIRT, GitHub, and threat intelligence feeds. Per-system applicability matched by ONTAP version range.
- **CISA KEV integration** — CVEs confirmed as actively exploited by CISA are flagged with 🚨 priority in the dashboard. The set of flagged entries grows as new KEV additions are detected and the Reference Library is refreshed.
- Firmware baseline checks for shelves and switches
- MetroCluster ISL requirement validation
- Kerberos AES enforcement detection (Microsoft KB5073381)
- SnapMirror synchronous policy alignment audit
- Legacy firewall policy deprecation detection (ONTAP 9.10.1+)

---

## 3. Use Cases

### QBR / Account Review Preparation

**Goal:** Walk into a quarterly review with complete, accurate, customer-specific data — without spending the morning manually pulling information.

**Workflow:**
1. Select the customer from the sidebar filter dropdown
2. Click **Sync** (or use today's cached data)
3. Go to **Action Planner** → click **Generate**
4. Navigate to **Tab 9 → QBR Pack** → click **Generate QBR Pack**

**Output:** A QBR Pack containing KPI scorecard, risk trend, resolved cases, open action items, and upgrade roadmap — ready for the customer presentation.

---

### Security Posture Assessment

**Goal:** When a new CVE or ONTAP advisory is published, immediately know which systems across all customers are affected — not just the ones you happen to check.

**Workflow:**
1. Go to **Technical Audit** in the sidebar
2. The **Security Advisories** section lists all tracked CVEs with per-system applicability
3. Each entry shows: CVE ID, CVSS score, affected version range, fixed version, and the specific CLI command to remediate
4. Use **Action Planner → Tab 3** to produce a customer-scoped security advisory section

**Output:** A complete, system-level security exposure list across your entire portfolio, with remediation steps ready to go into a CLI Runbook.

---

### Capacity Planning & Runway Review

**Goal:** Know which systems are approaching capacity limits — per node, with actual growth rates, not just a percentage bar.

**Workflow:**
1. Go to **Value & ROI (CSM)** in the sidebar
2. The capacity chart defaults to **Aggregate** (fleet-wide). Click **Per Node** to see individual node trend lines
3. The **Capacity Breakdown by Node** table shows: Used TB, Raw TB, Utilisation %, Growth/day, and Runway per node
4. Nodes approaching limits are colour-coded amber (>70%) and red (>85%)

**Output:** A per-node capacity breakdown with runway estimates, sourced from actual monthly telemetry data — matching the chart data exactly.

---

### Contract & Renewal Pipeline

**Goal:** Surface all expiring contracts and EOA hardware across the portfolio to build a proactive renewal and tech refresh pipeline.

**Workflow:**
1. Go to **Action Planner → Tab 10** (Contracts & Lifecycle) for the full expiry view
2. Cross-reference with **Tab 14** (Contract Compliance) for hardware warranty and service tier status
3. Filter by customer or by urgency (expiring within 30/60/90 days)
4. Generate an **Account Handover Brief** or **Extended Deliverables** from Tab 9 for formal documentation

**Output:** A ranked contract renewal pipeline with EOA/EOS milestones, tech refresh status, and service tier breakdown.

---

### OS Upgrade Planning

**Goal:** For every system running a non-current ONTAP release, determine the exact upgrade path — including any required intermediate versions.

**Workflow:**
1. Go to **Action Planner → Tab 5** (OS Upgrades)
2. Each system shows its current version and the recommended target
3. Multi-hop paths display all intermediate versions with version-specific notes and pre/post checks
4. Use the **CLI Runbook** deliverable (Tab 9) to extract upgrade commands for change management submission

**Output:** A system-by-system upgrade roadmap with hop sequences, version notes, and ITIL-classified CLI steps.

---

### MSP Monthly Service Reporting

**Goal:** Generate per-customer monthly service reports across a large managed portfolio without manual data compilation.

**Workflow:**
1. Select the customer from the sidebar filter
2. Go to **Action Planner → Tab 9 → MSP Service Report**
3. Click **Generate MSP Service Report**

**Output:** A monthly service report with SLA metrics, case resolution summary, proactive actions taken, and risk posture change — one per customer, all client-side.

---

### New Account Onboarding / Handover

**Goal:** When assigned a new account, rapidly understand the full fleet context. When handing off, produce a structured briefing.

**Workflow:**
1. Sync the portfolio (all accounts come in together — no per-account setup)
2. Select the customer in the sidebar filter
3. Review **Tab 13** (Account Intelligence) for the personnel map and site inventory
4. Generate an **Account Handover Brief** from **Tab 9**

**Output:** A structured handover document covering fleet health, open risks, contract status, key contacts, and pending actions.

---

### EOA / Tech Refresh Planning

**Goal:** Identify all End-of-Availability hardware across the portfolio before EOS dates create support gaps.

**Workflow:**
1. The Reference Library automatically flags EOA hardware across all systems during enrichment
2. Go to **Technical Audit** — EOA systems appear as Medium/High enrichment risks
3. Cross-reference with **Tab 10** for lifecycle milestones and EOS dates
4. Use **Tab 14** for warranty status and remaining support coverage

**Flagged EOA Platforms:**

> The EOA list in the Reference Library is updated dynamically as NetApp publishes new End-of-Availability notices. The entries below reflect the current database; always check the dashboard's lifecycle view or the live `REFERENCE_LIBRARY_EOA_PLATFORMS` array in `app.js` for the authoritative set.

- **AFF:** A200, A220, A300, A320, A700, A700s, A800, C190, C800
- **ASA:** C250, C400, C800
- **FAS:** 2600, 500f, 8200, 9000
- **StorageGRID:** SG5600, SG5700 appliance nodes *(older-generation object storage nodes)*
- **E-Series / EF-Series:** E2600, E2700, E5400, E5500, E5600, EF540, EF550, EF560 *(legacy SAN arrays)*
- **EOA Switches:** BES-53248, Cisco 9336C-FX2, NVIDIA SN2100

---

### MetroCluster Health Review

**Goal:** Validate MetroCluster switch configurations, firmware, and ISL parameters against NetApp requirements.

**Workflow:**
1. Go to **Action Planner → Tab 6** (Switch Validation)
2. All cluster and MetroCluster switches are inventoried with model and firmware version
3. ISL parameters (distance, packet loss, jitter, MTU) are validated against Reference Library baselines
4. Firmware currency is checked against recommended minimums for Cisco NX-OS, Cisco MDS, Brocade FOS, and Broadcom EFOS

---

## 4. Getting Started

### Prerequisites

| Requirement | Minimum | Notes |
|---|---|---|
| **Python** | 3.8+ | Check with `python --version` |
| **Active IQ Refresh Token** | — | Generated from the Active IQ portal |
| **Network access** | — | To `gql.aiq.netapp.com` and `api.activeiq.netapp.com` for initial sync |

> **No pip packages required** for the web dashboard. The server uses only Python standard library modules. `requirements_desktop.txt` is only needed for the optional standalone desktop app.

### Step 1 — Clone the Repository

```bash
git clone https://github.com/ebeauzec/AIQscraper.git
cd AIQscraper
```

### Step 2 — Get Your API Refresh Token

1. Log in to [activeiq.netapp.com](https://activeiq.netapp.com/)
2. Click **Quick Links** → **API Services**
3. Click **Generate Token**
4. Copy the **Refresh Token**

> The Refresh Token is stored locally in `aiq_config.json` and is only ever sent to the official NetApp OAuth endpoint. It is never transmitted to any third-party service.

### Step 3 — Start the Dashboard

| Method | How | Notes |
|---|---|---|
| **Windows Batch** ⭐ | Double-click `start_dashboard.bat` | **Recommended.** Auto-kills old processes, starts server, opens browser |
| **PowerShell** | `.\Start-Dashboard.ps1` | Coloured output with Python version check |
| **Direct Python** | `python server.py` → `http://localhost:8080` | Dev mode — verbose console output |
| **Desktop App** | `python launcher.py` | Standalone window (requires `pip install pywebview`) |

### Step 4 — First Sync

1. Open `http://localhost:8080` in your browser
2. Go to **Settings & Config** (last sidebar tab)
3. Paste your **Refresh Token**
4. Click **Sync Now**

First sync takes **30–90 seconds** (8+ GraphQL API calls). All subsequent page loads serve cached data instantly from SQLite while a background thread re-syncs.

### Step 5 — Filter to a Customer

Use the **Customer Filter** dropdown in the sidebar to scope all views and deliverables to a single customer. All tabs, charts, tables, and generated reports respect the active filter.

---

## 5. Dashboard Guide

The sidebar provides six primary navigation areas:

### Overview

Fleet-wide KPI cards (systems, clusters, critical risks, open cases), interactive charts (capacity trend, risk distribution, platform mix), and a sortable/filterable system inventory table.

### Technical Audit

The risk and security intelligence hub. Displays all Active IQ risks sorted by severity, security advisories with CVE cross-referencing, and Reference Library enrichment checks (Kerberos, SnapMirror, Varonis, firewall deprecation). Each advisory links to the NetApp Security Advisory portal.

### Support & Ops

Contract status pipeline (Active / Expiring / Expired cards), EOS/EOA lifecycle timeline sorted by urgency, and a filterable support case view (Open / Processing / Closed) with case age and system attachment.

### Value & ROI (CSM)

Storage efficiency and capacity intelligence:

- **Data Reduction Ratio** — dedupe + compression only. Snapshot-inclusive ratio shown as a secondary annotation for reference
- **Space Saved** — TB saved through deduplication and compaction (not including snapshot space)
- **FabricPool** — tiering ratio and adoption status
- **SnapMirror** — async/sync relationship counts
- **Capacity Projection Chart** — toggle between **Aggregate** (fleet-wide) and **Per Node** (individual node trend lines)
- **Capacity Breakdown by Node** — Used TB, Raw TB, Utilisation %, Growth/day, Runway, Data Source per node

> **Per Node toggle:** Click **Per Node** in the top-right of the chart to see each cluster node as a separate trend line. The breakdown table below updates to show per-node utilisation and runway. Raw TB shows "N/A" where the API reports capacity at cluster-aggregate level only — used TB and utilisation fall back to the actual monthly telemetry data (the same source the chart uses).

### Action Planner

The core reporting engine. Click **Generate** to build all 15 sections. Use the numbered tab row to navigate. See [Section 6](#6-action-planner--all-15-sections) for full detail on each section.

### Settings & Config

API token management, sync interval, custom account groups, watchlist IDs, and state export/import.

---

## 6. Action Planner — All 15 Sections

Click **Action Planner** in the sidebar, then **Generate**. All 15 sections are built and the numbered tab row appears above the content area.

| # | Section | What's Inside |
|---|---|---|
| **1** | **Executive Summary** | Fleet health KPIs, key findings, critical items needing immediate action |
| **2** | **Technical Risks** | All Active IQ risks — severity sorted, fix-grouped to eliminate duplicates, with affected systems and remediation |
| **3** | **Security Advisories** | CVE-referenced bulletins with CVSS, affected version ranges, fix versions, and specific CLI remediation commands |
| **4** | **Support Cases** | Active, in-progress, and recently closed cases — priority sorted, with case age and system link |
| **5** | **OS Upgrades** | Hop-by-hop upgrade paths. Direct where possible; multi-hop with intermediate versions and per-version notes. Covers ONTAP, StorageGRID, SANtricity |
| **6** | **Switch Validation** | Cluster and MetroCluster switch inventory with firmware currency check and ISL parameter validation |
| **7** | **Logistics & Health** | Site locations (city/country/state), account contacts, CSAT scores |
| **8** | **Guidelines** | ITIL change control tiers — Non-Disruptive / Disruptive but Data-Safe / Destructive — with pre/post actions |
| **9** | **Deliverables** | Six one-click downloadable report generators |
| **10** | **Contracts & Lifecycle** | Contract pipeline (Active/Expiring/Expired), lifecycle table sorted by urgency, tech refresh status, service tier breakdown |
| **11** | **Sustainability & ESG** | Fleet Sustainability Score with weekly trend, carbon/energy per system, data reduction ratios per customer |
| **12** | **Recommendations** | Active IQ key recommendations by category (VERSION, AUTO_SUPPORT, BEST_PRACTICES, CONFIG, ENTITLEMENTS) with rank scores |
| **13** | **Account Intelligence** | Personnel map (Sales Rep, CSM, SAM, ASP, Propensity per system), site inventory |
| **14** | **Contract Compliance** | Compliance posture cards, service tier distribution, per-system HW/SW service levels and EOA/EOS dates |
| **15** | **Operational Health** | AutoSupport recency audit (7-day silence detection), ARP enablement fleet audit, firmware currency, last reboot timeline |

---

## 7. Downloadable Deliverables

All deliverables are generated in the browser from your local data. Nothing is uploaded or transmitted. Find them in **Action Planner → Tab 9**.

> **Customer-scoped:** Set the Customer Filter in the sidebar before generating to produce a deliverable for a single account only.

| Deliverable | Best For | Contents |
|---|---|---|
| **Customer Success Plan** | Executive QBR presentation | Fleet health summary, key risks, strategic recommendations, contract renewal pipeline |
| **QBR Pack** | Quarterly Business Reviews | KPI scorecard, risk trend, resolved cases, open action items, upgrade roadmap |
| **MSP Service Report** | Monthly managed service reporting | SLA metrics, case resolution summary, proactive actions, risk posture change |
| **Account Handover Brief** | TAM-to-TAM transitions | Fleet context, open risks, contract status, key contacts, pending actions |
| **Extended Deliverables** | Deep technical briefings | Full risk register, advisory inventory, upgrade roadmap, switch validation |
| **CLI Runbook** | Implementation engineers / CAB submissions | Copy-paste ONTAP CLI commands, grouped by remediation and classified by ITIL tier |

---

## 8. Security & Data Privacy

### Tool Security Guarantees

| Guarantee | Detail |
|---|---|
| **100% Local** | All data stays in browser `localStorage` and local SQLite (`aiq_cache.db`). Nothing goes to any cloud service |
| **Zero AI/ML** | No generative AI, no ML models, no LLM services — anywhere in the stack. All outputs are fully deterministic |
| **No Telemetry** | The tool does not phone home, collect analytics, or transmit metadata of any kind |
| **Official NetApp APIs Only** | Network traffic is exclusively to `gql.aiq.netapp.com` and `api.activeiq.netapp.com` over TLS 1.2+ |
| **Read-Only** | Only reads telemetry via the Active IQ API. Never executes commands against production systems |
| **Human-Reviewed Remediation** | All CLI outputs go into change tickets for human review and CAB approval — nothing is auto-executed |
| **Offline After Sync** | Once synced, the dashboard operates fully offline from the local cache |
| **Minimal Footprint** | No install, no persistent services, no registry modifications, no external shares |

### Security Intelligence Database

The tool maintains a **live security advisory database** in [`security_bulletins.json`](file:///g:/My%20Drive/AntiGravity/AIQscraper/security_bulletins.json), cross-referenced against every system's ONTAP/StorageGRID/SnapCenter version at enrichment time. This is **in addition to** advisories returned by the Active IQ API.

> [!IMPORTANT]
> The server (`python server.py`) must be running for advisory data to load. If the server is offline, the database will be empty and the **Security Advisory Database** indicator in the Sync panel will show ⚠️ **server offline**.

| Metric | Value |
|--------|-------|
| **Current advisory entries** | **69** (grows with each daily scan) |
| **CISA KEV confirmed** | **2** (actively exploited in the wild) |
| **Coverage period** | 2024 – 2026 |
| **Products covered** | ONTAP 9, StorageGRID, SnapCenter, Astra Trident, SAN Host Utilities, Active IQ Unified Manager |
| **Database file** | `security_bulletins.json` — single source of truth |

#### How the Database Grows

```
Daily scan (08:00)  →  POST /api/bulletins  →  security_bulletins.json
                                                         ↓
App startup / Refresh button  →  GET /api/bulletins  →  in-memory DB  →  enriches all systems
```

The daily 08:00 background scan reads the NetApp Reference Library, checks `security.netapp.com` and NVD for new advisories, and POSTs any new entries to the running server. The server merges them (deduplicating by `id`) and writes to `security_bulletins.json`. **No code edits to `app.js` are ever needed.**

#### Adding a New Advisory Manually

**Option A — POST to server (preferred, server must be running):**
```bash
curl -X POST http://localhost:8080/api/bulletins \
  -H "Content-Type: application/json" \
  -d '{"bulletins":[{"id":"NTAP-YYYYMMDD-XXXX","cve":["CVE-XXXX-XXXXX"],"cvss":8.5,"severity":"high","title":"...","description":"...","affectedProducts":["ONTAP"],"affectedVersions":{"ontap":[{"from":"9.x.y","to":"9.x.yPn"}]},"fixedVersions":{"ontap":["9.x.yPn+1"]},"mitigation":"Upgrade to ...","published":"YYYY-MM-DD","link":"https://security.netapp.com/advisory/..."}]}'
```

**Option B — Edit `security_bulletins.json` directly:** Add an entry to the `bulletins` array, restart the server, then click **🛡️ Refresh Security Advisory DB** in the Sync panel.

#### Sources

| Source | Type |
|--------|------|
| `security.netapp.com` (NetApp PSIRT) | Official NetApp advisories (NTAP-YYYYMMDD-XXXX) |
| MITRE CVE | CVE dictionary cross-reference |
| NVD / NIST CVE API | CVSS scores, affected version metadata |
| CISA Known Exploited Vulnerabilities (KEV) | Active exploitation status |
| GitHub Security Advisories | Trident / Golang dependency CVEs |
| NetApp KB | Operational bugs (CONTAP-xxxxxx IDs) |
| Tenable, SentinelOne, Eclypsium, CIRCL | Threat intelligence cross-reference |

#### 🚨 CISA KEV — Actively Exploited Entries

> **This list is maintained dynamically.** The advisory database (`security_bulletins.json` + `NETAPP_SECURITY_BULLETIN_DB` in `app.js`) is refreshed from CISA KEV, NetApp PSIRT, and threat intelligence sources via the daily background scan and the **🛡️ Refresh Security Advisory DB** button. The current set of KEV-flagged entries is always visible in the dashboard's Security Bulletins panel — the entries below were those confirmed at the time this documentation was last written and are shown as **illustrative examples only**.

As of the last Reference Library sync, the following NetApp-related CVEs appeared on the CISA KEV catalog:

| CVE | CVSS | Product | Status | Fix |
|-----|------|---------|--------|----- |
| **CVE-2024-54085** | **10.0** | StorageGRID BMC (SG6160, SGF6112, SG110, SG1100) | 🚨 Active exploitation confirmed. PoC exists. | Apply AMI MegaRAC SPx firmware 12.7+/13.5+ |
| **CVE-2024-38475** | **9.1** | ONTAP 9 (Apache mod_rewrite) | 🚨 Actively exploited. CISA KEV 2024. | ONTAP 9.12.1P16 / 9.14.1P8 / 9.16.1 |

Additional KEV entries may have been added since. Always defer to the live dashboard or [https://www.cisa.gov/known-exploited-vulnerabilities-catalog](https://www.cisa.gov/known-exploited-vulnerabilities-catalog) for the authoritative list.

---

## 9. Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| **Port 8080 in use** | Old server process running | Use `start_dashboard.bat` — auto-kills old processes. Or: `netstat -ano \| findstr :8080` → `taskkill /F /PID <pid>` |
| **Dashboard outdated / tabs missing** | Browser cached old `index.html` | Hard refresh: **Ctrl+Shift+R** |
| **Server won't start** | Python not in PATH | Check: `python --version` (must be 3.8+) |
| **No data after sync** | Invalid or expired token | Regenerate at Active IQ → Quick Links → API Services |
| **CORS errors in console** | HTML opened as file:// not via server | Always use `http://localhost:8080` |
| **Action Planner tabs 10–15 missing** | Report not generated yet | Click **Action Planner** → click **Generate** |
| **Sync takes 60–90 seconds** | Large portfolio, first sync | Normal. Subsequent loads use the SQLite cache. Add `?force=1` to URL to force re-harvest |
| **Charts not rendering** | `chart.js` missing | Verify file exists in project folder. Hard refresh (Ctrl+Shift+R) |
| **Node capacity shows 0.0** | API reports cluster-aggregate, not per-node | Dashboard falls back to monthly telemetry. Ensure a full sync completed |
| **Desktop app won't launch** | Missing `pywebview` | `pip install -r requirements_desktop.txt` |

---

## 10. Internal Architecture

> This section is an addendum for developers who want to understand, extend, or contribute to the codebase. It is not required reading for daily use.

### High-Level Stack

```
Browser (app.js + styles.css + chart.js)
  │  fetch /api/harvest
  ▼
server.py  ─── port 8080 ───►  SQLite (aiq_cache.db)
  │
  ├── NetApp OAuth (api.activeiq.netapp.com) — token exchange
  └── Active IQ GraphQL (gql.aiq.netapp.com) — 8+ queries
```

### Component Reference

| File | Size | Role |
|---|---|---|
| `server.py` | ~75 KB | Python HTTP server. OAuth exchange, 8+ GQL queries, normalization, SQLite cache (WAL mode), static file serving, `/api/*` endpoints |
| `app.js` | ~700 KB | ~13,200 lines JavaScript. Enrichment engine, risk engine, upgrade path calculator, 15-tab Action Planner renderer, 6 deliverable generators, chart rendering, Reference Library |
| `index_src.html` | ~74 KB | Dev HTML shell — loads external `app.js` + `styles.css`. Changes to `app.js` take effect on browser refresh |
| `index.html` | ~680 KB | Compiled single-file HTML with all JS/CSS inlined. Rebuild after code changes |
| `styles.css` | ~22 KB | Dark-theme CSS, glassmorphism effects, responsive layout |
| `chart.js` | ~209 KB | Local copy of Chart.js library |
| `aiq_cache.db` | Variable | SQLite persistent cache (WAL mode) |
| `aiq_config.json` | ~2 KB | Server config — token, sync settings |
| `start_dashboard.bat` | ~1 KB | Windows batch launcher |
| `Start-Dashboard.ps1` | ~2 KB | PowerShell launcher with Python version check |
| `launcher.py` | ~8 KB | Desktop app wrapper (pywebview) |

### Data Flow

```
1. User pastes Refresh Token → Settings → Sync Now
2. server.py: exchange Refresh Token → Access Token (NetApp OAuth, TLS 1.2+)
3. server.py: 8+ GraphQL queries to gql.aiq.netapp.com
      Systems · Clusters · Risks · Cases · Watchlists
      Recommendations · Sustainability · Sites · Contracts · OS Catalog
4. server.py: normalize response
      – Flatten nested objects
      – Map HA partners
      – Attach cases to systems by serial number
      – Merge risk instances to parent risk definitions
      – Extract switches from port connectivity data
5. server.py: cache full result to SQLite (aiq_cache.db)
6. server.py: return normalized JSON to browser
7. app.js: enrichSystemTelemetry() runs on each system
      – Reference Library: EOA flags, CVE version-range matching,
        Kerberos AES detection, SnapMirror policy alignment,
        Varonis EOL, legacy firewall detection
      – Upgrade path calculation (direct + multi-hop)
      – Contract and lifecycle date normalization
      – SnapMirror relationship data
      – Efficiency metrics: dataReductionRatio (dedupe+compression only)
        Space saved: deDuplicationSavedKiB + compactionSavedKiB
8. app.js: store enriched systems in localStorage
9. app.js: render across sidebar tabs, charts, Action Planner
```

### Efficiency Calculation

The dashboard uses `dataReductionRatio` from `ONTAPSystemEfficiency.ratio.dataReductionRatio` — **dedupe + compression only, no snapshot savings.** The snapshot-inclusive `efficiencyRatio` is preserved and displayed as a secondary annotation. Space saved is `deDuplicationSavedKiB + compactionSavedKiB` only.

### Reference Library — EOA Platforms

> **The EOA platform list is updated dynamically** as NetApp publishes new End-of-Availability notices, synced via the daily Reference Library scan. The table below reflects the current database at the time of writing and is shown as a **representative snapshot**. Entries are matched against all system types — ONTAP (AFF/ASA/FAS), StorageGRID appliances, and E-Series/EF-Series arrays. Check the `REFERENCE_LIBRARY_EOA_PLATFORMS` array in `app.js` for the live list.

| Family | EOA Models |
|---|---|
| AFF | A200, A220, A300, A320, A700, A700s, A800, C190, C800 |
| ASA | C250, C400, C800 |
| FAS | 2600, 500f, 8200, 9000 |
| StorageGRID | SG5600, SG5700 appliance nodes |
| E-Series / EF-Series | E2600, E2700, E5400, E5500, E5600, EF540, EF550, EF560 |
| EOA Switches | BES-53248, Cisco 9336C-FX2, NVIDIA SN2100 |

### Reference Library — CVE Database

> **The advisory database is updated dynamically** via the daily 08:00 Reference Library scan and the **🛡️ Refresh Security Advisory DB** button. The table below is a **point-in-time snapshot** of representative entries from the initial Reference Library build — it is **not** a complete or current list. The authoritative source is always the live database in `security_bulletins.json` and `NETAPP_SECURITY_BULLETIN_DB` within `app.js`, which currently contains 80+ advisory entries across 90+ unique CVEs. Use the dashboard's Security Bulletins panel or run `jq '.bulletins | length' security_bulletins.json` for an accurate current count.

*Example entries (illustrative — refer to live DB for current coverage):*

| CVE | Product | Sev | CVSS | Summary |
|---|---|---|---|---|
| CVE-2026-22050 | ONTAP | High | 7.5 | Snapshot Lock Bypass |
| CVE-2026-22052 | ONTAP | Med | 5.3 | S3 NAS Bucket info disclosure |
| CVE-2026-20833 | ONTAP CIFS | Med | 5.9 | Kerberos AES enforcement (KB5073381) |
| CVE-2026-22054 | Config Advisor | Med | 5.3 | Hard-coded credentials 6.7.3 |
| CVE-2025-26512 | SnapCenter | Crit | 9.9 | Privilege escalation |
| CVE-2026-22051 | StorageGRID | Med | 4.3 | Metrics query info disclosure |
| CVE-2026-24051 | Trident | High | 7.0 | OpenTelemetry PATH hijack |
| … | … | … | … | *80+ additional entries in live DB* |

### Reference Library — Firmware Baselines

| Component | Recommended Min |
|---|---|
| NSM100 Shelf | 0220 |
| IOM12 SAS | 0260 |
| IOM3 SAS | 0200 |
| Cisco NX-OS | 9.3(12) |
| Cisco MDS | 9.2(2) |
| Brocade FOS | 9.2.1 |
| Broadcom EFOS | 3.8.0.2 |

### Reference Library — MetroCluster ISL Requirements

| Parameter | FC Brocade | FC Other | IP |
|---|---|---|---|
| Max Distance | 300 km | 200 km | 700 km |
| Max Packet Loss | 0.01% | 0.01% | 0.01% |
| Max Jitter | 3 ms | 3 ms | 3 ms |
| Required MTU | — | — | 9216 |

### Development Workflow

```bash
# Serve dev HTML (changes to app.js take effect on Ctrl+Shift+R)
python server.py

# Rebuild compiled index.html after code changes (Windows)
build_windows.bat

# Rebuild on macOS/Linux
bash build_mac.sh
```

---

## Change History

See [CHANGELOG.md](CHANGELOG.md) for the full version history.

---

## 11. Legal & Intellectual Property

> **Full terms:** [LICENSE](LICENSE) · [LEGAL.md](LEGAL.md)

### Ownership

This Software is the **sole and exclusive intellectual property of Eugene Beauzec**.
Copyright © 2025–2026 Eugene Beauzec. All Rights Reserved.

### Independent Development

This tool was developed **entirely independently** — on personal time, with personal resources, and without the involvement, direction, or funding of any employer or client, including NetApp, Inc. It does not contain or derive from any proprietary, confidential, or internal NetApp information, customer data, or trade secrets.

NetApp is not affiliated with, sponsoring, or endorsing this Software. Product names referenced (NetApp®, ONTAP®, Active IQ®, etc.) are trademarks of their respective owners, used solely for interoperability documentation.

### License Terms at a Glance

| Use | Permission |
|---|---|
| Personal / educational / research | ✅ Free |
| Internal non-commercial organisational use | ✅ Free |
| **Commercial use of any kind** | ⛔ **Requires Author's prior written consent** |
| Redistribution | ⛔ Requires Author's prior written consent |
| Claiming authorship / removing attribution | ⛔ Prohibited |

This is **not** an open-source or MIT-licensed project. All rights not expressly granted are reserved by the Author.

### Attribution

All permitted uses must retain this notice:
> *Copyright © 2025–2026 Eugene Beauzec. All Rights Reserved.*
> *[LICENSE](LICENSE) · [LEGAL.md](LEGAL.md)*

---

<p align="center">
  <strong>NetApp Active IQ Advisor Dashboard</strong><br>
  Copyright &copy; 2025&ndash;2026 <strong>Eugene Beauzec</strong>. All Rights Reserved.<br>
  <a href="LICENSE">Proprietary License</a> &middot; <a href="LEGAL.md">Legal &amp; IP</a> &middot; <a href="CHANGELOG.md">Changelog</a>
</p>
