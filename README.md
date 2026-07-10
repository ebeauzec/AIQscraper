# NetApp Active IQ TAM Dashboard

[![Version](https://img.shields.io/badge/version-3.0.0-blue)](CHANGELOG.md)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A comprehensive Technical Account Manager (TAM) dashboard for NetApp, integrating SAM, CSM, and TAM functions into a single operational tool. Connects to the Active IQ Digital Advisor APIs via REST and GraphQL endpoints.

---

## Quick Start

### Prerequisites
- **Python 3.8+** — check with `python --version`
- **pip packages** — `pip install -r requirements_desktop.txt`
- **Active IQ API Token** — [instructions below](#setting-up-api-credentials)

### How to Start the Dashboard

| Method | Command | Notes |
|---|---|---|
| **Batch file** ⭐ | Double-click `start_dashboard.bat` | Recommended. Auto-kills old processes, starts server, opens browser. |
| **PowerShell** | `.\Start-Dashboard.ps1` | Colored status output, full process cleanup. |
| **Direct Python** | `python server.py` then open `http://localhost:8080` | Development. Verbose console output. |
| **Desktop App** | `python launcher.py` | Standalone window (requires `pip install pywebview`). |

### How to Stop

- Press **Ctrl+C** in the terminal window, or just close it.

### Setting Up API Credentials
1. Log in to [activeiq.netapp.com](https://activeiq.netapp.com/)
2. Click **Quick Links** → **API Services**
3. Click **Generate Token** to create your **Refresh Token**
4. In the dashboard, go to **Settings & Config** → paste the token → click **Sync**

---

## Project File Structure

| File | Purpose |
|---|---|
| `server.py` | Python backend — GraphQL API integration, TAM data harvesting, SQLite caching |
| `index_src.html` | Development HTML — loads `app.js` and `styles.css` as external files |
| `index.html` | Compiled single-file HTML — has all JS/CSS baked in (for offline/distribution) |
| `app.js` | All frontend JavaScript (main development file — **edit this one**) |
| `styles.css` | All CSS styles |
| `chart.js` | Chart.js library (local copy) |
| `launcher.py` | Desktop app launcher (pywebview wrapper) |
| `start_dashboard.bat` | Windows batch launcher — kills old servers, starts fresh |
| `Start-Dashboard.ps1` | PowerShell launcher — same but with colored output |
| `aiq_cache.db` | SQLite database — persistent data storage |

> **Important**: When developing, the server serves `index_src.html` (which loads the external `app.js`). 
> Changes to `app.js` take effect immediately on browser refresh. 
> The compiled `index.html` is for distribution/offline use only and must be rebuilt after code changes.

---

## What the Tool Does

### Dashboard Tabs (Sidebar)
- **Overview Dashboard** — KPIs, charts, system inventory table
- **Technical Audit** — Predictive risks, security advisories (NTAP-SA), CVE references
- **Support & Ops** — Contract tracking, EOS/EOA dates, open support cases
- **Value & ROI (CSM)** — Storage efficiency, FabricPool, SnapMirror, capacity projections
- **Action Planner** — 15-section executive report generator (see below)
- **Settings & Config** — API token, sync interval, groups, import/export

### Action Plan Sub-Tabs (1-15)
| Tab | Content |
|---|---|
| 1. Summary | Executive overview with KPI summary |
| 2. Technical Risks | Prioritized risk register |
| 3. Security Advisories | CVE-referenced security bulletins |
| 4. Support Cases | Open technical support cases |
| 5. OS Upgrades | Upgrade paths with direct/multi-hop analysis |
| 6. Switch Validation | Cluster & MetroCluster switch inventory |
| 7. Logistics & Health | Site logistics, contacts, CSAT |
| 8. Guidelines | Change control procedures |
| 9. Deliverables Drafts | Downloadable reports & templates |
| **10. Contracts & Lifecycle** | Contract status, lifecycle events (EOA/EOS), renewal pipeline |
| **11. Sustainability & ESG** | Sustainability Score (0–100%), data reduction, carbon/energy |
| **12. Recommendations** | 5-category AIQ recommendations (Version, ASUP, Best Practices, Config, Support) |
| **13. Account Intelligence** | Sites, personnel (Sales/CSM/SAM/ASP), propensity, account overview |
| **14. Contract Compliance** | Compliance posture, service tier distribution, warranty status |
| **15. Operational Health** | ASUP health, ARP audit, firmware currency, reboot timeline |

---

## TAM Account Intelligence (Tabs 10–15)

The Action Planner includes six specialized Technical Account Management tabs that provide deep operational intelligence. These tabs are populated from Active IQ GraphQL TAM endpoints and are scoped to the selected customer when a customer filter is active.

### Tab 10: Contracts & Lifecycle
Displays contract status summary (active, expiring within 90 days, expired), lifecycle events sorted by urgency (end-of-availability, end-of-support milestones), and a contract renewal pipeline showing tech refresh status, service tiers, and HW EOA/EOS dates. All data is filtered to the selected customer's systems.

### Tab 11: Sustainability & ESG
Shows the fleet-wide Active IQ Sustainability Score (0–100%) with week-over-week trend data, historical weekly snapshots, and improvement factors. A per-customer "Average Data Reduction" card (dedup + compression ratio) provides customer-scoped efficiency metrics. Per-system monthly carbon emissions and energy consumption data is shown when available.

> **Note:** Sustainability scores are fleet-wide as the AIQ API does not support per-customer breakdown. A disclaimer banner is displayed.

### Tab 12: Recommendations
Aggregates Active IQ key recommendations grouped by category:
- **VERSION** — OS/firmware upgrade recommendations
- **AUTO_SUPPORT** — ASUP configuration and connectivity
- **BEST_PRACTICES** — Storage efficiency and configuration best practices
- **CONFIG** — System configuration improvements
- **SUPPORT_AND_ENTITLEMENTS** — Contract and support coverage

Each recommendation shows its rank score and sub-category for prioritization.

### Tab 13: Account Intelligence
The primary account overview tab showing:
- **Account Personnel** — Per-system breakdown of Sales Rep, CSM, SAM, ASP, and propensity category
- **Sites** — Physical data center locations filtered to the selected customer (city, country, age, critical/high propensity counts)
- **Summary Cards** — Customer count, site count, and system count scoped to the active filter

### Tab 14: Contract Compliance
Derives compliance posture from contract status, warranty dates, and service tiers:
- **Summary Cards** — Active contracts, expired contracts, warranty active, warranty expired
- **Service Tier Distribution** — Breakdown of support levels (Premium, Standard, etc.)
- **Renewal Pipeline** — Per-system contract details with HW/SW service levels, expiry dates, and EOA/EOS milestones

### Tab 15: Operational Health
Real-time operational posture assessment:
- **ASUP Health** — Systems with AutoSupport telemetry received within 7 days vs. stale (no ASUP > 7 days)
- **ARP Audit** — Systems with Autonomous Ransomware Protection enabled vs. not enabled
- **Firmware Currency** — Systems running recommended OS vs. behind minimum recommended version
- **Last Reboot Timeline** — Days since last reboot per system, sorted by most recent

### Tooltips
All summary cards across the tool display hover tooltips with detailed explanations. Cards also include descriptive subtitles for at-a-glance understanding without hovering.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| **Port 8080 in use / old server running** | Use `start_dashboard.bat` — it auto-kills old processes. Or manually: `taskkill /F /IM python.exe` |
| **Dashboard looks outdated / missing tabs** | Server may be serving the compiled `index.html`. Restart with `start_dashboard.bat` which serves `index_src.html` (with external `app.js`). Hard refresh: **Ctrl+Shift+R**. |
| **Server won't start** | Check Python is installed: `python --version`. Check port: `netstat -ano | findstr 8080`. |
| **No data after sync** | Verify your Refresh Token is valid. Check the terminal for API error messages. |
| **CORS errors** | Use `server.py` (not opening HTML directly). API Base URL should be `/api`. |
| **New tabs (10-15) not visible** | Click **Action Planner** → **Generate** → tabs appear in wrapped rows above the content. |

---

## Data Security & Compliance

### 100% AI-Free Processing
* **Zero AI/ML Dependencies**: No generative AI, ML, or LLM services used.
* **Deterministic Logic**: All calculations use standard JavaScript algorithms.

### Complete Data Sovereignty
* **Local-only**: All data stored in `localStorage` and local SQLite (`aiq_cache.db`).
* **Zero external transmission**: Only contacts official NetApp TLS endpoints.
* **Offline capable**: Works fully offline after initial sync.

### NetApp Security Policy
* **Read-only telemetry**: No execution commands against production systems.
* **Change control enforcement**: Outputs ITIL-aligned tickets and CLI runbooks for review.
* **Minimal footprint**: No installation, no external data shares.

---

## Change History
See the [CHANGELOG.md](CHANGELOG.md) for version release details.
