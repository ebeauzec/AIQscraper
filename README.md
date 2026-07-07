# NetApp Active IQ Account Report Dashboard

[![Version](https://img.shields.io/badge/version-1.8.0-blue)](CHANGELOG.md)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A zero-dependency, browser-based report builder and dashboard tailored for NetApp Support Account Managers (SAM), Technical Account Managers (TAM), and Customer Success Managers (CSM).

This tool runs **entirely inside your browser** (as a static webpage) from this local folder. It does not require any backend server, Node.js/Python installations, or database engines. It connects directly to the Active IQ Digital Advisor APIs (`activeiq.netapp.com`) and persists credentials in your browser's private local storage.

---

## What's New in Version 1.8.0

*   **Active IQ API Polling & Sync Configurations**: Added API Base URL inputs, selectable synchronization intervals (6, 12, 24 hours or 7 days), and a local synchronization metrics dashboard (tracking last/next sync times) to the settings view. Added an automated background interval timer that checks for sync criteria and triggers data updates without blocking UI operations.
*   **Watchlist-Only Synchronization**: Added an option to filter and synchronize only systems belonging to your active Active IQ Watchlists, saving API call quotas.
*   **Fixed Upgrade Path Down-grades**: Corrected version check loops in the pathfinder logic. Targeted OS/firmware upgrades now always guide the user to higher baselines, and up-to-date systems properly report empty hops in both the UI and printed deliverables.
*   **Resolved Support Article Links**: Replaced dead `/onprem/...` paths on `kb.netapp.com` (which returned 404s and triggered support portal redirects) with correct, working `/Advice_and_Troubleshooting/...` native URL routes.

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
*   **ONTAP (FAS & AFF Systems)**: On-premises primary flash storage.
*   **Cloud Volumes ONTAP (CVO)**: Software-defined storage deployed in AWS, Azure, or GCP.
*   **StorageGRID**: Webscale S3/Swift object storage.
*   **MetroCluster IP/FC**: High-availability synchronous multi-site disaster recovery configurations.
*   **SnapMirror & SyncMirror**: Asynchronous and synchronous remote data replication paths.

### 3rd-Party Platform & Hypervisor Best Practices
The tool highlights compliance warnings against NetApp storage best practices for virtualization hosts and orchestrators:
*   **VMware vSphere / ESXi**:
    *   *Multipathing*: Verifies that Native Multipathing (NMP) Path Selection Policy (PSP) is configured to **Round Robin (VMW_PSP_RR)** instead of default Fixed/MRU, and that the IOPS limit is modified to `1` — executing either `esxcli storage nmp psp roundrobin device config set -d <naa_id> -I 1 -t iops` (for ESXi 6.x) or `esxcli storage nmp psp roundrobin device config set --device <naa_id> --type iops --iops 1` (for ESXi 7.0/8.0+) — to balance controller load and prevent latency warnings.
    *   *Integration Plugins*: Audits connectivity and credentials for **VASA Provider** and **ONTAP Tools for VMware (OTV)** for VVol and datastore provisioning.
*   **Kubernetes (Astra Trident)**:
    *   *Driver Versioning*: Flags outdated Astra Trident CSI drivers backing Kubernetes Persistent Volumes (PVs) that mismatch host API versions.
*   **Cloud Providers (AWS / Azure / GCP)**:
    *   *VPC Endpoints*: Tracks network latency timeouts between CVO nodes and backing S3/Blob storage, recommending private VPC endpoints to reduce cloud data routing costs.

### 3rd-Party Workload Auto-Detection
Active IQ automatically identifies specific software workloads running on your cluster storage systems:
*   **SAP HANA Databases**: Classified by parsing ONTAP export policies (NFSv3/NFSv4.1 mount options such as `rsize=262144`, `wsize=262144`), volume naming patterns (containing `/usr/sap` or `sid`), certified initiator groups (igroups), and performance telemetry signatures (massive sequential 8MB write savepoints vs. low-latency 8KB transaction log commits).
*   **Kubernetes Container Orchestrators**: Identified via integration with **Astra Trident** and **Astra Control**. Trident writes structured JSON configuration payloads directly into the ONTAP volume comment field upon PVC creation (storing PVC names, namespaces, and cluster identifiers), which are extracted by Active IQ's AutoSupport ingest pipelines to map cluster topologies.

---

## Site Logistics & Customer Health Editor

SAMs and TAMs can manage account-specific details directly inside the application:
1. Go to the **Settings & Config** tab.
2. Select a system from the **Select System to Edit** dropdown.
3. Edit the following sections:
   *   *Logistics*: Delivery addresses, site access requirements (security clearances, escorts), and courier alerts.
   *   *Contacts*: Site engineer name, telephone, email, and NSS username.
   *   *Account Health*: CSAT score, AM/TAM representatives, upsell opportunities, and refresh timeline dates.
   *   *Projections*: Forecasted storage runway days, daily growth rates, peak IOPS performance, and historical capacity CSV strings.
   *   *Security Bulletins*: Enter technical vulnerabilities directly as a JSON array.
   *   *Support Cases*: Enter active case listings as a JSON array.
4. Click **Save System Metadata** to commit changes to local storage.

---

## Exporting & Importing Report Configurations

To share customer environments or preserve custom report states:
1.  **Exporting**: Click **Export Config (JSON)** on the Overview page or Settings page. This downloads a local JSON file containing your active systems list, risk profiles, contract lifecycles, and efficiency telemetry.
2.  **Importing**: Click **Import Config (JSON)** and select a previously exported `.json` configuration file. The webpage will immediately parse the schema and refresh all modules (TAM, SAM, CSM, Planner) with the new data.

---

## Action Plan Guidelines & Best Practices

When presenting the generated **Executive Action Plans** to customers, account teams should align next steps with NetApp change standards:

1.  **Change Management Windows**: 
    *   All hardware swaps (SAS cables, failed sparing drives, chassis fans) and firmware upgrades should be routed through internal Change Advisory Boards (CAB).
    *   Even if actions are designated as online/non-disruptive, schedule them during off-peak windows to absorb transient controller failovers or path resets without impacting production apps.
2.  **Firmware Updates**:
    *   Disk and shelf firmware updates should be applied before attempting major ONTAP OS upgrades to ensure complete driver compatibility.
3.  **Active IQ Change Advisor**:
    *   Utilize the Change Advisor tool inside the Active IQ portal to validate compatibility metrics for complex upgrades, especially MetroCluster switches or SnapMirror destinations.

## End-to-End Architecture, Data Handling, & Core Use Cases

This section outlines how data is handled behind the scenes and maps out practical operational workflows for TAM, SAM, and Customer Success functions.

### 1. Data Polling Architecture & Data Flows

The application operates on a local client-side polling cycle:
1. **Authentication Token Exchange**: The app takes your NSS Developer Refresh Token and makes an HTTP `POST` call to the NetApp OAuth endpoint (`/tokens/accessToken`). This returns a short-lived JSON Web Token (JWT) access token (valid for 1 hour).
2. **Telemetry Harvesting**: The app executes standard HTTP `GET` requests to retrieve telemetry endpoints:
   * `/systems`: Retrieves cluster inventory, OS/firmware versions, hardware platforms, capacity statistics, and SnapMirror states.
   * `/watchlists`: Retrieves user-configured cluster groups to enable targeted filtering.
3. **CORS Bypass Layer**: Because the application runs as a static file, requests are routed either directly to the public API (when a local CORS unblocking extension is active) or through a local reverse-proxy gateway configuration (when deployed on a local server).
4. **Background Polling Loop**: The application instantiates a 60-second checking interval (`checkAutoSync()`). If automatic synchronization is enabled (e.g., 6 hours, 12 hours, or 24 hours) and the duration since the last sync exceeds the configured threshold, the browser automatically executes a telemetry refresh in the background.

### 2. Zero-Trust Local Storage & Security

Data security is critical when handling enterprise datacenter telemetry. This dashboard runs on a **zero-trust local-only architecture**:
* **Where Data is Stored**: All credentials, access tokens, customer system databases (`aiq_systems_db`), custom subgroups (`aiq_custom_groups`), watchlists, and custom metadata are persisted **strictly inside the browser's local sandbox (`localStorage`)**.
* **Zero External Transmission**: No telemetry data, serial numbers, IP addresses, or access tokens are ever transmitted to external servers, cloud databases, or third-party loggers.
* **Offline Independence**: Because the database resides in `localStorage`, the dashboard can be run fully offline in air-gapped secure rooms without losing access to reports or previous audit logs.

---

### 3. User Role Workflows & Real-World Use Cases

The dashboard consolidates technical metrics to serve three distinct support functions:

#### Use Case A: Technical Account Manager (TAM) - Deep-Dive Engineering & Upgrades
* **Goal**: Audit a customer's environmental health, identify hardware faults, and plan a major OS upgrade sequence.
* **End-to-End Steps**:
  1. Open the **Overview Dashboard** and select the customer's cluster (e.g., `netapp-aff-01`).
  2. Navigate to the **TAM Tab** and review active risks (e.g., "Single Controller Path Failure").
  3. Inspect the **L1 Cabling Map** diagram at the bottom of the page to identify the exact physical controller port (e.g., Slot A - Port 1a) and destination shelf port reporting errors.
  4. Go to **Upgrade Pathfinder** under the actions column. Review the multi-hop OS path (e.g., upgrading a legacy 9.5 system to 9.12.1 requires intermediate hops through 9.7 and 9.11). Copy the sequential command instructions and read-only NetApp support guides.
  5. Toggle to the **Virtualization & Containers** card to check ESXi Round Robin compliance and Astra Trident CSI driver versions.

#### Use Case B: Support Account Manager (SAM) - Service Operations & Case Escalations
* **Goal**: Conduct a weekly operational review with a customer, audit open support tickets, and address warranty renewals.
* **End-to-End Steps**:
  1. Open the dashboard and filter the sidebar by the customer's account name.
  2. Navigate to the **SAM Tab** and review the **Support Contracts** grid. Note any systems showing red warnings (warranty expiring in less than 30 days) to prepare renewal quotes.
  3. Audit the **Open Technical Cases** log. Read case summaries, priority levels, and TAM engineering notes. Highlight critical "S1" or "S2" cases blocking progress.
  4. Check the **Field Actions** table to see if any outstanding factory recalls or critical firmware bulletins require scheduling cluster maintenance.
  5. Click **Download Operations Report (CSV)** to export the ticket list into Excel for the customer meeting.

#### Use Case C: Customer Success Manager (CSM) - Adoption, ROI, & QBR Planning
* **Goal**: Prepare data-backed slides for a Quarterly Business Review (QBR), showing capacity growth runways and software feature adoption rates.
* **End-to-End Steps**:
  1. Filter the sidebar by the customer account.
  2. Navigate to the **CSM Tab** and inspect the **Storage Efficiency & ROI** gauges. Note the overall data reduction ratio (e.g. 3.5:1) and space saved to calculate cost savings.
  3. Review **FabricPool Cloud Tiering**: Identify how many TBs of cold data have been migrated to AWS S3/Azure Blob to demonstrate hybrid cloud ROI.
  4. Audit the **Capability Adoption Grid**: Check if SnapMirror replication is enabled to verify disaster recovery compliance.
  5. Check the **Capacity Runway Projection**: Review the 3-month growth trend graph to estimate when the customer will reach 90% capacity, and generate a preemptive tech refresh recommendation.
  6. Go to the **Action Planner**, select the customer, click **Generate Consolidated Action Plan**, and print it to a clean PDF report to share during the QBR.

---

## Indemnity & License Agreement

This tool is distributed under the **MIT License**. 

> [vanity badge](LICENSE)
> **Operational Responsibility & Indemnity Disclaimer:**
> This is an unofficial utility script. Users are solely responsible for verifying the accuracy of the risks, field actions, contract states, and ONTAP upgrade targets in this dashboard before scheduling maintenance or making configuration changes to production clusters. The developers and contributors of this tool assume no liability for system downtime, data corruption, or service disruptions.
> 
> For full details, see the [LICENSE](LICENSE) file.

### Strict Read-Only Design
This dashboard is designed to be **strictly read-only** under all circumstances. It retrieves read-only telemetry data using HTTP `GET` requests. It contains no forms, endpoints, scripts, or interfaces that can execute mutating requests (`POST` for configuration, `PUT`, `PATCH`, or `DELETE`) against the Active IQ portal or any customer storage systems. The only `POST` call in the application is strictly for the initial authentication token swap.

---

## Instructions

### 1. Launch the Application
Simply double-click the **`index.html`** file in this directory to open the dashboard in your default web browser (Chrome, Edge, or Firefox).

### 2. Testing with Demo Data (Offline Mode)
To see how the dashboard functions immediately:
1. Open the dashboard.
2. Click the **Settings & Config** tab in the sidebar.
3. Turn on the **Enable Offline Demo Mode (Mock Data)** toggle.
4. Go back to the **Overview Dashboard** to inspect system reports, charts, and metrics. Click on any system row, go to **Technical Audit**, and click **Remediation Plan** on a risk to see the detailed action plan.

### 3. Setting Up Production API Credentials & Polling
To view your own live customer accounts and clusters:
1. Open your browser and log in to [activeiq.netapp.com](https://activeiq.netapp.com/) using your NetApp Support Site (NSS) credentials.
2. In the top navigation bar, click the **Quick Links** icon and select **API Services**.
3. Under the API Services tab, click **Generate Token**.
4. Copy the long **Refresh Token** shown on screen.
5. In your local dashboard application, navigate to the **Settings & Config** tab.
6. Disable **Offline Demo Mode**, paste the token into the **Refresh Token** input box.
7. Configure the **Active IQ API Base Endpoint URL** (defaults to the public NetApp REST API gateway).
8. Select an **Auto-Polling / Sync Interval** (Manual Sync, or automatic checks every 6, 12, or 24 hours).
9. Toggle **Watchlist-Only Synchronization** if you want to only synchronize systems listed in your active Active IQ Watchlists.
10. Click **Save Configuration** or **Synchronize Data Now** to trigger the initial sync.

---

## Bypassing Browser CORS Checks

Because the page is loaded directly as a local file (`file:///.../index.html`), browser security rules (CORS) may block direct JavaScript `fetch` calls to the public Active IQ API domain. 

If you encounter connection errors when trying to connect to the live API, choose one of these options:

### Option A: Use a Developer Browser Extension (Easiest)
Install a standard, browser-approved developer extension that toggles CORS headers for local files:
* **Chrome**: Search the Chrome Web Store for **"CORS Unblock"** or **"Allow CORS"** and enable it.
* **Firefox/Edge**: Search their respective add-on stores for **"CORS Bypass"** or **"CORS Access Control"**.

### Option B: Launch Chrome with Web Security Disabled
Create a temporary browser instance that relaxes cross-origin limitations for local testing:
* **Windows (PowerShell/Run CMD)**:
  ```cmd
  chrome.exe --disable-web-security --user-data-dir="C:/temp_chrome_dev"
  ```
* **macOS (Terminal)**:
  ```bash
  open -n -a "Google Chrome" --args --user-data-dir="/tmp/temp_chrome_dev" --disable-web-security
  ```

### Option C: Serve and Proxy via server.py (Best Server-to-Server Practice)
If your security policies prevent browser extensions/modifications, serve the files and proxy all API calls natively using the included custom Python server:
* Open your command prompt/terminal in this folder and run:
  ```bash
  python server.py
  ```
* Open your browser and navigate to `http://localhost:8080` to access the dashboard.
* In the **Settings & Config** tab, change the **Active IQ API Base Endpoint URL** to `/api` and click **Save Configuration**.
* The server will automatically intercept all `/api/...` calls and forward them to the NetApp API server-to-server, bypassing CORS restrictions without compromising security.

---

## Change History
See the [CHANGELOG.md](CHANGELOG.md) for version release details.
