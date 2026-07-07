# NetApp Active IQ Account Report Dashboard

[![Version](https://img.shields.io/badge/version-1.6.0-blue)](CHANGELOG.md)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A zero-dependency, browser-based report builder and dashboard tailored for NetApp Support Account Managers (SAM), Technical Account Managers (TAM), and Customer Success Managers (CSM).

This tool runs **entirely inside your browser** (as a static webpage) from this local folder. It does not require any backend server, Node.js/Python installations, or database engines. It connects directly to the Active IQ Digital Advisor APIs (`activeiq.netapp.com`) and persists credentials in your browser's private local storage.

---

## What's New in Version 1.6.0

*   **L1 Connection & Port Mapping Visualizer**: Audit physical cabling topologies directly inside the Technical Health tab. Displays a rear controller panel interface card with color-coded port indicators and dynamically draws interactive SVG cabling paths to corresponding link partner Core/SAN Switches or Disk Shelves, integrating live LED statuses matching active predictive telemetry warning risks.
*   **Sub-Tabbed Action Planner**: Refactored the long Action Planner view into clean, tabbed sections. You can easily switch between report areas, each showing active alert-count counts (e.g. *Technical Risks (4)*), with media-print overrides to print the entire sequence to PDF automatically.
*   **In-Tab Deliverable Downloads**: Download categorized reports and templates directly within each section of the Action Planner. Includes options to export full system inventories as a CSV spreadsheet or download custom customer advisory email drafts, switch firmware checklists, and site dispatch tickets as TXT files.
*   **GraphQL Query Console Sandbox**: Play with and validate live Active IQ GraphQL queries directly from the Settings page. Includes syntax defaults, variable JSON editors, execution timers, and formatted JSON output blocks.
*   **Universal Offline file:// Protocol Support**: Wrapped all `localStorage` reads/writes in fail-safe try/catch accessors to prevent DOMException crashes, allowing you to open the dashboard directly from your local filesystem (double-clicking the `index.html` file) in any modern browser.
*   **Sleek Neon-Cyan Scrollbars**: Overrode default Webkit scrollbar selectors with custom glowing scrollbar themes matching the general dark cyber-aesthetic of the dashboard.

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
    *   *Multipathing*: Verifies that Native Multipathing (NMP) Path Selection Policy (PSP) is configured to **Round Robin (VMW_PSP_RR)** instead of default Fixed/MRU, and that the IOPS limit is modified to `1` (via `esxcli storage nmp psp roundrobin device config set -I 1 -t iops`) to balance controller load and prevent latency warnings.
    *   *Integration Plugins*: Audits connectivity and credentials for **VASA Provider** and **ONTAP Tools for VMware (OTV)** for VVol and datastore provisioning.
*   **Kubernetes (Astra Trident)**:
    *   *Driver Versioning*: Flags outdated Astra Trident CSI drivers backing Kubernetes Persistent Volumes (PVs) that mismatch host API versions.
*   **Cloud Providers (AWS / Azure / GCP)**:
    *   *VPC Endpoints*: Tracks network latency timeouts between CVO nodes and backing S3/Blob storage, recommending private VPC endpoints to reduce cloud data routing costs.

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

### 3. Setting Up Production API Credentials
To view your own live customer accounts and clusters:
1. Open your browser and log in to [activeiq.netapp.com](https://activeiq.netapp.com/) using your NetApp Support Site (NSS) credentials.
2. In the top navigation bar, click the **Quick Links** icon and select **API Services**.
3. Under the API Services tab, click **Generate Token**.
4. Copy the long **Refresh Token** shown on screen.
5. In your local dashboard application, navigate to the **Settings & Config** tab.
6. Disable **Offline Demo Mode**, paste the token into the **Refresh Token** input box, and click **Save Configuration**.

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

### Option C: Serve via a Simple Local Web Server
If your security policies prevent browser modifications, serve the files from a local port rather than `file://`:
* If you have Python installed, open your command prompt/terminal in this folder and run:
  ```bash
  python -m http.server 8080
  ```
* Open your browser and navigate to `http://localhost:8080` to access the app with standard local origin permissions.

---

## Change History
See the [CHANGELOG.md](CHANGELOG.md) for version release details.
