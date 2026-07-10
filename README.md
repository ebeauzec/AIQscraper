# NetApp Active IQ Account Report Dashboard

[![Version](https://img.shields.io/badge/version-2.0.0-blue)](CHANGELOG.md)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A report builder and operational dashboard for NetApp Support Account Managers (SAM), Technical Account Managers (TAM), and Customer Success Managers (CSM).

This tool can run as a **standalone browser page** for demo/offline use, or with the included **Python server** (`server.py`) for full API connectivity, persistent SQLite storage, and CORS-free operation. It connects to the Active IQ Digital Advisor APIs via both REST and GraphQL endpoints (`activeiq.netapp.com`, `gql.aiq.netapp.com`).

---

## What's New in Version 2.0.0

This is a **major release** introducing a persistent server backend, GraphQL API integration, and redesigned deliverables.

*   **Python Server Backend (`server.py`)**: Full reverse-proxy and API gateway that handles OAuth token exchange, GraphQL harvesting, SQLite persistence, and serves the dashboard. Eliminates the need for CORS browser extensions.
*   **SQLite Persistent Database**: All system telemetry, risks, and metadata now persist in a local `aiq_cache.db` database across browser sessions and machines. Browser localStorage remains as a fast client-side cache.
*   **GraphQL API Integration**: Migrated from REST-only polling to NetApp's GraphQL API for richer data including cluster-level capacity, SnapMirror relationship counts, HA configuration, contacts, contracts, and security advisories.
*   **Fix-Grouped Deliverables**: All report templates now group findings by their corrective fix (e.g. "Upgrade to ONTAP 9.16.1"). A single upgrade that resolves 8 CVEs shows as one prioritised action with all addressed findings listed beneath it. Reports filter to **Critical and High only** for executive brevity.
*   **SnapMirror Relationship Mapping**: Cluster-level SnapMirror counts mapped to individual systems with async/sync breakdown in the CSM module.
*   **Chronological Chart Labels**: Capacity projection charts now display real calendar months instead of generic offset labels.
*   **Actionable Remediation Text**: Security advisories include specific upgrade targets (e.g. "Upgrade to ONTAP 9.16.1") instead of generic "See Security Advisory".

### Previous Releases

See [CHANGELOG.md](CHANGELOG.md) for the full version history (v1.0.0 – v1.11.0).

---

## What the Tool Does

This dashboard consolidates telemetry data from the public Active IQ API to help account teams prepare customer reviews, identify system issues, and optimize installations.

*   **Technical Audit Module**: Lists active predictive risks (e.g., single-path storage failures, outdated shelf firmware) and **Security & Technical Bulletins** (NetApp Security Advisories - NTAP-SA) with CVE references, vulnerability status, and official mitigation links.
*   **Support & Ops Module**: Tracks support contract expiration thresholds, flags hardware End-of-Support (EOS/EOA) dates, and displays unresolved NetApp Field Actions (FA). Includes **3rd-Party Hypervisor Integration** compliance checks and **Open Technical Support Cases** list.
*   **Site Logistics & Sales Health**: Displays site-specific delivery addresses, access and security gate restrictions, transit alerts, primary technical contacts (with NSS usernames), and account health indicators (AM/TAM leads, customer CSAT sentiment scores, upgrade potential pipelines, tech refresh windows).
*   **CSM Module (ROI & Adoption)**: Showcases storage efficiencies, FabricPool cloud capacity tiering savings, SnapMirror disaster recovery replication states, and a capability adoption scorecard. Includes a **Capacity & Performance Projection Graph** forecasting storage runway days and peak IOPS latency boundaries.
*   **Action Planner**: Compiles an exhaustive, print-friendly **Executive Action Plan** for a single system, all systems under a specific customer account, or your entire monitored portfolio. Includes prioritized risks, security bulletins, active support cases, runway timelines, logistics site contacts, and Change Control proceeding guidelines.
*   **Sidebar Filtering (Accounts & Groups)**: Dynamically groups systems by Customer Account or Custom Subgroups directly in the sidebar navigation pane. Clicking a group filters the entire dashboard context instantly, complete with risk count indicators.
*   **Import/Export Config**: Save your active telemetry reports, custom mock datasets, and updated logistics/bulletins/cases schemas as a JSON file, or import external files to load report views instantly.

---

## Technical Support Cases Tracking

SAMs and customer leads can review active technical assistance cases directly in the **Support & Ops** tab:
*   **Case ID**: Unique NetApp Support Case identifier.
*   **Subject**: Clear title description of the reported issue (e.g., SSD failure, license mismatches, VASA Provider sync issues).
*   **Severity**: Standard NetApp priority levels (`S1 - Critical`, `S2 - Major`, `S3 - Medium`, `S4 - Low`).
*   **Status**: Dynamic workflow tracker (e.g., `Open - Pending Parts Dispatch`, `Open - NetApp Engineering`, `Open - Customer Action`, `Resolved - Pending Customer Closure`).
*   **Timestamps**: Opened Date and Last Updated Date.
*   **TAM Notes**: Operational updates and next actions (e.g., parts delivery estimates, escalation states).

---

## Supported Platforms & Technologies

This reporting tool is aligned to retrieve and map telemetry across the complete NetApp product portfolio:
*   **ONTAP (FAS & AFF Systems)**: On-premises unified primary flash/hybrid storage, including next-gen flagship models (**AFF A1K**, **AFF A90**, **AFF A70**, and **AFF C80** capacity flash) and legacy platforms.
*   **All SAN Array (ASA Systems)**: Dedicated block-only SAN storage platforms (including **ASA A90** and **ASA A30**), optimized for symmetric active-active multipathing workloads.
*   **Cloud Volumes ONTAP (CVO)**: Software-defined storage deployed in AWS, Azure, or GCP.
*   **StorageGRID**: Webscale S3/Swift object storage, including high-capacity hardware appliances like the **SG6160**.
*   **E-Series & EF-Series**: High-performance block storage platforms, including NVMe-native **EF600** controllers.
*   **MetroCluster IP/FC**: High-availability synchronous multi-site disaster recovery configurations.
*   **SnapMirror & SyncMirror**: Asynchronous and synchronous remote data replication paths.

---

## End-to-End Architecture, Data Handling, & Core Use Cases

### 1. Data Polling Architecture & Data Flows

The application supports two data flow modes:

**Server Mode (Recommended)** — using `server.py`:
1. **Authentication**: The server exchanges your NSS Refresh Token for a short-lived JWT access token via the NetApp OAuth endpoint.
2. **GraphQL Harvesting**: The server queries `gql.aiq.netapp.com/graphql` for systems, clusters, risks, cases, contracts, contacts, and site data in a single batch. This provides significantly richer data than the REST API alone.
3. **SQLite Persistence**: Harvested data is stored in `aiq_cache.db` — a local SQLite database that persists across browser sessions and machine reboots.
4. **Dashboard Serving**: The server serves the dashboard at `http://localhost:8080` and proxies all `/api/...` requests server-to-server, eliminating CORS restrictions entirely.

**Browser-Only Mode** — opening `index.html` directly:
1. **Authentication Token Exchange**: The app takes your NSS Developer Refresh Token and makes an HTTP `POST` call to the NetApp OAuth endpoint (`/tokens/accessToken`).
2. **REST Telemetry Harvesting**: Standard HTTP `GET` requests to `/systems` and `/watchlists` endpoints.
3. **CORS Bypass Required**: Requires a browser CORS extension or Chrome launched with `--disable-web-security`.
4. **Background Polling Loop**: A 60-second checking interval (`checkAutoSync()`) triggers automatic telemetry refreshes based on your configured sync interval.

### 2. Zero-Trust Local Storage & Security

Data security is critical when handling enterprise datacenter telemetry. This dashboard runs on a **zero-trust local-only architecture**:
* **Where Data is Stored**: In browser-only mode, all data persists in `localStorage`. When using `server.py`, data is additionally stored in a local SQLite database (`aiq_cache.db`) which remains on your local machine.
* **Zero External Transmission**: No telemetry data, serial numbers, IP addresses, or access tokens are ever transmitted to external servers, cloud databases, or third-party loggers. The server only communicates with official NetApp API endpoints.
* **Offline Independence**: The SQLite database and localStorage cache both support fully offline operation after initial sync. The dashboard can be used in air-gapped secure rooms without losing access to reports or audit logs.

---

## Setup & Deployment

### Quick Start
1. Install **Python 3.8+**.
2. Install dependencies: `pip install -r requirements_desktop.txt`
3. Run: `python server.py`
4. Open `http://localhost:8080` in your browser.
5. In **Settings**, paste your **Active IQ Refresh Token** and click **Sync**.

### Setting Up API Credentials
1. Log in to [activeiq.netapp.com](https://activeiq.netapp.com/).
2. Click **Quick Links** > **API Services**.
3. Click **Generate Token** to create your **Refresh Token**.
4. Paste this token into the dashboard **Settings & Config** tab.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| **Server won't start** | Verify Python 3.8+ is installed (`python --version`). Check that port 8080 is not in use (`netstat -an | findstr 8080`). |
| **No data after sync** | Verify your Refresh Token is valid and not expired. Check the `server.py` terminal output for API error messages. |
| **Empty dashboard** | Ensure you've clicked **Sync** in Settings. Try enabling **Demo Mode** first to confirm the UI works. |
| **CORS errors** | Use `server.py` instead of opening `index.html` directly. Set the API Base URL to `/api`. |
| **Charts show wrong dates** | Hard refresh with `Ctrl+Shift+R` to clear cached JavaScript. |
| **Stale or outdated data** | The SQLite database persists data indefinitely. Use **Force Full Resync** in Settings to re-harvest all systems. |
| **Database locked errors** | Close any other programs accessing `aiq_cache.db`. Restart `server.py`. |

---

## Data Security, Sovereignty & AI Compliance Statement

This reporting tool was designed from the ground up to comply with strict corporate security baselines, air-gapped environments, and data protection guidelines. 

### 1. 100% AI-Free Processing (No LLMs)
* **Zero AI/ML Dependencies**: This application does **not** make calls to, communicate with, or use any generative AI, Machine Learning (ML), or Large Language Model (LLM) services (internally or externally). 
* **Deterministic Logic**: All risk calculations, remediation schedules, and action control runbooks are derived locally using deterministic, standard JavaScript algorithms. There is no risk of hallucinated commands or unauthorized data leaks to public/private AI model training pipelines.

### 2. Complete Data Sovereignty & Privacy
* **Self-Contained Local Execution**: The dashboard compiles into a single HTML file (`index.html`). It runs fully inside your browser sandbox and can be executed completely offline.
* **Local SQLite Persistence**: When using `server.py`, all harvested data is stored in a local SQLite database (`aiq_cache.db`) that remains strictly on your local machine. No data is transmitted to external databases or cloud services.
* **No External Data Leakage**: The application does not utilize tracking cookies, analytics modules, Google Analytics, or external web beacons.
* **Browser-Private Storage**: Configuration, tokens, and custom metadata are stored in the browser's `localStorage` and/or the local SQLite database — both remain on your machine.
* **Authorized TLS Endpoint Polling**: The application only contacts NetApp's official, TLS-encrypted endpoints (`https://api.activeiq.netapp.com` and `https://gql.aiq.netapp.com`).

### 3. NetApp Security Policy Adherence
* **Read-Only Telemetry Ingest**: The dashboard does not run execution commands against active production storage nodes. Telemetry ingestion is strictly read-only.
* **Change Control Enforcement**: Rather than applying changes itself, the dashboard outputs standard ITIL-aligned change tickets and version-aware step-by-step CLI runbooks for review and execution by authorized system engineers during scheduled maintenance windows.
* **Corporate IT Compliance**: Minimal footprint — run `server.py` or open `index.html` directly. No installation, no external data shares, fully compliant with NetApp's data security classifications and standard corporate computer policies.

---

## Change History
See the [CHANGELOG.md](CHANGELOG.md) for version release details.
